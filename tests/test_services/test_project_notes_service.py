"""Tests für services.project_notes_service.

Pattern: test_engine-Fixture + monkeypatch auf engine im Service-Modul
(analog test_timeline_state.py / test_timeline_snapshot_service.py).
Plan-Test (02_DATA_SERVICES.md Task 2.4) nutzt init_db + DBSession,
aber das Repo verwendet das test_engine-Fixture-Pattern aus tests/conftest.py.
"""
from sqlalchemy.orm import Session

from database.models import Project
from services.project_notes_service import get_notes, update_notes


def _project(test_engine, name="notes-svc"):
    with Session(test_engine) as s:
        p = Project(name=name, path=f"/tmp/{name}")
        s.add(p)
        s.commit()
        return p.id


def _patch_engine(monkeypatch, test_engine):
    import services.project_notes_service as svc_mod
    monkeypatch.setattr(svc_mod, "engine", test_engine)


def test_get_notes_default_empty(test_engine, monkeypatch):
    _patch_engine(monkeypatch, test_engine)
    pid = _project(test_engine)
    assert get_notes(pid) == ""


def test_update_creates_row_if_missing(test_engine, monkeypatch):
    _patch_engine(monkeypatch, test_engine)
    pid = _project(test_engine, "notes-svc-2")
    update_notes(pid, "# Hello")
    assert get_notes(pid) == "# Hello"


def test_update_overwrites_existing(test_engine, monkeypatch):
    _patch_engine(monkeypatch, test_engine)
    pid = _project(test_engine, "notes-svc-3")
    update_notes(pid, "first")
    update_notes(pid, "second")
    assert get_notes(pid) == "second"
