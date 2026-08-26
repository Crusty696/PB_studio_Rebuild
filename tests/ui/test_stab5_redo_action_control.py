from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QKeySequence, QUndoCommand
from PySide6.QtWidgets import QApplication, QMessageBox


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_window_redo_action_uses_standard_shortcut_and_timeline_stack(
    monkeypatch,
) -> None:
    app = _qapp()
    from ui.controllers.panel_setup import PanelSetupController

    monkeypatch.setattr(PanelSetupController, "setup_chat_dock", lambda self: None)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes),
    )

    from main import PBWindow

    window = PBWindow()
    stack = window.timeline_view.undo_stack
    state = {"value": 0}

    class MarkerCommand(QUndoCommand):
        def redo(self) -> None:
            state["value"] += 1

        def undo(self) -> None:
            state["value"] -= 1

    try:
        redo_actions = [action for action in window.actions() if action.text() == "Redo"]
        assert len(redo_actions) == 1
        redo_action = redo_actions[0]
        assert redo_action.parent() is window
        assert redo_action.isVisible() is True
        assert redo_action.isEnabled() is True
        assert redo_action.shortcut() == QKeySequence(QKeySequence.StandardKey.Redo)

        stack.clear()
        stack.push(MarkerCommand())
        stack.undo()
        assert state["value"] == 0
        assert stack.canRedo() is True

        redo_action.trigger()
        app.processEvents()

        assert state["value"] == 1
        assert stack.canUndo() is True
    finally:
        stack.clear()
        window.close()
        window.deleteLater()
        app.processEvents()
