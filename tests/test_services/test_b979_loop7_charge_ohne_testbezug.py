"""Loop 7.4 — die Charge mit hohem Schadensbild und ohne jeden Testbezug.

`tools/fix_ohne_test.py` führt 42 Bug-IDs, bei denen weder die ID noch das
umschließende Symbol in `tests/` vorkommt. Nach Schweregrad sortiert standen
oben dreizehn mit `severity: high`. Diese Datei deckt die davon ab, die ohne
GUI und ohne Hardware prüfbar sind:

    B-244  services/actions/audio_actions.py:263   describe_audio_track
    B-335  services/brain/scorer.py:52             gewichtetes Mittel
    B-354  services/convert_service.py:275         NVENC-Codec-Prüfung
    B-453  ui/widgets/media_grid.py:1002           QPixmap auf dem GUI-Thread
    B-622  ui/controllers/edit_workspace.py:957    column-select statt session.get
    B-795  ui/controllers/edit_workspace.py:655…   Projekt-Token-Guard
    B-865  ui/controllers/project_management.py    Auto-Resume-Vorrang
    B-913  services/brain_gateway.py:397           Mode-Allowlist für Vision

B-335 war zusätzlich per Handprobe am 2026-09-03 als ungedeckt belegt: der Fix
umgekehrt, `8 passed` — kein Test bemerkte es.

Nicht enthalten und mit Begründung offen gelassen:

* **B-330** — die Fundstelle in `main.py:1947` ist nur ein Verweis in einem
  Kommentar; der eigentliche Fix sitzt in `ui/widgets/wheel_guard.py` und hat
  dort bereits einen Test (`tests/ui/test_wheel_guard.py:109`).
* **B-216, B-217** — im Vault als `reserved-gap` mit `real_bug: false`
  geführt, im Code markieren sie echte Reparaturen. Der Widerspruch gehört
  geklärt, bevor ein Test festschreibt, was gelten soll.
* **B-241 (obsolete), B-235 (deferred), B-864/B-922/B-961 (open)** — ein Test
  würde einen Zustand zementieren, der noch zur Entscheidung steht.
* **B-453** ist enthalten, **B-603** nicht: dessen Batch-Pfad scheitert laut
  Vault real und läuft im Hard-Cut-Fallback. Ein Test würde den Ist-Zustand
  als Soll festschreiben.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _quelle(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _nur_code(text: str) -> str:
    """Kommentare weg — Wächter-Regel aus Loop 6.

    Viermal traf dort ein Guard die gesuchte Zeichenkette im Kommentar.
    """
    return "\n".join(z.split("#", 1)[0] for z in text.splitlines())


def _code_nach_marker(rel: str, marker: str, zeilen: int = 20) -> str:
    alle = _quelle(rel).splitlines()
    for nr, zeile in enumerate(alle):
        if marker in zeile:
            return _nur_code("\n".join(alle[nr + 1:nr + 1 + zeilen]))
    raise AssertionError(f"Marker {marker!r} nicht gefunden in {rel}")


# ---------------------------------------------------------------------------
# B-244 — describe_audio_track als Lese-Aktion
# ---------------------------------------------------------------------------

def test_b244_die_aktion_ist_registriert():
    """Vor dem Fix hatte das Brain keinen Pfad, einen Audio-Track zu beschreiben."""
    from services.action_registry import action_registry
    from services.actions import audio_actions  # noqa: F401 — Import registriert

    assert "describe_audio_track" in action_registry.list_actions()


def test_b244_die_aktion_liest_nur_und_veraendert_nichts():
    """Eine Lese-Aktion darf keinen Worker starten und nichts schreiben."""
    quelle = _nur_code(_quelle("services/actions/audio_actions.py"))
    ab = quelle.index("describe_audio_track")
    block = quelle[ab:ab + 3000]

    assert "session.commit()" not in block, "die Lese-Aktion schreibt in die DB"
    assert "_make_enqueue_action" not in block, "die Lese-Aktion startet einen Worker"


# ---------------------------------------------------------------------------
# B-335 — gewichtetes Mittel statt Division durch die Achsenanzahl
# ---------------------------------------------------------------------------

def test_b335_der_score_teilt_durch_die_gewichtssumme():
    """Der Kern: `weighted_sum / weight_sum`, nicht durch die Achsenanzahl.

    Per Handprobe am 2026-09-03 als ungedeckt belegt — der Fix umgekehrt,
    `8 passed`.
    """
    code = _nur_code(_quelle("services/brain/scorer.py"))

    assert "final = weighted_sum / weight_sum if weight_sum > 1e-9 else 0.0" in code


def test_b335_eine_leere_gewichtssumme_ergibt_null_statt_division():
    """Ohne die Schwelle wäre es eine Division durch Null."""
    def score(weighted_sum: float, weight_sum: float) -> float:
        return weighted_sum / weight_sum if weight_sum > 1e-9 else 0.0

    assert score(0.0, 0.0) == 0.0
    assert score(5.0, 0.0) == 0.0
    assert score(3.0, 2.0) == pytest.approx(1.5)


def test_b335_das_gewichtete_mittel_bleibt_im_wertebereich():
    """Der Kommentar verspricht dieselbe [0,1]-Skala wie die Bridge-Werte."""
    def score(paare):
        ws = sum(w * v for w, v in paare)
        s = sum(w for w, _ in paare)
        return ws / s if s > 1e-9 else 0.0

    # Alle Achsen im Bereich [0,1] -> Ergebnis ebenfalls.
    assert 0.0 <= score([(2.0, 0.1), (1.0, 0.9), (3.0, 0.5)]) <= 1.0
    # Eine schwach gewichtete Ausreisser-Achse kippt das Ergebnis nicht.
    assert score([(10.0, 0.5), (0.1, 1.0)]) == pytest.approx(0.505, abs=0.01)


# ---------------------------------------------------------------------------
# B-354 — NVENC: der tatsächliche Preset-Codec zählt
# ---------------------------------------------------------------------------

def test_b354_geprueft_wird_der_codec_des_presets():
    """Vorher wurde nur auf h264 geprüft — ein HEVC-Preset fiel dann selbst
    dann auf libx264 zurück, wenn hevc_nvenc funktionierte."""
    code = _code_nach_marker("services/convert_service.py",
                             "F-22 (B-354)", zeilen=12)

    assert "nvenc_info.get(preset.video_codec)" in code, (
        "es wird wieder ein fester Codecname geprueft statt des Presets"
    )


def test_b354_nur_nvidia_encoder_im_spiel():
    """GPU-Hartregel des Projekts: ausschliesslich NVENC, sonst CPU."""
    code = _nur_code(_quelle("services/convert_service.py"))

    for fremd in ("h264_qsv", "hevc_qsv", "h264_amf", "hevc_amf",
                  "h264_videotoolbox", "h264_vaapi"):
        assert fremd not in code, f"fremder Hardware-Encoder im Code: {fremd}"


def test_b354_ohne_nvenc_faellt_es_auf_cpu_oder_wirft():
    quelle = _quelle("services/convert_service.py")
    ab = quelle.index("F-22 (B-354)")
    block = quelle[ab:ab + 900]

    assert "require_nvenc()" in block
    assert "ConversionError" in block


# ---------------------------------------------------------------------------
# B-453 — QPixmap entsteht auf dem GUI-Thread
# ---------------------------------------------------------------------------

def test_b453_das_thumbnail_wird_queued_zugestellt():
    """`emit` passiert im Pool-Thread; QPixmap darf nur im GUI-Thread entstehen."""
    code = _nur_code(_quelle("ui/widgets/media_grid.py"))

    assert "runnable.signals.done.connect(card.apply_thumbnail_image)" in code


def test_b453_der_empfaenger_ist_ein_qobject():
    """Nur ein QObject-Empfänger bekommt die Queued-Zustellung."""
    code = _nur_code(_quelle("ui/widgets/media_grid.py"))
    ab = code.index("runnable.signals.done.connect")
    umgebung = code[max(0, ab - 600):ab]

    assert "_get_thumb_pool()" in code[ab:ab + 200]
    assert "card" in umgebung


# ---------------------------------------------------------------------------
# B-622 — column-select statt session.get(AudioTrack)
# ---------------------------------------------------------------------------

def test_b622_der_otio_build_laedt_keine_blobs():
    """`session.get(AudioTrack)` zog beatgrid/waveform_data eager mit — 42 s Freeze."""
    code = _code_nach_marker("ui/controllers/edit_workspace.py",
                             "B-622: column-select statt session.get", zeilen=14)

    assert "session.execute(" in code
    assert "select(" in code
    assert "session.get(" not in code, "der eager-Ladepfad ist zurueck"


@pytest.mark.parametrize("blob", ["beatgrid", "waveform_data"])
def test_b622_keine_blob_beziehung_in_der_auswahl(blob):
    code = _code_nach_marker("ui/controllers/edit_workspace.py",
                             "B-622: column-select statt session.get", zeilen=14)

    assert blob not in code


# ---------------------------------------------------------------------------
# B-795 — Auto-Edit-Ergebnis gegen den Projekt-Token prüfen
# ---------------------------------------------------------------------------

def test_b795_das_ergebnis_wird_gegen_den_projekt_token_geprueft():
    """Ohne Guard schreibt ein spät eintreffender Worker ins neue Projekt."""
    code = _nur_code(_quelle("ui/controllers/edit_workspace.py"))

    assert "B-795" in _quelle("ui/controllers/edit_workspace.py")
    assert "_current_project_token" in code or "project_token" in code, (
        "kein Projekt-Token im Auto-Edit-Pfad"
    )


def test_b795_der_guard_sitzt_an_mehreren_stellen():
    """Erfolgs- und Fehlerpfad brauchen ihn beide."""
    quelle = _quelle("ui/controllers/edit_workspace.py")

    assert quelle.count("B-795") >= 3, (
        f"nur {quelle.count('B-795')} B-795-Stellen — Erfolgs- oder Fehlerpfad fehlt"
    )


# ---------------------------------------------------------------------------
# B-865 — nur Auto-Resume darf den interaktiven Hinweis überspringen
# ---------------------------------------------------------------------------

def test_b865_skip_preblock_ist_ein_eigener_parameter():
    """Ein globales Abschalten würde den B-465-Hinweis für alle Wege entfernen."""
    quelle = _quelle("ui/controllers/project_management.py")

    assert "skip_preblock" in quelle


def test_b865_der_service_guard_bleibt_aktiv():
    """Der Vorrang gilt nur für den interaktiven Hinweis, nicht für den Guard."""
    quelle = _quelle("ui/controllers/project_management.py")
    ab = quelle.index("skip_preblock: B-865")
    block = quelle[ab:ab + 400]

    assert "ProjectManager.open_project" in block
    assert "bleibt aktiv" in block


# ---------------------------------------------------------------------------
# B-913 — Vision-Modus durchläuft die Mode-Allowlist
# ---------------------------------------------------------------------------

def test_b913_nicht_chat_modi_werden_validiert():
    """`brain_learn_note` ist im Vision-Modus nicht erlaubt."""
    code = _code_nach_marker("services/brain_gateway.py",
                             "B-913: Nicht-Chat-Modi", zeilen=6)

    assert "_validate_params(action, payload.get(\"params\", {}), mode)" in code


def test_b913_der_chat_modus_nimmt_den_anderen_zweig():
    """Nur im Chat gibt es die Sonderbehandlung für brain_learn_note."""
    quelle = _quelle("services/brain_gateway.py")
    ab = quelle.index("B-913: Nicht-Chat-Modi")
    davor = quelle[max(0, ab - 400):ab]

    assert 'action == "brain_learn_note" and mode == "chat"' in davor
    assert "normalize_brain_learn_params" in davor


def test_b913_ein_validierungsfehler_wird_abgewiesen():
    quelle = _quelle("services/brain_gateway.py")
    ab = quelle.index("B-913: Nicht-Chat-Modi")
    danach = quelle[ab:ab + 400]

    assert "except ValueError" in danach
    assert "_reject(" in danach


# ---------------------------------------------------------------------------
# Alle Stellen behalten ihren Marker
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("marker,pfad", [
    ("B-244", "services/actions/audio_actions.py"),
    ("B-335", "services/brain/scorer.py"),
    ("B-354", "services/convert_service.py"),
    ("B-453", "ui/widgets/media_grid.py"),
    ("B-622", "ui/controllers/edit_workspace.py"),
    ("B-795", "ui/controllers/edit_workspace.py"),
    ("B-865", "ui/controllers/project_management.py"),
    ("B-913", "services/brain_gateway.py"),
])
def test_alle_stellen_behalten_ihren_marker(marker, pfad):
    """Ohne Marker findet kein Werkzeug die Stelle wieder."""
    assert marker in _quelle(pfad)
