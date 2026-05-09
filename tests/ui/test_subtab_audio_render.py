"""Render-Test fuer Sub-Tab Audio Beatgrid (Phase 07 / Task 7.2)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.workspaces.schnitt.tab_audio import SchnittTabAudio


def _qapp():
    return QApplication.instance() or QApplication([])


def test_set_audio_id_renders_grid_items():
    _qapp()
    t = SchnittTabAudio()
    t.set_audio_id(None)  # Defensive: kein Audio
    assert t.waveform_view.scene().itemsBoundingRect().isEmpty()

    # mit fake-Daten
    t.render_grid_lines([0.5, 1.0, 1.5, 2.0])
    assert len(t.waveform_view.scene().items()) >= 4
