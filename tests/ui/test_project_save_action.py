"""B-459: Existing projects need a visible Save action."""
from __future__ import annotations

import inspect
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock


def test_b459_project_management_exposes_save_project() -> None:
    from ui.controllers.project_management import ProjectManagementController

    assert hasattr(ProjectManagementController, "_save_project")


def test_b459_tools_menu_has_save_before_save_as() -> None:
    from ui.controllers.workspace_setup import WorkspaceSetupController

    source = inspect.getsource(WorkspaceSetupController._build_top_bar)
    save_idx = source.find('tools.addAction("Speichern", self.window.project_management._save_project)')
    save_as_idx = source.find('tools.addAction("Speichern unter", self.window.project_management._save_project_as)')

    assert save_idx != -1
    assert save_as_idx != -1
    assert save_idx < save_as_idx


def test_b528_ctrl_s_shortcut_wired_to_save_project() -> None:
    """B-528: Strg+S muss window-weit an _save_project gebunden sein (vorher nur
    Menue-Eintrag ohne Shortcut -> Strg+S speicherte nicht)."""
    from ui.controllers.workspace_setup import WorkspaceSetupController

    source = inspect.getsource(WorkspaceSetupController._create_workspaces)
    assert "QKeySequence.StandardKey.Save" in source, (
        "B-528: kein Save-Shortcut (Strg+S) registriert"
    )
    save_idx = source.find("QKeySequence.StandardKey.Save")
    # Der Save-Shortcut-Block muss _save_project verdrahten und am Fenster
    # registriert sein (addAction), damit Strg+S app-weit greift.
    tail = source[save_idx:save_idx + 400]
    assert "project_management._save_project" in tail
    assert "self.window.addAction(save_action)" in tail


def test_b459_save_project_marks_existing_dirty_project_clean() -> None:
    from ui.controllers.project_management import ProjectManagementController

    ctrl = ProjectManagementController.__new__(ProjectManagementController)
    ctrl.window = SimpleNamespace(
        _dirty=True,
        _project_manager=SimpleNamespace(current_project_path=Path("C:/Project")),
        _save_window_state=MagicMock(),
        panel_setup=SimpleNamespace(_console_append=MagicMock()),
        status_bar=SimpleNamespace(showMessage=MagicMock()),
    )
    ctrl._mark_clean = MagicMock()

    ctrl._save_project()

    ctrl.window._save_window_state.assert_called_once()
    ctrl._mark_clean.assert_called_once()
    ctrl.window.panel_setup._console_append.assert_called_once()
    ctrl.window.status_bar.showMessage.assert_called_once()
