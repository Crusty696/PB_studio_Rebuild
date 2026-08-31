"""B-946 — Ducking-Ergebnisse landeten im Repo statt im Projekt.

Der Ordner wurde an zwei Stellen unabhaengig gebildet, beide ueber
``Path(__file__).parent...``:

* ``ui/controllers/stems.py`` (Knopf in der Oberflaeche)
* ``workers/registry.py`` (Chat-Aktion, seit B-940)

Folge: Ergebnisse aller Projekte lagen im selben Ordner und vermischten sich
beim Projektwechsel. Im Repo-Baum blockierten sie ausserdem den Handoff-Check —
am 2026-08-31 mit 86 MB aus einem einzigen Live-Test.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from services.ducked_paths import ducked_ausgabe, ducked_ordner, projekt_wurzel


def test_ordner_liegt_neben_den_stems(monkeypatch, tmp_path):
    """Stems liegen unter <APP_ROOT>/storage/stems — Ducking gehoert daneben."""
    import database.session as sess

    monkeypatch.setattr(sess, "APP_ROOT", tmp_path)

    assert ducked_ordner(anlegen=False) == tmp_path / "storage" / "ducked"


def test_pfad_folgt_dem_projektwechsel(monkeypatch, tmp_path):
    """APP_ROOT wird von set_project umgebogen; ein kopierter Wert waere veraltet."""
    import database.session as sess

    erstes = tmp_path / "projekt_a"
    zweites = tmp_path / "projekt_b"

    monkeypatch.setattr(sess, "APP_ROOT", erstes)
    a = ducked_ausgabe("Track", anlegen=False)

    monkeypatch.setattr(sess, "APP_ROOT", zweites)
    b = ducked_ausgabe("Track", anlegen=False)

    assert a != b
    assert str(erstes) in a
    assert str(zweites) in b


def test_wert_wird_zur_laufzeit_gelesen():
    """Quellcode-Guard: kein 'from database.session import APP_ROOT'.

    Ein zum Importzeitpunkt kopierter Wert bleibt beim Projektwechsel stehen —
    genau der Fehler, den services/stem_router.py mit getattr vermeidet.
    """
    src = inspect.getsource(projekt_wurzel)

    assert "getattr" in src
    assert "from database.session import APP_ROOT" not in src


@pytest.mark.parametrize("titel, erwartet", [
    ("AC/DC: Back*in?Black", "AC_DC_ Back_in_Black_ducked.wav"),
    ("Ein <Track>", "Ein _Track__ducked.wav"),
    ("", "track_ducked.wav"),
    (None, "track_ducked.wav"),
])
def test_verbotene_zeichen_im_dateinamen(monkeypatch, tmp_path, titel, erwartet):
    import database.session as sess

    monkeypatch.setattr(sess, "APP_ROOT", tmp_path)

    assert Path(ducked_ausgabe(titel, anlegen=False)).name == erwartet


def test_ohne_app_root_faellt_es_auf_den_repo_ordner_zurueck(monkeypatch):
    """Kein aktives Projekt darf das Ducking nicht verhindern."""
    import database.session as sess

    monkeypatch.setattr(sess, "APP_ROOT", None)

    wurzel = projekt_wurzel()

    assert wurzel.is_dir()
    assert (wurzel / "services").is_dir(), "Rueckfall zeigt auf den Repo-Ordner"


def test_beide_aufrufer_nutzen_dieselbe_stelle():
    """Der Kern von B-946: keine zweite, unabhaengige Pfadbildung mehr."""
    import ui.controllers.stems as stems_modul
    import workers.registry as registry_modul

    for modul in (stems_modul, registry_modul):
        quelle = inspect.getsource(modul)
        assert "ducked_ausgabe" in quelle, f"{modul.__name__} nutzt den Helfer nicht"
        assert '"storage" / "ducked"' not in quelle, (
            f"{modul.__name__} bildet den Pfad wieder selbst"
        )
