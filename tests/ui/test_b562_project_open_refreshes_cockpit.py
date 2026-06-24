"""B-562 — Cockpit-Dashboard muss bei jedem Projektwechsel voll refreshen.

Frueher rief ``_on_project_changed`` nur ``dashboard.update_project(name, path)``
ohne project_id/Readiness. Der Cockpit-Innenstatus blieb dadurch
„Kein Projekt geladen" bis zum ersten Workspace-Wechsel zu Index 0 (der als
einziger ``_refresh_project_dashboard`` ausloeste). Nach dem Fix laeuft der volle
Refresh schon beim Projekt-Open.

Wiring-Guard im Stil von ``test_b321_project_open_avoids_sync_combo_refresh``.
Der behaviorale Live-Beweis kommt aus dem pb-gui-tester-Retest.
"""
from __future__ import annotations

import inspect


def test_on_project_changed_triggers_full_dashboard_refresh() -> None:
    from ui.controllers.project_management import ProjectManagementController

    source = inspect.getsource(ProjectManagementController._on_project_changed)

    # Voll-Refresh (Name + Pfad + project_id + Readiness) statt nur Namens-Label.
    assert "_refresh_project_dashboard" in source, (
        "B-562-Regression: _on_project_changed muss den vollen Cockpit-Refresh "
        "ausloesen, nicht nur dashboard.update_project(name, path)."
    )


def test_refresh_project_dashboard_passes_project_id() -> None:
    from ui.controllers.workspace_setup import WorkspaceSetupController

    source = inspect.getsource(WorkspaceSetupController._refresh_project_dashboard)

    # Der Refresh muss die project_id ermitteln und an Readiness durchreichen,
    # sonst zeigt get_cockpit_readiness(None) weiter „Kein Projekt geladen".
    assert "get_active_project_id" in source
    assert "dashboard.refresh(project_id)" in source
