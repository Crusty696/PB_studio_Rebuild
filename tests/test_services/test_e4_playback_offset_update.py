from __future__ import annotations

from datetime import datetime
import inspect

from sqlalchemy import create_engine, event, update
from sqlalchemy.orm import Session

from database import Base, Project, VideoClip


def _engine_with_clips():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Project(id=1, name="E4", path="/tmp/e4"))
        session.add_all([
            VideoClip(
                id=1,
                project_id=1,
                file_path="/v/1.mp4",
                duration=10.0,
                playback_offset=0.1,
            ),
            VideoClip(
                id=2,
                project_id=1,
                file_path="/v/2.mp4",
                duration=10.0,
                playback_offset=0.2,
            ),
            VideoClip(
                id=3,
                project_id=1,
                file_path="/v/3.mp4",
                duration=10.0,
                playback_offset=0.3,
            ),
            VideoClip(
                id=4,
                project_id=1,
                file_path="/v/deleted.mp4",
                duration=10.0,
                playback_offset=0.4,
                deleted_at=datetime(2026, 1, 1),
            ),
        ])
        session.commit()
    return engine


def _offsets(engine):
    with Session(engine) as session:
        return dict(session.query(VideoClip.id, VideoClip.playback_offset))


def test_e4_update_matches_old_orm_semantics_without_video_selects():
    old_engine = _engine_with_clips()
    new_engine = _engine_with_clips()
    clip_offsets = {1: 1.25, 2: -0.5, 3: 0.0, 4: 9.9, 999: 7.7}

    with Session(old_engine) as session:
        for video_id, offset in clip_offsets.items():
            clip = session.query(VideoClip).filter(
                VideoClip.id == video_id,
                VideoClip.deleted_at.is_(None),
            ).first()
            if clip:
                clip.playback_offset = offset
        session.commit()

    statements: list[str] = []

    def _before(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(new_engine, "before_cursor_execute", _before)
    try:
        with Session(new_engine) as session:
            for video_id, offset in clip_offsets.items():
                session.execute(
                    update(VideoClip)
                    .where(
                        VideoClip.id == video_id,
                        VideoClip.deleted_at.is_(None),
                    )
                    .values(playback_offset=offset)
                )
            session.commit()
    finally:
        event.remove(new_engine, "before_cursor_execute", _before)

    assert _offsets(new_engine) == _offsets(old_engine) == {
        1: 1.25,
        2: -0.5,
        3: 0.0,
        4: 0.4,
    }
    video_selects = [
        statement for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
        and "video_clips" in statement
    ]
    video_updates = [
        statement for statement in statements
        if statement.lstrip().upper().startswith("UPDATE")
        and "video_clips" in statement
    ]
    assert video_selects == []
    assert len(video_updates) == len(clip_offsets)


def test_e4_phase3_source_uses_filtered_update_not_full_orm_load():
    from services.pacing_service import _auto_edit_phase3_inner

    source = inspect.getsource(_auto_edit_phase3_inner)
    block = source.split("# F-001 Fix: Save playback_offset", 1)[1]
    block = block.split("_degraded =", 1)[0]
    assert "session.execute(" in block
    assert "_sa_update(VideoClip)" in block
    assert "VideoClip.deleted_at.is_(None)" in block
    assert "session.query(VideoClip)" not in block
