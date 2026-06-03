"""B-462 Stage 1: GUI media delete must soft-delete (set deleted_at) instead of
physically deleting the parent rows.

Design (D-056, user-confirmed 2026-06-03):
- delete_selected_media and delete_all_media set deleted_at on VideoClip/AudioTrack.
- Analysis children (Scene, Beatgrid, ...) are kept (full undo, filtered via parent).
- Relationship children (TimelineEntry, ClipAnchor, AudioVideoAnchor, PacingBlueprint)
  are still removed (no orphan in the active timeline).
- VectorDB embeddings are kept on a soft delete.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import Project, Scene, TimelineEntry, VideoClip


class _FakeVectorDB:
    """No-op VectorDB so soft-delete tests have no external side effects.

    B-462 Stage 1 keeps the VectorDB embedding cleanup on a soft delete so
    Semantic-Search does not return soft-deleted clips; the real service is
    mocked here to keep the test hermetic.
    """

    def delete_all(self):
        return None

    def delete_by_clip_ids(self, clip_ids):
        return None


def _seed_video_with_children(session, project_id):
    video = VideoClip(
        project_id=project_id, file_path="/tmp/v.mp4", width=1920, height=1080
    )
    session.add(video)
    session.flush()
    scene = Scene(video_clip_id=video.id, start_time=0.0, end_time=1.0, label="s")
    session.add(scene)
    timeline = TimelineEntry(project_id=project_id, media_id=video.id, track="video")
    session.add(timeline)
    session.commit()
    return video.id, scene.id, timeline.id


def test_delete_selected_media_soft_deletes_video_keeps_analysis(
    test_engine, monkeypatch
):
    import services.ingest_service as ingest_service

    monkeypatch.setattr(ingest_service, "VectorDBService", _FakeVectorDB)

    with Session(test_engine) as session:
        project = Project(name="P", path=".")
        session.add(project)
        session.flush()
        pid = project.id
        vid, sid, tid = _seed_video_with_children(session, pid)

    n = ingest_service.delete_selected_media([vid], [])
    assert n == 1

    with Session(test_engine) as session:
        v = session.get(VideoClip, vid)
        assert v is not None, "video row must be kept (soft delete)"
        assert v.deleted_at is not None, "video must have deleted_at set"
        assert session.get(Scene, sid) is not None, "analysis child Scene must be kept"
        assert (
            session.get(TimelineEntry, tid) is None
        ), "relationship child TimelineEntry must be removed"

    assert (
        ingest_service.get_all_video(pid) == []
    ), "soft-deleted video must be excluded from active reads"


def test_delete_all_media_soft_deletes_parents_keeps_analysis(
    test_engine, monkeypatch
):
    import services.ingest_service as ingest_service

    monkeypatch.setattr(ingest_service, "VectorDBService", _FakeVectorDB)

    with Session(test_engine) as session:
        project = Project(name="P", path=".")
        session.add(project)
        session.flush()
        pid = project.id
        vid, sid, tid = _seed_video_with_children(session, pid)

    ingest_service.delete_all_media(pid)

    with Session(test_engine) as session:
        v = session.get(VideoClip, vid)
        assert v is not None, "video row must be kept (soft delete)"
        assert v.deleted_at is not None, "video must have deleted_at set"
        assert session.get(Scene, sid) is not None, "analysis child Scene must be kept"
        assert (
            session.get(TimelineEntry, tid) is None
        ), "relationship child TimelineEntry must be removed"

    assert ingest_service.get_all_video(pid) == []
