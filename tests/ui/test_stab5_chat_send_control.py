from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow

import ui.chat_dock as chat_dock_module


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_send_button_routes_text_through_real_handler(monkeypatch) -> None:
    app = _qapp()

    class _StatusDot(QLabel):
        def stop(self) -> None:
            pass

    monkeypatch.setattr(chat_dock_module, "AiStatusDot", _StatusDot)
    window = QMainWindow()
    dock = chat_dock_module.ChatDock(window)
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    try:
        dock.input_field.setText("Elementgenauer Kontrolltext")
        QTest.mouseClick(dock.btn_send, Qt.MouseButton.LeftButton)
        app.processEvents()

        chat_text = dock.chat_log.toPlainText()
        assert "▸ Du: Elementgenauer Kontrolltext" in chat_text
        assert "✖ Kein Agent konfiguriert." in chat_text
        assert dock.input_field.text() == ""
        assert dock.btn_send.isEnabled()
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
