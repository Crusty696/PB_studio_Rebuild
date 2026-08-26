from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget

from ui.controllers.workspace_setup import WorkspaceSetupController


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _noop_namespace(*names: str) -> SimpleNamespace:
    return SimpleNamespace(**{name: (lambda: None) for name in names})


def test_tools_button_mouse_click_opens_bound_product_menu() -> None:
    app = _qapp()
    host = QMainWindow()
    central = QWidget(host)
    layout = QVBoxLayout(central)
    host.setCentralWidget(central)
    host.project_management = _noop_namespace(
        "_show_settings",
        "_new_project",
        "_open_project",
        "_save_project",
        "_save_project_as",
        "_show_shortcut_help",
        "_show_about",
    )
    host.import_media = _noop_namespace(
        "_import_video", "_import_audio", "_import_folder"
    )
    host.audio_analysis = _noop_namespace("_analyze_audio_v2")
    host._open_studio_brain = lambda: None
    controller = WorkspaceSetupController(host)
    controller._build_top_bar(layout, "test")

    tools_buttons = [
        button
        for button in host.findChildren(QPushButton)
        if button.text() == "Tools"
    ]
    assert len(tools_buttons) == 1
    tools_button = tools_buttons[0]
    tools_menu = tools_button.menu()
    assert tools_menu is not None
    assert host._btn_recent is tools_button
    assert [action.text() for action in tools_menu.actions()[:3]] == [
        "Tasks anzeigen",
        "Log anzeigen",
        "KI Chat anzeigen",
    ]

    try:
        host.show()
        app.processEvents()
        assert tools_button.isVisible() is True
        assert tools_button.isEnabled() is True
        assert tools_menu.isVisible() is False

        QTest.mouseClick(tools_button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert tools_menu.isVisible() is True
    finally:
        tools_menu.hide()
        host.close()
        host.deleteLater()
        app.processEvents()
