"""SCHNITT-Redesign Task 1.2: TimelineSnapshot-Tabelle.

Verifiziert dass die ``timeline_snapshots``-Tabelle existiert und ein
echter Round-Trip (INSERT + SELECT) funktioniert. Nutzt die conftest-
Fixture ``test_engine`` (In-Memory SQLite) statt der Live-DB.
"""
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from database.models import Project, TimelineSnapshot


def test_timeline_snapshot_table_exists(test_engine):
    tables = inspect(test_engine).get_table_names()
    assert "timeline_snapshots" in tables


def test_timeline_snapshot_create_and_load(test_engine):
    with Session(test_engine) as s:
        p = Project(name="snap-test", path="/tmp/snap-test")
        s.add(p)
        s.flush()
        snap = TimelineSnapshot(
            project_id=p.id,
            version=1,
            label="initial",
            payload_json='{"clips":[]}',
        )
        s.add(snap)
        s.commit()
        loaded = s.query(TimelineSnapshot).filter_by(project_id=p.id).one()
        assert loaded.version == 1
        assert loaded.label == "initial"
        assert loaded.payload_json == '{"clips":[]}'
        assert loaded.created_at is not None


def test_timeline_snapshot_cascade_on_project_delete(test_engine):
    """Soft-Delete-Architektur kennt PB Studio, aber FK ON DELETE CASCADE
    greift bei einem harten DELETE — der Index muss konsistent bleiben.
    """
    with Session(test_engine) as s:
        p = Project(name="cascade-snap", path="/tmp/cascade-snap")
        s.add(p)
        s.flush()
        s.add(TimelineSnapshot(
            project_id=p.id, version=1, label="v1", payload_json="{}"
        ))
        s.add(TimelineSnapshot(
            project_id=p.id, version=2, label="v2", payload_json="{}"
        ))
        s.commit()
        assert s.query(TimelineSnapshot).count() == 2
        s.delete(p)
        s.commit()
        assert s.query(TimelineSnapshot).count() == 0
