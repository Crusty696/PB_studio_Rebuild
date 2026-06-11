"""B-462 Stage 2 (Task 12, option C): Two-Tier purge + restore for soft-deleted media.

Design (D-056 / full-audit-fixplan Task 12, user-released 2026-06-11):
- Soft delete (Stage 1) sets ``deleted_at`` and keeps analysis children.
- ``get_soft_deleted_media`` lists the soft-deleted parents (the "Papierkorb").
- ``restore_media`` clears ``deleted_at`` so the row is active again. Analysis
  children survive a soft delete, so a restore brings the clip back with them.
- ``purge_soft_deleted_media`` is the irreversible "Papierkorb leeren": it
  physically deletes ALL soft-deleted parents of the project plus their analysis
  children (recycled hard-delete path) and the matching VectorDB embeddings.
- Active media (``deleted_at IS NULL``) must never be touched by purge.
"""
from __future__ import annotations

import datetime as _dt

from sqlalchemy.orm import Session

from database import (
    AnalysisStatus,
    AudioTrack,
    Beatgrid,
    Project,
    Scene,
    VideoClip,
)


class _FakeVectorDB:
    """No-op VectorDB so purge/restore tests stay hermetic."""

    def delete_all(self):
        return None

    def delete_by_clip_ids(self, clip_ids):
        return None


def _seed(session, project_id, *, deleted: bool):
    """Create one video (+Scene) and one audio (+Beatgrid), active or soft-deleted."""
    stamp = _dt.datetime.now() if deleted else None
    video = VideoClip(
        project_id=project_id, file_path=f"/tmp/v_{deleted}.mp4",
        width=1920, height=1080, deleted_at=stamp,
    )
    audio = AudioTrack(
        project_id=project_id, file_path=f"/tmp/a_{deleted}.wav",
        title="t", deleted_at=stamp,
    )
    session.add_all([video, audio])
    session.flush()
    session.add(Scene(video_clip_id=video.id, start_time=0.0, end_time=1.0, label="s"))
    session.add(Beatgrid(audio_track_id=audio.id, bpm=120.0))
    # Polymorphe Analyse-Status-Rows (B-188/D-028) — Purge muss sie mitnehmen.
    session.add(AnalysisStatus(media_type="video", media_id=video.id, step_key="scene_detection", status="done"))
    session.add(AnalysisStatus(media_type="audio", media_id=audio.id, step_key="bpm_detection", status="done"))
    session.commit()
    return video.id, audio.id


def test_get_soft_deleted_media_lists_only_deleted(test_engine):
    import services.ingest_service as ingest_service

    with Session(test_engine) as session:
        project = Project(name="P", path=".")
        session.add(project)
        session.flush()
        pid = project.id
        del_vid, del_aid = _seed(session, pid, deleted=True)
        _seed(session, pid, deleted=False)

    items = ingest_service.get_soft_deleted_media(pid)
    ids = {(it["type"], it["id"]) for it in items}
    assert ("Video", del_vid) in ids
    assert ("Audio", del_aid) in ids
    assert len(items) == 2, "only soft-deleted parents belong in the trash list"
    assert all(it.get("deleted_at") is not None for it in items)


def test_restore_media_clears_deleted_at(test_engine):
    import services.ingest_service as ingest_service

    with Session(test_engine) as session:
        project = Project(name="P", path=".")
        session.add(project)
        session.flush()
        pid = project.id
        vid, aid = _seed(session, pid, deleted=True)

    n = ingest_service.restore_media([vid], [aid])
    assert n == 2

    with Session(test_engine) as session:
        assert session.get(VideoClip, vid).deleted_at is None
        assert session.get(AudioTrack, aid).deleted_at is None

    assert {it["id"] for it in ingest_service.get_all_video(pid)} == {vid}
    assert {it["id"] for it in ingest_service.get_all_audio(pid)} == {aid}


def test_purge_physically_deletes_soft_deleted_and_children(test_engine, monkeypatch):
    import services.ingest_service as ingest_service

    monkeypatch.setattr(ingest_service, "VectorDBService", _FakeVectorDB)

    with Session(test_engine) as session:
        project = Project(name="P", path=".")
        session.add(project)
        session.flush()
        pid = project.id
        vid, aid = _seed(session, pid, deleted=True)
        with Session(test_engine) as s2:
            sid = s2.query(Scene.id).filter(Scene.video_clip_id == vid).scalar()
            bid = s2.query(Beatgrid.id).filter(Beatgrid.audio_track_id == aid).scalar()

    n = ingest_service.purge_soft_deleted_media(pid)
    assert n == 2, "two soft-deleted parents purged"

    with Session(test_engine) as session:
        assert session.get(VideoClip, vid) is None, "parent physically gone"
        assert session.get(AudioTrack, aid) is None
        assert session.get(Scene, sid) is None, "analysis child physically gone"
        assert session.get(Beatgrid, bid) is None
        # B-188/D-028: polymorphe analysis_status-Orphans muessen beim Purge weg.
        remaining = session.query(AnalysisStatus).filter(
            AnalysisStatus.media_id.in_([vid, aid])
        ).count()
        assert remaining == 0, "analysis_status orphans must be purged"


def test_purge_does_not_touch_active_media(test_engine, monkeypatch):
    import services.ingest_service as ingest_service

    monkeypatch.setattr(ingest_service, "VectorDBService", _FakeVectorDB)

    with Session(test_engine) as session:
        project = Project(name="P", path=".")
        session.add(project)
        session.flush()
        pid = project.id
        _seed(session, pid, deleted=True)
        act_vid, act_aid = _seed(session, pid, deleted=False)

    ingest_service.purge_soft_deleted_media(pid)

    with Session(test_engine) as session:
        assert session.get(VideoClip, act_vid) is not None, "active video survives purge"
        assert session.get(AudioTrack, act_aid) is not None, "active audio survives purge"
