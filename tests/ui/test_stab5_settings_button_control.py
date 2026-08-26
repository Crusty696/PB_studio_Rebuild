from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.controllers.project_management import ProjectManagementController
from ui.controllers.workspace_setup import WorkspaceSetupController


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _noop_namespace(*names: str) -> SimpleNamespace:
    return SimpleNamespace(**{name: (lambda: None) for name in names})


class _Signal:
    def __init__(self) -> None:
        self.connected: list[object] = []

    def connect(self, slot: object) -> None:
        self.connected.append(slot)


class _SettingsDialog:
    instances: list[_SettingsDialog] = []

    def __init__(self, parent) -> None:
        self.parent = parent
        self.ollama_settings_changed = _Signal()
        self.exec_calls = 0
        self.delete_calls = 0
        self.instances.append(self)

    def exec(self) -> None:
        self.exec_calls += 1

    def deleteLater(self) -> None:
        self.delete_calls += 1


def test_settings_button_click_runs_real_dialog_handler_twice(monkeypatch) -> None:
    app = _qapp()
    _SettingsDialog.instances.clear()
    monkeypatch.setattr(
        "ui.dialogs.settings_dialog.SettingsDialog", _SettingsDialog
    )
    host = QMainWindow()
    central = QWidget(host)
    layout = QVBoxLayout(central)
    host.setCentralWidget(central)
    host.project_management = ProjectManagementController(host)
    host.import_media = _noop_namespace(
        "_import_video", "_import_audio", "_import_folder"
    )
    host.audio_analysis = _noop_namespace("_analyze_audio_v2")
    host._open_studio_brain = lambda: None
    controller = WorkspaceSetupController(host)
    controller._build_top_bar(layout, "test")
    settings_buttons = [
        button
        for button in host.findChildren(QPushButton)
        if button.text() == "Einstellungen"
    ]
    assert len(settings_buttons) == 1
    settings_button = settings_buttons[0]

    try:
        host.show()
        app.processEvents()
        assert settings_button.isVisible() is True

        QTest.mouseClick(settings_button, Qt.MouseButton.LeftButton)
        QTest.mouseClick(settings_button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(_SettingsDialog.instances) == 2
        for dialog in _SettingsDialog.instances:
            assert dialog.parent is host
            assert dialog.ollama_settings_changed.connected == [
                host.project_management._apply_ollama_settings
            ]
            assert dialog.exec_calls == 1
            assert dialog.delete_calls == 1
    finally:
        host.close()
        host.deleteLater()
        app.processEvents()
