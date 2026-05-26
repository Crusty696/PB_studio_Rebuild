from __future__ import annotations

from datetime import datetime

from database import Project, TimelineEntry, VideoClip


def _patch_active_project_engine(monkeypatch, test_engine):
    import database.session as db_session_module

    monkeypatch.setattr(db_session_module, "engine", test_engine)


def test_b415_add_to_timeline_rejects_cross_project_video(
    test_engine,
    db_session,
    project,
    monkeypatch,
):
    from services.actions import edit_actions

    _patch_active_project_engine(monkeypatch, test_engine)
    other_project = Project(name="Other", path="/tmp/other", resolution="1920x1080", fps=30.0)
    db_session.add(other_project)
    db_session.commit()
    clip = VideoClip(
        project_id=other_project.id,
        file_path="/tmp/other.mp4",
        duration=10.0,
    )
    db_session.add(clip)
    db_session.commit()
    clip_id = clip.id

    result = edit_actions.add_to_timeline(clip_id, "video")

    assert "error" in result
    assert "aktiven Projekt" in result["error"]
    assert db_session.query(TimelineEntry).filter_by(project_id=project.id).count() == 0


def test_b415_add_to_timeline_rejects_soft_deleted_video(
    test_engine,
    db_session,
    project,
    monkeypatch,
):
    from services.actions import edit_actions

    _patch_active_project_engine(monkeypatch, test_engine)
    clip = VideoClip(
        project_id=project.id,
        file_path="/tmp/deleted.mp4",
        duration=10.0,
        deleted_at=datetime.now(),
    )
    db_session.add(clip)
    db_session.commit()
    clip_id = clip.id

    result = edit_actions.add_to_timeline(clip_id, "video")

    assert "error" in result
    assert "nicht gefunden" in result["error"]
    assert db_session.query(TimelineEntry).filter_by(project_id=project.id).count() == 0
