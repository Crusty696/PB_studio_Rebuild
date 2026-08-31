"""B-954 — "Zuletzt benutzt" zeigte trotz B-936 dauerhaft "Nie".

Der Live-Test am 2026-08-31 zeigte alle neun Modelle auf "Nie", obwohl die App
SigLIP siebenmal geladen hatte. Dahinter lagen drei Defekte in Reihe:

1. ``touch_last_used`` schreibt nur, wenn die Registry-Zeile schon existiert —
   die entsteht aber erst beim Oeffnen des Modell-Managers (``scan_all``).
   Zusammen mit der Drosselung aus B-945, die sich auch **wirkungslose**
   Versuche merkte, blieb die Spalte danach eine Stunde lang leer.
2. ``_upsert_model`` schrieb bei jedem Scan ``last_used_at`` aus dem
   Scan-Ergebnis zurueck — der Scan kennt keine Nutzungszeit, also NULL. Ein
   Klick auf "Aktualisieren" loeschte den Zeitstempel.
3. ``scan_all`` liefert die Eintraege, die der Dialog anzeigt, mit
   ``last_used_at=""``. Selbst ein korrekter DB-Wert kam nie auf den Schirm.

Nur der erste Teil (Drosselung) stammte aus meiner eigenen Arbeit.
"""

from __future__ import annotations

import datetime

import pytest


# ── 1. Rueckmeldung und Drosselung ───────────────────────────────────────

def test_touch_meldet_wenn_es_nichts_zu_schreiben_gab(test_engine):
    """Ohne Registry-Zeile passiert nichts — das muss der Aufrufer erfahren."""
    from services.model_lifecycle_service import get_model_lifecycle_service

    assert get_model_lifecycle_service().touch_last_used("gibt-es-nicht") is False


def test_touch_meldet_erfolg_mit_zeile(test_engine):
    from sqlalchemy.orm import Session

    from database import ModelRegistry
    from services.model_lifecycle_service import get_model_lifecycle_service

    with Session(test_engine) as session:
        session.add(ModelRegistry(model_id="modell-x", source="huggingface"))
        session.commit()

    assert get_model_lifecycle_service().touch_last_used("modell-x") is True


def test_drosselung_merkt_sich_keinen_fehlversuch(monkeypatch):
    """Der Defekt aus B-945: ein wirkungsloser Versuch sperrte eine Stunde."""
    from services.model_manager import ModelManager

    ergebnisse = [False, True]
    aufrufe = []

    class _FakeService:
        def touch_last_used(self, model_id):
            aufrufe.append(model_id)
            return ergebnisse.pop(0)

    import services.model_lifecycle_service as mls

    monkeypatch.setattr(mls, "get_model_lifecycle_service", lambda *a, **k: _FakeService())

    manager = ModelManager.__new__(ModelManager)
    manager._last_used_geschrieben = {}

    ModelManager._touch_last_used(manager, "modell-x")   # scheitert
    assert "modell-x" not in manager._last_used_geschrieben

    ModelManager._touch_last_used(manager, "modell-x")   # jetzt erfolgreich
    assert "modell-x" in manager._last_used_geschrieben
    assert len(aufrufe) == 2, "der zweite Versuch wurde weggedrosselt"


# ── 2. Der Scan darf den Zeitstempel nicht loeschen ──────────────────────

def test_scan_ueberschreibt_die_nutzungszeit_nicht(test_engine):
    from sqlalchemy.orm import Session

    from database import ModelRegistry
    from services.model_lifecycle_service import ModelEntry, get_model_lifecycle_service

    fruher = datetime.datetime(2026, 8, 31, 15, 31, 32)
    with Session(test_engine) as session:
        session.add(ModelRegistry(
            model_id="modell-y", source="huggingface", last_used_at=fruher))
        session.commit()

    svc = get_model_lifecycle_service()
    # So kommt ein Eintrag aus dem Scan: ohne Nutzungszeit.
    svc._upsert_model(ModelEntry(
        model_id="modell-y", source="huggingface", display_name="Y",
        size_mb=1.0, installed_at="", last_used_at="", status="installed"))

    with Session(test_engine) as session:
        zeile = session.query(ModelRegistry).filter_by(model_id="modell-y").first()

    assert zeile.last_used_at == fruher, "der Scan hat die Nutzungszeit geloescht"


# ── 3. Die Anzeige bekommt den Wert aus der Datenbank ────────────────────

def test_gescannte_eintraege_bekommen_die_nutzungszeit(test_engine):
    from sqlalchemy.orm import Session

    from database import ModelRegistry
    from services.model_lifecycle_service import ModelEntry, get_model_lifecycle_service

    with Session(test_engine) as session:
        session.add(ModelRegistry(
            model_id="modell-z", source="huggingface",
            last_used_at=datetime.datetime.utcnow()))
        session.commit()

    eintrag = ModelEntry(
        model_id="modell-z", source="huggingface", display_name="Z",
        size_mb=1.0, installed_at="", last_used_at="", status="installed")

    get_model_lifecycle_service()._nutzungszeiten_nachtragen([eintrag])

    assert eintrag.last_used_at, "Anzeige haette weiter 'Nie' gezeigt"
    assert eintrag.last_used_display == "Heute"


def test_vorhandener_wert_wird_nicht_ueberschrieben(test_engine):
    from services.model_lifecycle_service import ModelEntry, get_model_lifecycle_service

    eintrag = ModelEntry(
        model_id="modell-z", source="ollama", display_name="Z", size_mb=1.0,
        installed_at="", last_used_at="2020-01-01T00:00:00", status="installed")

    get_model_lifecycle_service()._nutzungszeiten_nachtragen([eintrag])

    assert eintrag.last_used_at == "2020-01-01T00:00:00"


def test_leere_liste_stuerzt_nicht_ab(test_engine):
    from services.model_lifecycle_service import get_model_lifecycle_service

    get_model_lifecycle_service()._nutzungszeiten_nachtragen([])
