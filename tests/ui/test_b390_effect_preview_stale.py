"""B-390: Eine spaeter fertig werdende aeltere Effekt-Vorschau (stale Worker)
darf die Vorschau des juengsten Requests nicht ueberschreiben.

_start_effect_worker erhoeht eine monotone _effect_request_seq und bindet sie an
den Frame-Callback; _on_effect_frame_ready verwirft Frames, deren req_id nicht der
aktuellen Sequenz entspricht.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def _ctrl(current_seq: int):
    from ui.controllers.convert import ConvertController
    c = ConvertController.__new__(ConvertController)
    c._effect_request_seq = current_seq
    c.window = SimpleNamespace(effects_preview=MagicMock())
    return c


def test_b390_stale_frame_is_discarded():
    _qapp()
    c = _ctrl(current_seq=5)
    # aelterer Worker (req_id=3) wird fertig -> muss verworfen werden
    c._on_effect_frame_ready(b"\x00" * 12, 2, 2, req_id=3)
    c.window.effects_preview.setPixmap.assert_not_called()


def test_b390_current_frame_updates_preview():
    _qapp()
    c = _ctrl(current_seq=5)
    # juengster Worker (req_id=5) -> Vorschau wird gesetzt
    c._on_effect_frame_ready(b"\x00" * 12, 2, 2, req_id=5)
    c.window.effects_preview.setPixmap.assert_called_once()


def test_b390_start_worker_increments_sequence():
    from ui.controllers.convert import ConvertController
    c = ConvertController.__new__(ConvertController)
    c._effect_request_seq = 7
    c.window = SimpleNamespace(
        worker_dispatcher=SimpleNamespace(_start_worker_thread=MagicMock()),
        effects_preview=MagicMock(),
    )
    # FrameExtractWorker echt zu bauen wuerde ffmpeg anfassen -> wir pruefen nur,
    # dass die Sequenz monoton steigt. _start_effect_worker baut den Worker; falls
    # das fehlschlaegt, war die Sequenz aber schon erhoeht (Zeile vor Worker-Bau).
    try:
        c._start_effect_worker("nonexistent.mp4", "")
    except Exception:
        pass
    assert c._effect_request_seq == 8
