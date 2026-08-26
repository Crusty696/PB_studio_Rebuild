from __future__ import annotations

import os
from pathlib import Path
from types import MethodType

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from main import PBWindow


REPO_ROOT = Path(__file__).resolve().parents[2]


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


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
        self._steer_tab = type("_Steer", (), {"runRequested": _Signal()})()
        self.calls: list[str] = []

    def show(self) -> None:
        self.calls.append("show")

    def raise_(self) -> None:
        self.calls.append("raise")

    def activateWindow(self) -> None:
        self.calls.append("activate")


def test_ctrl_b_invokes_real_studio_brain_handler_twice(monkeypatch) -> None:
    app = _qapp()
    source = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    assert 'QShortcut(_QKS("Ctrl+B"), self, self._open_studio_brain)' in source

    host = QWidget()
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

    host._on_brain_timeline_nav = MethodType(lambda self, value: None, host)
    host._on_brain_run_requested = MethodType(lambda self, value: None, host)
    handler = MethodType(PBWindow._open_studio_brain, host)
    shortcut = QShortcut(QKeySequence("Ctrl+B"), host, handler)

    host.show()
    host.activateWindow()
    host.setFocus()
    app.processEvents()
    QTest.keyClick(
        host, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier
    )
    QTest.keyClick(
        host, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier
    )
    app.processEvents()

    assert shortcut.parent() is host
    assert instance_calls == ["instance", "instance"]
    assert brain.calls == [
        "show", "raise", "activate",
        "show", "raise", "activate",
    ]
    assert brain.timelineNavigationRequested.connected == [
        host._on_brain_timeline_nav
    ]
    assert brain._steer_tab.runRequested.connected == [
        host._on_brain_run_requested
    ]
