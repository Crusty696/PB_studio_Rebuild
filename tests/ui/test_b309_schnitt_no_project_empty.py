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


def test_b309_schnitt_push_uses_no_project_state_before_db_fallback(monkeypatch):
    import database
    from ui.controllers.workspace_setup import WorkspaceSetupController

    def _must_not_be_called():
        raise AssertionError("DB fallback darf ohne ProjectManager-Projekt nicht laufen")

    monkeypatch.setattr(database, "get_active_project_id", _must_not_be_called)

    ctrl = _Ctrl()
    notes = _Notes()
    ws = SimpleNamespace(editor_view=SimpleNamespace(tab_rl_notes=notes))
    window = SimpleNamespace(
        logger=_Logger(),
        _project_manager=SimpleNamespace(current_project_path=None),
        _schnitt_ws=ws,
        _schnitt_ctrl=ctrl,
    )

    WorkspaceSetupController(window)._push_active_project_to_schnitt()

    assert ctrl.pid is None
    assert notes.pid is None
