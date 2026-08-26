from __future__ import annotations

import os
from types import MethodType, SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

from main import PBWindow
from ui.controllers.workspace_setup import WorkspaceSetupController


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _noop_namespace(*names: str) -> SimpleNamespace:
    return SimpleNamespace(**{name: (lambda: None) for name in names})


class _Signal:
    def __init__(self) -> None:
        self.connected: list[object] = []

    def disconnect(self, slot: object) -> None:
        try:
            self.connected.remove(slot)
        except ValueError as exc:
            raise TypeError("slot is not connected") from exc

    def connect(self, slot: object) -> None:
        self.connected.append(slot)


class _BrainWindow:
    def __init__(self) -> None:
        self.timelineNavigationRequested = _Signal()
        self._steer_tab = SimpleNamespace(runRequested=_Signal())
        self.calls: list[str] = []

    def show(self) -> None:
        self.calls.append("show")

    def raise_(self) -> None:
        self.calls.append("raise")

    def activateWindow(self) -> None:
        self.calls.append("activate")


def test_brain_button_click_invokes_real_singleton_handler_twice(monkeypatch) -> None:
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
    host._on_brain_timeline_nav = MethodType(lambda self, value: None, host)
    host._on_brain_run_requested = MethodType(lambda self, value: None, host)
    host._open_studio_brain = MethodType(PBWindow._open_studio_brain, host)

    brain = _BrainWindow()
    instance_calls: list[str] = []

    class _StudioBrainWindow:
        @classmethod
        def instance(cls) -> _BrainWindow:
            instance_calls.append("instance")
            return brain

    monkeypatch.setattr(
        "ui.studio_brain_window.StudioBrainWindow", _StudioBrainWindow
    )
    controller = WorkspaceSetupController(host)
    controller._build_top_bar(layout, "test")

    try:
        host.show()
        app.processEvents()
        assert host._btn_open_brain.text() == "Brain"
        assert host._btn_open_brain.isVisible() is True

        QTest.mouseClick(host._btn_open_brain, Qt.MouseButton.LeftButton)
        QTest.mouseClick(host._btn_open_brain, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert instance_calls == ["instance", "instance"]
        assert brain.calls == [
            "show",
            "raise",
            "activate",
            "show",
            "raise",
            "activate",
        ]
        assert brain.timelineNavigationRequested.connected == [
            host._on_brain_timeline_nav
        ]
        assert brain._steer_tab.runRequested.connected == [
            host._on_brain_run_requested
        ]
    finally:
        host.close()
        host.deleteLater()
        app.processEvents()
