from __future__ import annotations

from sqlalchemy import event


def test_b315_get_cut_list_bulk_loads_video_titles(test_engine, db_session, project):
    import database
    from services.timeline_service import get_cut_list

    project_id = project.id
    for idx in range(5):
        clip = database.VideoClip(
            project_id=project_id,
            file_path=f"/tmp/clip_{idx}.mp4",
            duration=1.0,
        )
        db_session.add(clip)
        db_session.flush()
        db_session.add(
            database.TimelineEntry(
                project_id=project_id,
                track="video",
                media_id=clip.id,
                start_time=float(idx),
                end_time=float(idx + 1),
            )
        )
    db_session.commit()

    select_count = 0

    def _count_select(_conn, _cursor, statement, _params, _context, _executemany):
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT"):
            select_count += 1

    event.listen(test_engine, "before_cursor_execute", _count_select)
    try:
        rows = get_cut_list(project_id)
    finally:
        event.remove(test_engine, "before_cursor_execute", _count_select)

    assert [row["title"] for row in rows] == [
        "clip_0",
        "clip_1",
        "clip_2",
        "clip_3",
        "clip_4",
    ]
    assert select_count <= 2
