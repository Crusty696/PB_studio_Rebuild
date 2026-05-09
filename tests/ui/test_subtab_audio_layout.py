"""Layout-Test fuer Sub-Tab Audio (Phase 07 / Task 7.1)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.workspaces.schnitt.tab_audio import SchnittTabAudio


def _qapp():
    return QApplication.instance() or QApplication([])


def test_widgets_present():
    _qapp()
    t = SchnittTabAudio()
    assert t.waveform_view is not None
    assert t.stem_workspace is not None
    assert t.lufs_label is not None
    assert t.key_label is not None
