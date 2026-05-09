"""Tests für services.project_notes_service.

Pattern: test_engine-Fixture + monkeypatch auf engine im Service-Modul
(analog test_timeline_state.py / test_timeline_snapshot_service.py).
Plan-Test (02_DATA_SERVICES.md Task 2.4) nutzt init_db + DBSession,
aber das Repo verwendet das test_engine-Fixture-Pattern aus tests/conftest.py.
"""
import datetime as _datetime
import time

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from database.models import Project, ProjectNote
from services.project_notes_service import get_notes, update_notes


def _project(test_engine, name="notes-svc"):
    with DBSession(test_engine) as s:
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


def test_update_returns_updated_at(test_engine, monkeypatch):
    """T4.2: update_notes liefert datetime zurück; matcht DB-Zeile."""
    _patch_engine(monkeypatch, test_engine)
    pid = _project(test_engine, "notes-svc-4")
    ts = update_notes(pid, "hello")
    assert isinstance(ts, _datetime.datetime)
    with DBSession(test_engine) as s:
        row = s.query(ProjectNote).filter_by(project_id=pid).one()
        assert row.updated_at == ts


def test_update_idempotent_no_integrity_error(test_engine, monkeypatch):
    """T4.1: zwei sequentielle update_notes mit gleicher project_id → kein
    IntegrityError dank Upsert (vorher: TOCTOU-Race möglich).
    """
    _patch_engine(monkeypatch, test_engine)
    pid = _project(test_engine, "notes-svc-5")
    # Beide Aufrufe gehen durch — Upsert-Statement macht INSERT-OR-UPDATE atomar.
    update_notes(pid, "first")
    update_notes(pid, "second")
    update_notes(pid, "third")
    assert get_notes(pid) == "third"


# ---------------------------------------------------------------------------
# T5.1 Coverage-Sweep (E1)
# ---------------------------------------------------------------------------


def test_update_notes_fk_violation_raises(test_engine, monkeypatch):
    """Non-existing project_id → IntegrityError (FK-Constraint greift)."""
    _patch_engine(monkeypatch, test_engine)
    # FK-Enforcement in SQLite — manche Setups brauchen PRAGMA. Wir prüfen
    # entweder IntegrityError oder akzeptieren stummen INSERT, falls FK-Check
    # ausgeschaltet ist (Repo-Default: aktiv via tests/conftest).
    bogus_pid = 999_999
    with pytest.raises(IntegrityError):
        update_notes(bogus_pid, "ghost")


def test_updated_at_bumps_on_overwrite(test_engine, monkeypatch):
    """Zweiter update_notes-Call bumpt updated_at (manuell gesetzt in Service)."""
    _patch_engine(monkeypatch, test_engine)
    pid = _project(test_engine, "notes-bump")
    ts1 = update_notes(pid, "first")
    # SQLite-Auflösung kann Mikrosekunden glätten — kurz warten
    time.sleep(0.01)
    ts2 = update_notes(pid, "second")
    assert ts2 >= ts1
    # Bei zwei aufeinanderfolgenden utcnow-Calls sollte ts2 strikt > ts1 sein
    assert ts2 > ts1
    with DBSession(test_engine) as s:
        row = s.query(ProjectNote).filter_by(project_id=pid).one()
        assert row.updated_at == ts2


def test_update_with_empty_string(test_engine, monkeypatch):
    """update_notes(pid, "") — leere Strings gelten als gültiger Reset."""
    _patch_engine(monkeypatch, test_engine)
    pid = _project(test_engine, "notes-empty")
    update_notes(pid, "first")
    update_notes(pid, "")
    assert get_notes(pid) == ""


def test_unicode_markdown(test_engine, monkeypatch):
    """Unicode-Roundtrip — Markdown mit Umlauten + CJK bleibt identisch."""
    _patch_engine(monkeypatch, test_engine)
    pid = _project(test_engine, "notes-unicode")
    payload = "# Müll äöü 日本"
    update_notes(pid, payload)
    assert get_notes(pid) == payload
