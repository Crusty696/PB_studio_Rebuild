from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_crash_log_button_click_opens_existing_log(monkeypatch, tmp_path) -> None:
    app = _qapp()
    from ui.dialogs import crash_dialog

    log_path = tmp_path / "pb_studio.log"
    log_path.write_text("crash", encoding="utf-8")
    opened: list[str] = []
    monkeypatch.setattr(crash_dialog, "_LOG_PATH", log_path)
    monkeypatch.setattr(crash_dialog.sys, "platform", "win32")
    monkeypatch.setattr(crash_dialog.os, "startfile", opened.append)

    dialog = crash_dialog.CrashDialog(RuntimeError, RuntimeError("boom"), None)
    try:
        dialog.show()
        app.processEvents()
        log_buttons = [
            button
            for button in dialog.findChildren(QPushButton)
            if button.text() == "Log-Datei öffnen"
        ]
        assert len(log_buttons) == 1
        button = log_buttons[0]
        assert button.isVisibleTo(dialog) is True
        assert button.isEnabled() is True

        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert [Path(path) for path in opened] == [log_path]
        assert dialog.isVisible() is True
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()
