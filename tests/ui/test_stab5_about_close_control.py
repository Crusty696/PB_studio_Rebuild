from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_about_close_button_click_accepts_dialog(monkeypatch) -> None:
    app = _qapp()
    from ui.dialogs import about

    monkeypatch.setattr(about, "_gpu_info", lambda: "NVIDIA GeForce GTX 1060")
    dialog = about.AboutDialog()
    accepted = []
    dialog.accepted.connect(lambda: accepted.append(True))
    try:
        dialog.show()
        app.processEvents()
        close_buttons = [
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == "Schliessen"
        ]
        assert len(close_buttons) == 1
        button = close_buttons[0]
        assert button.objectName() == "btn_accent"
        assert button.isVisibleTo(dialog) is True
        assert button.isEnabled() is True

        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert accepted == [True]
        assert dialog.result() == QDialog.DialogCode.Accepted
        assert dialog.isVisible() is False
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()
