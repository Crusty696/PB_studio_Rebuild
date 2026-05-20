from __future__ import annotations

import inspect


def test_project_change_does_not_refresh_director_combos_synchronously() -> None:
    from ui.controllers.project_management import ProjectManagementController

    source = inspect.getsource(ProjectManagementController._on_project_changed)

    assert "_refresh_media_table" in source
    assert "_refresh_director_combos" not in source


def test_schnitt_project_push_does_not_refresh_director_combos_synchronously() -> None:
    from ui.controllers.workspace_setup import WorkspaceSetupController

    source = inspect.getsource(WorkspaceSetupController._push_active_project_to_schnitt)

    assert "_refresh_director_combos" not in source
