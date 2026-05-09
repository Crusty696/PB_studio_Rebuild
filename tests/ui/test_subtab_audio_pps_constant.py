"""PPS-Konstante zentralisiert (Phase 07 / Task T2.4).

Stellt sicher, dass _PIXELS_PER_SECOND existiert und konsistent
in render_grid_lines + set_structure_markers benutzt wird.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGraphicsRectItem

from ui.workspaces.schnitt import tab_audio as audio_mod
from ui.workspaces.schnitt.tab_audio import SchnittTabAudio


def _qapp():
    return QApplication.instance() or QApplication([])


def test_pps_constant_exists_and_is_float():
    assert hasattr(audio_mod, "_PIXELS_PER_SECOND")
    pps = audio_mod._PIXELS_PER_SECOND
    assert isinstance(pps, float)
    assert pps > 0.0


def test_render_grid_lines_uses_pps_constant_by_default():
    _qapp()
    t = SchnittTabAudio()
    pps = audio_mod._PIXELS_PER_SECOND
    t.render_grid_lines([1.0])
    items = t.waveform_view.scene().items()
    assert items, "mind. eine Linie erwartet"
    line = items[0].line()
    assert abs(line.x1() - 1.0 * pps) < 1e-6


def test_structure_markers_use_pps_constant():
    _qapp()
    t = SchnittTabAudio()
    pps = audio_mod._PIXELS_PER_SECOND
    t.set_structure_markers([{"start": 2.0, "end": 6.0, "label": "Drop"}])
    rects = [it for it in t.waveform_view.scene().items()
             if isinstance(it, QGraphicsRectItem)]
    assert len(rects) == 1
    rect = rects[0].rect()
    assert abs(rect.x() - 2.0 * pps) < 1e-6
    assert abs(rect.width() - 4.0 * pps) < 1e-6
