"""SCHNITT-Redesign Task 1.1: TimelineEntry.locked column.

Verifiziert dass das ``locked``-Flag auf ``timeline_entries`` existiert
und per Default ``False`` ist. Nutzt die konfto-Fixture ``test_engine``
(In-Memory SQLite) statt der Live-DB.
"""
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from database.models import Project, TimelineEntry


def test_timeline_entry_has_locked_column(test_engine):
    cols = {c["name"] for c in inspect(test_engine).get_columns("timeline_entries")}
    assert "locked" in cols


def test_timeline_entry_locked_defaults_false(test_engine):
    with Session(test_engine) as s:
        p = Project(name="locked-default-test", path="/tmp/locked-test")
        s.add(p)
        s.flush()
        e = TimelineEntry(
            project_id=p.id,
            track="video",
            media_id=1,
            start_time=0.0,
        )
        s.add(e)
        s.commit()
        s.refresh(e)
        assert e.locked is False
