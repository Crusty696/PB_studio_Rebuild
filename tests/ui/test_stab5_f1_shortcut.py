from __future__ import annotations

import os
from pathlib import Path
from types import MethodType

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
import pytest

from ui.controllers.project_management import ProjectManagementController


REPO_ROOT = Path(__file__).resolve().parents[2]


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    ("sequence", "key", "modifiers", "source_line"),
    [
        (
            QKeySequence(Qt.Key.Key_F1),
            Qt.Key.Key_F1,
            Qt.KeyboardModifier.NoModifier,
            "QShortcut(_QKS(Qt.Key.Key_F1), self, "
            "self.project_management._show_shortcut_help)",
        ),
        (
            QKeySequence("Ctrl+?"),
            Qt.Key.Key_Question,
            Qt.KeyboardModifier.ControlModifier,
            'QShortcut(_QKS("Ctrl+?"), self, '
            "self.project_management._show_shortcut_help)",
        ),
    ],
    ids=("f1", "ctrl_question"),
)
def test_help_shortcut_invokes_real_handler(
    monkeypatch, sequence, key, modifiers, source_line
) -> None:
    app = _qapp()
    source = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    assert source_line in source

    host = QWidget()
    dialog_calls: list[tuple[str, QWidget]] = []

    class _Dialog:
        def __init__(self, parent: QWidget) -> None:
            dialog_calls.append(("init", parent))

        def exec(self) -> None:
            dialog_calls.append(("exec", host))

    monkeypatch.setattr(
        "ui.dialogs.shortcut_help_dialog.ShortcutHelpDialog", _Dialog
    )
    class _Controller:
        pass

    controller = _Controller()
    controller.window = host
    controller._show_shortcut_help = MethodType(
        ProjectManagementController._show_shortcut_help, controller
    )
    shortcut = QShortcut(sequence, host, controller._show_shortcut_help)

    host.show()
    host.activateWindow()
    host.setFocus()
    app.processEvents()
    QTest.keyClick(host, key, modifiers)
    app.processEvents()

    assert shortcut.parent() is host
    assert dialog_calls == [("init", host), ("exec", host)]
