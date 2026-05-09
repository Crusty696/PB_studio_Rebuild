"""TimelineState Tests — SCHNITT Redesign 2026-05-09 Task 2.2."""
import pytest
from sqlalchemy.orm import Session
from database import init_db, engine
from database.models import Project, TimelineEntry
from services.timeline_state import TimelineState, ClipEntry


def _make_project_with_clips(test_engine):
    """Beachte: passt sich an die im Repo etablierte test_engine-Fixture an
    und nutzt Session statt DBSession."""
    with Session(test_engine) as s:
        p = Project(name="ts-test", path="/tmp/ts-test")
        s.add(p)
        s.flush()
        s.add(TimelineEntry(project_id=p.id, track="video", media_id=1,
                            start_time=0.0, end_time=2.0, lane=0, locked=True))
        s.add(TimelineEntry(project_id=p.id, track="video", media_id=2,
                            start_time=2.0, end_time=4.0, lane=0, locked=False))
        s.commit()
        return p.id


def test_load_returns_clips_with_lock_state(test_engine, monkeypatch):
    # TimelineState.load nutzt das modul-globale `engine` aus database/__init__.py
    # → patche es auf test_engine, analog zum Idempotenz-Test (Task 1.4).
    import services.timeline_state as ts_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)
    pid = _make_project_with_clips(test_engine)
    state = TimelineState.load(pid)
    assert state.project_id == pid
    assert len(state.clips) == 2
    locks = sorted(c.locked for c in state.clips)
    assert locks == [False, True]


def test_lock_count(test_engine, monkeypatch):
    import services.timeline_state as ts_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)
    pid = _make_project_with_clips(test_engine)
    state = TimelineState.load(pid)
    assert state.lock_count() == 1


def test_save_snapshot_returns_id_and_persists(test_engine, monkeypatch):
    import services.timeline_state as ts_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)
    pid = _make_project_with_clips(test_engine)
    state = TimelineState.load(pid)
    snap_id = state.save_snapshot(label="vor-regen")
    assert snap_id is not None
    from database.models import TimelineSnapshot
    with Session(test_engine) as s:
        snap = s.get(TimelineSnapshot, snap_id)
        assert snap.label == "vor-regen"
        assert snap.project_id == pid
        assert "media_id" in snap.payload_json
