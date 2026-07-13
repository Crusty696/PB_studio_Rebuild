from __future__ import annotations

from contextlib import contextmanager
import inspect
from types import SimpleNamespace

from sqlalchemy import event
from sqlalchemy.orm import Session

import database
from database import Project, TimelineEntry
from ui.timeline import ClipRecord, InteractiveTimeline, PIXELS_PER_SECOND


def test_e7_anchor_sync_bulk_persists_identical_times_with_one_query(
    qapp, test_engine, monkeypatch
):
    with Session(test_engine) as session:
        project = Project(name="E7", path="/tmp/e7")
        session.add(project)
        session.flush()
        entries = [
            TimelineEntry(
                project_id=project.id,
                track="video",
                media_id=11,
                start_time=20.0,
                end_time=25.0,
                source_start=0.0,
                source_end=5.0,
                lane=0,
            ),
            TimelineEntry(
                project_id=project.id,
                track="video",
                media_id=22,
                start_time=30.0,
                end_time=38.0,
                source_start=0.0,
                source_end=8.0,
                lane=1,
            ),
        ]
        session.add_all(entries)
        session.commit()
        entry_ids = [entry.id for entry in entries]

    @contextmanager
    def _session():
        with Session(test_engine) as session:
            yield session

    monkeypatch.setattr(database, "nullpool_session", _session)
    timeline = InteractiveTimeline()
    timeline.clip_records = [
        ClipRecord(
            entry_id=1000,
            media_id=1,
            track_type="audio",
            title="Audio",
            x=0.0,
            y=0.0,
            width=100.0,
            height=40.0,
        ),
        ClipRecord(
            entry_id=entry_ids[0],
            media_id=11,
            track_type="video",
            title="V1",
            x=20.0 * PIXELS_PER_SECOND,
            y=50.0,
            width=100.0,
            height=40.0,
        ),
        ClipRecord(
            entry_id=entry_ids[1],
            media_id=22,
            track_type="video",
            title="V2",
            x=30.0 * PIXELS_PER_SECOND,
            y=50.0,
            width=100.0,
            height=40.0,
        ),
        ClipRecord(
            entry_id=999999,
            media_id=33,
            track_type="video",
            title="Missing",
            x=40.0 * PIXELS_PER_SECOND,
            y=50.0,
            width=100.0,
            height=40.0,
        ),
    ]
    timeline._anchor_map = {
        1000: [SimpleNamespace(time_offset=10.0)],
        entry_ids[0]: [SimpleNamespace(time_offset=2.0)],
        entry_ids[1]: [SimpleNamespace(time_offset=3.0)],
        999999: [SimpleNamespace(time_offset=4.0)],
    }

    statements: list[str] = []

    def _before(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(test_engine, "before_cursor_execute", _before)
    try:
        assert timeline.sync_anchors() is True
    finally:
        event.remove(test_engine, "before_cursor_execute", _before)
        timeline.deleteLater()

    entry_selects = [
        statement for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
        and "FROM timeline_entries" in statement
    ]
    assert len(entry_selects) == 1, entry_selects

    with Session(test_engine) as session:
        persisted = {
            entry.id: (entry.start_time, entry.end_time)
            for entry in session.query(TimelineEntry).filter(
                TimelineEntry.id.in_(entry_ids)
            )
        }
    assert persisted == {
        entry_ids[0]: (8.0, 13.0),
        entry_ids[1]: (7.0, 15.0),
    }


def test_e7_sync_source_uses_lazy_bulk_load_not_session_get():
    source = inspect.getsource(InteractiveTimeline.sync_anchors)
    assert "session.get(TimelineEntry" not in source
    assert "TimelineEntry.id.in_(_ids)" in source
    assert 'lazyload("*")' in source
