from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMenu,
    QPushButton,
    QStatusBar,
)

from services.recent_projects import RecentProjectsManager
from ui.controllers import workspace_setup as workspace_setup_module
from ui.controllers.workspace_setup import WorkspaceSetupController


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_recent_projects_clear_action_clears_store_and_reports_success(
    monkeypatch,
    tmp_path,
) -> None:
    app = _qapp()
    host = QMainWindow()
    host._btn_recent = QPushButton("Tools", host)
    host._btn_recent.setGeometry(10, 10, 100, 22)
    host.status_bar = QStatusBar(host)
    host.setStatusBar(host.status_bar)
    controller = WorkspaceSetupController(host)
    project_dir = tmp_path / "Mein Projekt"
    project_dir.mkdir()
    cleared: list[bool] = []

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
        classmethod(lambda cls: [str(project_dir)]),
    )
    monkeypatch.setattr(
        RecentProjectsManager,
        "clear",
        classmethod(lambda cls: cleared.append(True)),
    )

    try:
        host.show()
        app.processEvents()
        controller._show_recent_projects_menu()

        menu = CapturingMenu.instance
        assert menu is not None
        actions = menu.actions()
        assert len(actions) == 3
        assert actions[0].text() == project_dir.name
        assert actions[1].isSeparator() is True

        clear_action = actions[2]
        assert clear_action.text() == "Liste leeren"
        assert clear_action.isVisible() is True
        assert clear_action.isEnabled() is True
        assert clear_action.parent() is host
        assert menu.executed_at == host._btn_recent.mapToGlobal(
            host._btn_recent.rect().bottomLeft()
        )

        clear_action.trigger()
        app.processEvents()

        assert cleared == [True]
        assert host.status_bar.currentMessage() == "Letzte Projekte geleert."
    finally:
        host.close()
        host.deleteLater()
        app.processEvents()
