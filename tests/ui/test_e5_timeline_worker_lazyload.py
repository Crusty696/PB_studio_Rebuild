from __future__ import annotations

import inspect

from sqlalchemy import event
from sqlalchemy.orm import Session, lazyload

from database import ClipAnchor, Project, TimelineEntry


def _seed(test_engine) -> int:
    with Session(test_engine) as session:
        project = Project(name="E5", path="/tmp/e5")
        session.add(project)
        session.flush()
        entries = [
            TimelineEntry(
                project_id=project.id,
                track="video",
                media_id=11,
                start_time=0.0,
                end_time=5.0,
                source_start=0.0,
                source_end=5.0,
                lane=0,
            ),
            TimelineEntry(
                project_id=project.id,
                track="audio",
                media_id=22,
                start_time=0.0,
                end_time=10.0,
                source_start=0.0,
                source_end=10.0,
                lane=1,
            ),
        ]
        session.add_all(entries)
        session.flush()
        session.add_all([
            ClipAnchor(timeline_entry_id=entries[0].id, time_offset=1.0, label="A"),
            ClipAnchor(timeline_entry_id=entries[0].id, time_offset=2.0, label="B"),
            ClipAnchor(timeline_entry_id=entries[1].id, time_offset=3.0, label="C"),
        ])
        session.commit()
        return project.id


def _load(test_engine, project_id: int, *, optimized: bool):
    statements: list[str] = []

    def _before(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(test_engine, "before_cursor_execute", _before)
    try:
        with Session(test_engine) as session:
            query = session.query(TimelineEntry)
            if optimized:
                query = query.options(lazyload("*"))
            entries = query.filter_by(project_id=project_id).all()
            entry_ids = [entry.id for entry in entries]
            anchors = session.query(ClipAnchor).filter(
                ClipAnchor.timeline_entry_id.in_(entry_ids)
            ).all()
            entry_data = [
                (
                    entry.id,
                    entry.track,
                    entry.media_id,
                    entry.start_time,
                    entry.end_time,
                    entry.lane,
                )
                for entry in entries
            ]
            anchor_map: dict[int, list[tuple[float, str | None]]] = {}
            for anchor in anchors:
                anchor_map.setdefault(anchor.timeline_entry_id, []).append(
                    (anchor.time_offset, anchor.label)
                )
        return entry_data, anchor_map, statements
    finally:
        event.remove(test_engine, "before_cursor_execute", _before)


def test_e5_timeline_entry_and_anchor_parity_with_fewer_queries(test_engine):
    project_id = _seed(test_engine)

    old_entries, old_anchors, old_statements = _load(
        test_engine, project_id, optimized=False
    )
    new_entries, new_anchors, new_statements = _load(
        test_engine, project_id, optimized=True
    )

    assert new_entries == old_entries
    assert new_anchors == old_anchors
    assert len(new_entries) == 2
    assert sum(len(items) for items in new_anchors.values()) == 3
    assert len(old_statements) == 3, old_statements
    assert len(new_statements) == 2, new_statements


def test_e5_worker_entries_query_disables_mapper_eager_loads():
    from ui.timeline import InteractiveTimeline

    source = inspect.getsource(InteractiveTimeline.load_from_db)
    entries_query = source.split("entries = session.query(TimelineEntry)", 1)[1]
    entries_query = entries_query.split("_audio_ids", 1)[0]
    assert 'lazyload("*")' in entries_query
