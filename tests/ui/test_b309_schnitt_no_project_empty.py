"""B-309: SCHNITT darf ohne geoeffnetes Projekt keine Editor-Shell zeigen."""

from __future__ import annotations

from types import SimpleNamespace


class _Logger:
    def debug(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


class _Ctrl:
    def __init__(self):
        self.pid = "unset"

    def set_active_project_protected(self, pid):
        self.pid = pid


class _Notes:
    def __init__(self):
        self.pid = "unset"

    def set_active_project(self, pid):
        self.pid = pid


class _CutList:
    def __init__(self):
        self.pid = "unset"
        self.calls = []

    def set_project(self, pid):
        self.pid = pid
        self.calls.append(pid)


class _Stack:
    def __init__(self):
        self.indices = []

    def setCurrentIndex(self, index):
        self.indices.append(index)


class _SchnittWs:
    def __init__(self, notes, cut_list):
        self.refreshes = 0
        self.editor_view = SimpleNamespace(
            tab_rl_notes=notes,
            tab_schnitt=SimpleNamespace(cut_list_panel=cut_list),
        )

    def refresh_state_from_db(self):
        self.refreshes += 1


class _MediaTableController:
    def __init__(self):
        self.combo_refreshes = []

    def _refresh_director_combos(self, *args, **kwargs):
        self.combo_refreshes.append((args, kwargs))


class _Binder:
    def __init__(self):
        self.refresh_calls = []

    def refresh(self, project_id):
        self.refresh_calls.append(project_id)

    def refresh_current_project(self):
        raise AssertionError("Kein Projekt darf keinen aktiven DB-Fallback lesen")


class _Dashboard:
    def __init__(self):
        self.updated = []
        self.refreshed = []

    def update_project(self, name, path, project_id=None):
        self.updated.append((name, path, project_id))

    def refresh(self, project_id):
        self.refreshed.append(project_id)


def test_b309_schnitt_push_uses_no_project_state_before_db_fallback(monkeypatch):
    import database
    from ui.controllers.workspace_setup import WorkspaceSetupController

    def _must_not_be_called():
        raise AssertionError("DB fallback darf ohne ProjectManager-Projekt nicht laufen")

    monkeypatch.setattr(database, "get_active_project_id", _must_not_be_called)

    ctrl = _Ctrl()
    notes = _Notes()
    cut_list = _CutList()
    tab_schnitt = SimpleNamespace(cut_list_panel=cut_list)
    ws = SimpleNamespace(
        editor_view=SimpleNamespace(tab_rl_notes=notes, tab_schnitt=tab_schnitt)
    )
    window = SimpleNamespace(
        logger=_Logger(),
        _project_manager=SimpleNamespace(current_project_path=None),
        _schnitt_ws=ws,
        _schnitt_ctrl=ctrl,
    )

    WorkspaceSetupController(window)._push_active_project_to_schnitt()

    assert ctrl.pid is None
    assert notes.pid is None
    assert cut_list.pid is None


def test_b310_schnitt_push_updates_cut_list_panel(monkeypatch):
    import database
    from ui.controllers.workspace_setup import WorkspaceSetupController

    monkeypatch.setattr(database, "get_active_project_id", lambda: 23)

    ctrl = _Ctrl()
    notes = _Notes()
    cut_list = _CutList()
    tab_schnitt = SimpleNamespace(cut_list_panel=cut_list)
    ws = SimpleNamespace(
        editor_view=SimpleNamespace(tab_rl_notes=notes, tab_schnitt=tab_schnitt)
    )
    window = SimpleNamespace(
        logger=_Logger(),
        _project_manager=SimpleNamespace(current_project_path=object()),
        _schnitt_ws=ws,
        _schnitt_ctrl=ctrl,
    )

    WorkspaceSetupController(window)._push_active_project_to_schnitt()

    assert ctrl.pid == 23
    assert notes.pid == 23
    assert cut_list.pid == 23


def test_b315_workspace_switch_to_schnitt_has_no_direct_duplicate_refresh(monkeypatch):
    import database
    from ui.controllers.workspace_setup import WorkspaceSetupController

    monkeypatch.setattr(database, "get_active_project_id", lambda: 23)

    ctrl = _Ctrl()
    notes = _Notes()
    cut_list = _CutList()
    ws = _SchnittWs(notes, cut_list)
    media_ctrl = _MediaTableController()
    window = SimpleNamespace(
        logger=_Logger(),
        _project_manager=SimpleNamespace(current_project_path=object()),
        _schnitt_ws=ws,
        _schnitt_ctrl=ctrl,
        workspace_stack=_Stack(),
        media_table_controller=media_ctrl,
    )
    controller = WorkspaceSetupController(window)
    controller._update_workflow_gates = lambda: None

    controller._on_workspace_changed(2)

    assert window.workspace_stack.indices == [2]
    assert ctrl.pid == 23
    assert notes.pid == 23
    assert cut_list.calls == [23]
    assert ws.refreshes == 0
    assert media_ctrl.combo_refreshes == [
        ((23,), {"allow_active_fallback": False})
    ]


def test_b311_dashboard_refresh_uses_no_project_state_before_db_fallback(monkeypatch):
    import database
    from ui.controllers.workspace_setup import WorkspaceSetupController

    calls = []

    def _must_not_be_called():
        calls.append(True)
        raise AssertionError("DB fallback darf ohne ProjectManager-Projekt nicht laufen")

    monkeypatch.setattr(database, "get_active_project_id", _must_not_be_called)

    dashboard = _Dashboard()
    window = SimpleNamespace(
        logger=_Logger(),
        _project_manager=SimpleNamespace(current_project_path=None),
        _project_dashboard=dashboard,
        _project_name_label=SimpleNamespace(text=lambda: "Kein Projekt"),
    )

    WorkspaceSetupController(window)._refresh_project_dashboard()

    assert dashboard.updated == [("Kein Projekt", None, None)]
    assert dashboard.refreshed == [None]
    assert calls == []


def test_b315_workflow_gates_do_not_read_active_project_without_open_project():
    from ui.controllers.workspace_setup import WorkspaceSetupController

    binder = _Binder()
    window = SimpleNamespace(
        logger=_Logger(),
        _project_manager=SimpleNamespace(current_project_path=None),
        _schnitt_action_binder=binder,
    )

    WorkspaceSetupController(window)._update_workflow_gates()

    assert binder.refresh_calls == [None]
