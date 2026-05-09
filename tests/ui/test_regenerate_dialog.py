"""Phase 06 / Task 6.3: Confirm-Dialog ``confirm_regenerate``."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox

from ui.workspaces.schnitt.regenerate_dialog import confirm_regenerate


def _qapp():
    return QApplication.instance() or QApplication([])


def test_yes_returns_true():
    _qapp()
    with patch.object(
        QMessageBox, "warning",
        return_value=QMessageBox.StandardButton.Yes,
    ):
        assert confirm_regenerate(None) is True


def test_no_returns_false():
    _qapp()
    with patch.object(
        QMessageBox, "warning",
        return_value=QMessageBox.StandardButton.No,
    ):
        assert confirm_regenerate(None) is False
