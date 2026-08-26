from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication, QMessageBox


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_window_save_action_uses_standard_shortcut_and_project_handler(
    monkeypatch,
) -> None:
    app = _qapp()
    from ui.controllers.panel_setup import PanelSetupController
    from ui.controllers.project_management import ProjectManagementController

    save_calls: list[ProjectManagementController] = []
    monkeypatch.setattr(PanelSetupController, "setup_chat_dock", lambda self: None)
    monkeypatch.setattr(
        ProjectManagementController,
        "_save_project",
        lambda self: save_calls.append(self),
    )
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *args, **kwargs: QMessageBox.StandardButton.Yes),
    )

    from main import PBWindow

    window = PBWindow()
    try:
        save_actions = [
            action for action in window.actions() if action.text() == "Speichern"
        ]
        assert len(save_actions) == 1
        save_action = save_actions[0]
        assert save_action.parent() is window
        assert save_action.isVisible() is True
        assert save_action.isEnabled() is True
        assert save_action.shortcut() == QKeySequence(QKeySequence.StandardKey.Save)

        save_action.trigger()
        app.processEvents()

        assert save_calls == [window.project_management]
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
