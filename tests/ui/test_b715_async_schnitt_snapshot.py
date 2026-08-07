"""B-715 — SCHNITT-Projektwechsel liest DB-Zustand ausschliesslich im Worker."""

from __future__ import annotations

from types import SimpleNamespace


class _Logger:
    def debug(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass


class _Timer:
    def __init__(self):
        self.stopped = 0

    def stop(self):
        self.stopped += 1


class _TextEdit:
    def __init__(self):
        self.blocks = []
        self.text = None

    def blockSignals(self, value):
        self.blocks.append(value)

    def setPlainText(self, value):
        self.text = value


class _Label:
    def __init__(self):
        self.text = None

    def setText(self, value):
        self.text = value


class _Notes:
    def __init__(self):
        self._autosave_timer = _Timer()
        self.notes_edit = _TextEdit()
        self.saved_label = _Label()

    def set_active_project(self, _project_id):
        raise AssertionError("B-715 darf den DB-lesenden Notes-Setter nicht aufrufen")


class _CutList:
    def __init__(self):
        self.rendered = None

    def set_project(self, _project_id):
        raise AssertionError("B-715 darf den DB-lesenden Cut-List-Setter nicht aufrufen")

    def _render_empty(self, message):
        self.rendered = ("empty", message)

    def _render_cuts(self, cuts):
        self.rendered = ("cuts", cuts)


class _Workspace:
    def __init__(self):
        self.applied = []
        self.notes = _Notes()
        self.cut_list = _CutList()
        self.editor_view = SimpleNamespace(
            tab_rl_notes=self.notes,
            tab_schnitt=SimpleNamespace(cut_list_panel=self.cut_list),
        )

    def apply_project_snapshot(self, project_id, timeline_entry_count):
        self.applied.append((project_id, timeline_entry_count))

    def set_active_project(self, _project_id):
        raise AssertionError("B-715 darf den synchronen Workspace-Setter nicht aufrufen")


class _Binder:
    def __init__(self):
        self.db_engine = object()
        self.contexts = []

    def apply_context(self, context):
        self.contexts.append(context)

    def refresh(self, _project_id):
        raise AssertionError("B-715 darf Binder.refresh nicht im GUI-Thread aufrufen")


class _Combo:
    def __init__(self):
        self.blocks = []
        self.index = None

    def blockSignals(self, value):
        self.blocks.append(value)

    def setCurrentIndex(self, value):
        self.index = value


def test_b715_snapshot_reader_collects_all_project_change_values(monkeypatch):
    import database
    import services.project_notes_service as notes_service
    import services.schnitt_context as context_service
    import services.timeline_service as timeline_service
    from ui.controllers.workspace_setup import _build_schnitt_project_snapshot

    context = SimpleNamespace(timeline_entry_count=4)
    project = SimpleNamespace(transition_type="cut")

    class _Session:
        def get(self, model, project_id):
            assert model is database.Project
            assert project_id == 23
            return project

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(database, "get_active_project_id", lambda: 23)
    monkeypatch.setattr(database, "nullpool_session", lambda: _Session())
    monkeypatch.setattr(context_service, "build_schnitt_context", lambda engine, pid: context)
    monkeypatch.setattr(notes_service, "get_notes", lambda pid: "Worker-Notiz")
    monkeypatch.setattr(timeline_service, "get_cut_list", lambda pid: [{"index": 1}])

    snapshot = _build_schnitt_project_snapshot(object())

    assert snapshot.project_id == 23
    assert snapshot.timeline_entry_count == 4
    assert snapshot.notes == "Worker-Notiz"
    assert snapshot.gate_context is context
    assert snapshot.transition_type == "cut"
    assert snapshot.cut_list == ({"index": 1},)


def test_b715_apply_snapshot_only_mutates_ui():
    from ui.controllers.workspace_setup import (
        WorkspaceSetupController,
        _SchnittProjectSnapshot,
    )

    workspace = _Workspace()
    binder = _Binder()
    combo = _Combo()
    window = SimpleNamespace(
        logger=_Logger(),
        _schnitt_ws=workspace,
        _schnitt_action_binder=binder,
        transition_combo=combo,
    )
    snapshot = _SchnittProjectSnapshot(
        project_id=23,
        timeline_entry_count=4,
        notes="Worker-Notiz",
        gate_context="gate-context",
        transition_type="cut",
        cut_list=({"index": 1},),
    )

    WorkspaceSetupController(window)._apply_schnitt_project_snapshot(snapshot)

    assert workspace.applied == [(23, 4)]
    assert workspace.notes._project_id == 23
    assert workspace.notes._autosave_timer.stopped == 1
    assert workspace.notes.notes_edit.text == "Worker-Notiz"
    assert workspace.cut_list._project_id == 23
    assert workspace.cut_list.rendered == ("cuts", [{"index": 1}])
    assert binder.contexts == ["gate-context"]
    assert combo.index == 1


def test_b715_no_project_snapshot_blocks_stale_schnitt_actions():
    from ui.controllers.workspace_setup import WorkspaceSetupController

    workspace = _Workspace()
    binder = _Binder()
    window = SimpleNamespace(
        logger=_Logger(),
        _project_manager=SimpleNamespace(current_project_path=None),
        _schnitt_ws=workspace,
        _schnitt_action_binder=binder,
        transition_combo=_Combo(),
    )

    WorkspaceSetupController(window)._push_active_project_to_schnitt()

    assert workspace.applied == [(None, 0)]
    assert binder.contexts[0].missing_reasons == ("Projekt fehlt",)
