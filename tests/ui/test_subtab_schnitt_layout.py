"""Layout-Test fuer SchnittTabSchnitt (Phase 05 / Task 5.1)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.workspaces.schnitt.tab_schnitt import SchnittTabSchnitt


def _qapp():
    return QApplication.instance() or QApplication([])


def test_tab_has_preview_transport_timeline():
    _qapp()
    t = SchnittTabSchnitt()
    assert t.video_preview is not None
    assert t.btn_play.text() in ("▶", "▶")
    assert t.btn_stop.text() in ("■", "■")
    assert t.timeline_view is not None
    assert t.cut_info_label is not None


def test_preview_size_640x360():
    _qapp()
    t = SchnittTabSchnitt()
    assert t.video_preview.minimumWidth() == 640
    assert t.video_preview.minimumHeight() == 360
