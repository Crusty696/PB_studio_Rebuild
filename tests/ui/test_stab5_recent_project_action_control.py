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


def test_recent_project_action_keeps_path_and_triggers_open(
    monkeypatch,
    tmp_path,
) -> None:
    app = _qapp()
    host = QMainWindow()
    host._btn_recent = QPushButton("Tools", host)
    host._btn_recent.setGeometry(10, 10, 100, 22)
    controller = WorkspaceSetupController(host)
    project_dir = tmp_path / "Mein Projekt"
    project_dir.mkdir()
    project_path = str(project_dir)
    opened_paths: list[str] = []
    controller._open_recent_project = opened_paths.append

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
        classmethod(lambda cls: [project_path]),
    )

    try:
        host.show()
        app.processEvents()
        controller._show_recent_projects_menu()

        menu = CapturingMenu.instance
        assert menu is not None
        project_action = menu.actions()[0]
        assert project_action.text() == project_dir.name
        assert project_action.data() == project_path
        assert project_action.isVisible() is True
        assert project_action.isEnabled() is True
        assert project_action.parent() is host
        assert menu.executed_at == host._btn_recent.mapToGlobal(
            host._btn_recent.rect().bottomLeft()
        )

        project_action.trigger()
        app.processEvents()

        assert opened_paths == [project_path]
    finally:
        host.close()
        host.deleteLater()
        app.processEvents()
