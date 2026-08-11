"""B-746: schaltet der AUDIO-Tab im Material-Workspace wirklich um?

Das Ticket meldete einen No-Op: Klick auf ``AUDIO`` liefert Harness-Erfolg,
sichtbar bleibt aber die Videoansicht. Ein Current-Retry am 2026-08-02 zeigte
das Gegenteil (``a01_drums``, ``Stems``, ``Audio: a01_drums`` erschienen), und
die statische Pruefung fand ein symmetrisches Toggle-Wiring ohne Overlay- oder
EventFilter-Quelle, die Maus-Events schluckt. Das Ticket blieb seither
``needs-verification``, weil der No-Op nie reproduzierbar war.

Dieser Test beantwortet die Frage dauerhaft auf Widget-Ebene, statt sie bei
jedem GUI-Lauf neu zu stellen: er umgeht Maus/HiDPI/Koordinaten komplett und
prueft ausschliesslich, ob der Zustandswechsel des Buttons den Stack
mitnimmt. Faellt er, ist es ein echter Produktfehler; bleibt er gruen und die
GUI zeigt trotzdem nichts, liegt es am Klick, nicht am Wiring — genau die
Unterscheidung, an der B-746 haengengeblieben ist (vergleiche B-616, dort war
es nachweislich das Testwerkzeug).

Pattern wie ``tests/ui/test_workspaces_smoke.py``: offscreen Qt, plain
QApplication, kein qtbot.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture()
def media_ws():
    _ensure_qapp()
    from ui.workspaces import MediaWorkspace

    w = MediaWorkspace()
    yield w
    w.deleteLater()


def test_b746_audio_button_switches_stack(media_ws):
    """Der Kern des Tickets: AUDIO aktivieren muss den Stack auf Index 1 legen."""
    assert media_ws.mode_stack.currentIndex() == 0, "Startzustand ist Video"

    media_ws.btn_mode_audio.setChecked(True)
    assert media_ws.mode_stack.currentIndex() == 1, (
        "B-746: btn_mode_audio wurde aktiviert, der mode_stack ist aber nicht "
        "auf die Audio-Seite gewechselt — das waere der gemeldete No-Op."
    )


def test_b746_video_button_switches_back(media_ws):
    """Rueckweg: der Toggle muss symmetrisch sein, nicht nur einmal wirken."""
    media_ws.btn_mode_audio.setChecked(True)
    assert media_ws.mode_stack.currentIndex() == 1

    media_ws.btn_mode_video.setChecked(True)
    assert media_ws.mode_stack.currentIndex() == 0, (
        "B-746: Rueckschalten auf VIDEO hat den Stack nicht zurueckgesetzt."
    )


def test_b746_buttons_are_mutually_exclusive(media_ws):
    """Beide Modi gleichzeitig aktiv waere ein widerspruechlicher Zustand.

    Genau daraus entstuende die Beobachtung des Tickets — 'VIDEO bleibt gold',
    obwohl AUDIO angeklickt wurde.
    """
    media_ws.btn_mode_audio.setChecked(True)
    assert media_ws.btn_mode_video.isChecked() is False, (
        "B-746: VIDEO blieb aktiv, obwohl AUDIO gewaehlt wurde."
    )

    media_ws.btn_mode_video.setChecked(True)
    assert media_ws.btn_mode_audio.isChecked() is False, (
        "B-746: AUDIO blieb aktiv, obwohl VIDEO gewaehlt wurde."
    )


def test_b746_buttons_are_enabled_and_checkable(media_ws):
    """Ein deaktivierter oder nicht-checkbarer Button waere ein stiller No-Op."""
    for name in ("btn_mode_video", "btn_mode_audio"):
        btn = getattr(media_ws, name)
        assert btn.isEnabled(), f"B-746: {name} ist deaktiviert."
        assert btn.isCheckable(), f"B-746: {name} ist nicht checkable."
