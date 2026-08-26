from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QPushButton

from services.recent_projects import RecentProjectsManager
from ui.controllers import workspace_setup as workspace_setup_module
from ui.controllers.workspace_setup import WorkspaceSetupController


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_recent_projects_empty_state_is_visible_disabled_action(
    monkeypatch,
) -> None:
    app = _qapp()
    host = QMainWindow()
    host._btn_recent = QPushButton("Tools", host)
    host._btn_recent.setGeometry(10, 10, 100, 22)
    controller = WorkspaceSetupController(host)

    class CapturingMenu(QMenu):
        instance: "CapturingMenu | None" = None

        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self.executed_at: QPoint | None = None
            CapturingMenu.instance = self

        def exec(self, pos: QPoint):
            self.executed_at = pos
            return None

    monkeypatch.setattr(workspace_setup_module, "QMenu", CapturingMenu)
    monkeypatch.setattr(
        RecentProjectsManager,
        "get_all",
        classmethod(lambda cls: []),
    )

    try:
        host.show()
        app.processEvents()
        controller._show_recent_projects_menu()

        menu = CapturingMenu.instance
        assert menu is not None
        actions = menu.actions()
        assert len(actions) == 1
        empty_action = actions[0]
        assert empty_action.text() == "(Keine letzten Projekte)"
        assert empty_action.isVisible() is True
        assert empty_action.isEnabled() is False
        assert empty_action.parent() is host
        assert menu.executed_at == host._btn_recent.mapToGlobal(
            host._btn_recent.rect().bottomLeft()
        )
    finally:
        host.close()
        host.deleteLater()
        app.processEvents()
