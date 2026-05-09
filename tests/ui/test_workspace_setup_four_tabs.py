"""Phase 10.2 Verification: workspace_setup remapped to 4 tabs with SchnittWorkspace."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


def test_main_window_has_four_stack_widgets_and_schnitt():
    _qapp()
    from main import PBWindow
    win = PBWindow()
    try:
        assert win.workspace_stack.count() == 4
        assert hasattr(win, "_schnitt_ws")
        assert win._schnitt_ws is not None
    finally:
        win.close()
