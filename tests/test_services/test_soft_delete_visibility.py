from __future__ import annotations

import datetime as _dt

from sqlalchemy.orm import Session

from database import AudioTrack, Project, Scene, VideoClip


def test_ingest_media_lists_exclude_soft_deleted_parents(test_engine):
    import services.ingest_service as ingest_service

    ingest_service.engine = test_engine
    with Session(test_engine) as session:
        project = Project(name="P", path=".")
        session.add(project)
        session.flush()
        audio = AudioTrack(
            project_id=project.id,
            file_path="/tmp/deleted-audio.wav",
            title="deleted audio",
            deleted_at=_dt.datetime.now(),
        )
        video = VideoClip(
            project_id=project.id,
            file_path="/tmp/deleted-video.mp4",
            width=1920,
            height=1080,
            deleted_at=_dt.datetime.now(),
        )
        session.add_all([audio, video])
        session.commit()
        project_id = project.id

    assert ingest_service.get_all_audio(project_id) == []
    assert ingest_service.get_all_video(project_id) == []
    assert ingest_service.get_combo_items(project_id) == []


def test_pacing_scene_lookup_hides_orphan_children_of_soft_deleted_video(test_engine, monkeypatch):
    import services.pacing_beat_grid as pacing_beat_grid

    monkeypatch.setattr(pacing_beat_grid, "engine", test_engine)
    pacing_beat_grid._get_video_info_cached.cache_clear()

    with Session(test_engine) as session:
        project = Project(name="P", path=".")
        session.add(project)
        session.flush()
        video = VideoClip(
            project_id=project.id,
            file_path="/tmp/deleted-video.mp4",
            duration=10.0,
            deleted_at=_dt.datetime.now(),
        )
        session.add(video)
        session.flush()
        scene = Scene(
            video_clip_id=video.id,
            start_time=0.0,
            end_time=1.0,
            label="orphan visible only through deleted parent",
        )
        session.add(scene)
        session.commit()
        video_id = video.id

    assert pacing_beat_grid._get_scenes(video_id) == []
    assert pacing_beat_grid._get_video_info([video_id]) == {}
