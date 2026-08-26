from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QKeySequence, QUndoCommand
from PySide6.QtWidgets import QApplication, QMessageBox


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_window_undo_action_uses_standard_shortcut_and_timeline_stack(
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
        undo_actions = [action for action in window.actions() if action.text() == "Undo"]
        assert len(undo_actions) == 1
        undo_action = undo_actions[0]
        assert undo_action.parent() is window
        assert undo_action.isVisible() is True
        assert undo_action.isEnabled() is True
        assert undo_action.shortcut() == QKeySequence(QKeySequence.StandardKey.Undo)

        stack.clear()
        stack.push(MarkerCommand())
        assert state["value"] == 1
        assert stack.canUndo() is True

        undo_action.trigger()
        app.processEvents()

        assert state["value"] == 0
        assert stack.canRedo() is True
    finally:
        stack.clear()
        window.close()
        window.deleteLater()
        app.processEvents()
