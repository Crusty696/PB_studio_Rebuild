"""SchnittWorkspace State-Manager-Tests (Phase 04 / Task 4.3).

Plan-Abweichung: nutzt `test_engine`-Fixture aus tests/conftest.py + Session
statt `init_db() + DBSession(engine)` (vgl. Phase 02/03).
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from sqlalchemy.orm import Session
from database.models import Project, TimelineEntry


def _qapp():
    return QApplication.instance() or QApplication([])


def _project(test_engine, with_clip: bool) -> int:
    with Session(test_engine) as s:
        p = Project(name="schnitt-state", path="/tmp/schnitt-state")
        s.add(p)
        s.flush()
        if with_clip:
            s.add(TimelineEntry(
                project_id=p.id, track="video", media_id=1,
                start_time=0, end_time=2, lane=0,
            ))
        s.commit()
        return p.id


def _patch_workspace_engine(monkeypatch, test_engine):
    import ui.workspaces.schnitt_workspace as ws_mod
    monkeypatch.setattr(ws_mod, "engine", test_engine)


def test_initial_no_project_shows_empty(test_engine, monkeypatch):
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_EMPTY
    ws = SchnittWorkspace()
    ws.set_active_project(None)
    assert ws.current_state() == STATE_EMPTY


def test_project_with_no_clips_shows_empty(test_engine, monkeypatch):
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_EMPTY
    ws = SchnittWorkspace()
    pid = _project(test_engine, with_clip=False)
    ws.set_active_project(pid)
    assert ws.current_state() == STATE_EMPTY


def test_project_with_clips_shows_editor(test_engine, monkeypatch):
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_EDITOR
    ws = SchnittWorkspace()
    pid = _project(test_engine, with_clip=True)
    ws.set_active_project(pid)
    assert ws.current_state() == STATE_EDITOR


def test_show_loading_then_editor(test_engine, monkeypatch):
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import (
        SchnittWorkspace, STATE_LOADING, STATE_EDITOR,
    )
    ws = SchnittWorkspace()
    pid = _project(test_engine, with_clip=False)
    ws.set_active_project(pid)
    ws.enter_loading()
    assert ws.current_state() == STATE_LOADING
    # Simuliere Worker-Done
    pid2 = _project(test_engine, with_clip=True)
    ws.set_active_project(pid2)
    ws.refresh_state_from_db()
    assert ws.current_state() == STATE_EDITOR
