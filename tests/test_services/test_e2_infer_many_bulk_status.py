from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from database import (
    AnalysisStatus,
    AudioTrack,
    Beatgrid,
    Project,
    Scene,
    StructureSegment,
    VideoClip,
    WaveformData,
)


def test_e2_infer_many_bulk_status_and_reuses_loaded_scenes(test_engine, monkeypatch):
    from services import analysis_status_service as svc

    with Session(test_engine) as session:
        session.add(Project(id=1, name="P", path="."))
        for video_id in (1, 2):
            session.add(VideoClip(
                id=video_id,
                project_id=1,
                file_path=f"/v/{video_id}.mp4",
                duration=30.0,
                width=1920,
                height=1080,
                fps=30.0,
                codec="h264",
            ))
            session.add(Scene(
                video_clip_id=video_id,
                start_time=0.0,
                end_time=5.0,
                ai_caption="caption",
            ))
        session.add(AnalysisStatus(
            media_type="video",
            media_id=1,
            step_key="metadata_extract",
            status="failed",
            error_message="old",
        ))
        session.commit()

    @contextmanager
    def _session():
        with Session(test_engine) as session:
            yield session

    monkeypatch.setattr(svc, "nullpool_session", _session)
    statements: list[str] = []

    def _before(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(test_engine, "before_cursor_execute", _before)
    try:
        svc.infer_many_from_db("video", [1, 2])
    finally:
        event.remove(test_engine, "before_cursor_execute", _before)

    status_selects = [
        statement for statement in statements
        if statement.lstrip().startswith("select") and "analysis_status" in statement
    ]
    scene_selects = [
        statement for statement in statements
        if statement.lstrip().startswith("select") and " scenes" in statement
    ]
    assert len(status_selects) == 1
    assert len(scene_selects) == 2

    with Session(test_engine) as session:
        rows = session.execute(
            select(AnalysisStatus).where(AnalysisStatus.media_type == "video")
        ).scalars().all()
        actual = {
            (row.media_id, row.step_key): (
                row.status,
                row.error_message,
                row.value_summary,
            )
            for row in rows
        }

    assert set(actual) == {
        (video_id, step_key)
        for video_id in (1, 2)
        for step_key in (
            "metadata_extract",
            "scene_detection",
            "scene_db_storage",
            "ai_scene_caption",
        )
    }
    assert actual[(1, "metadata_extract")][0:2] == ("done", None)
    assert actual[(1, "metadata_extract")][2] == {
        "duration": 30.0,
        "resolution": "1920x1080",
        "fps": 30.0,
        "codec": "h264",
    }
    assert actual[(2, "scene_detection")][2] == {"scenes": 1}
    assert actual[(2, "ai_scene_caption")][2] == {"captioned_scenes": 1}


def test_e2_infer_many_audio_uses_same_bulk_status_map(test_engine, monkeypatch):
    from services import analysis_status_service as svc

    with Session(test_engine) as session:
        session.add(Project(id=1, name="P", path="."))
        session.add(AudioTrack(
            id=1,
            project_id=1,
            file_path="/a/1.mp3",
            duration=60.0,
            key="8A",
            key_confidence=0.9,
            lufs=-14.0,
            mood="dark",
            genre="psy",
            spectral_bands=[0.1, 0.2],
            stem_vocals_path="vocals.wav",
        ))
        session.add(Beatgrid(
            audio_track_id=1,
            bpm=120.0,
            offset=0.0,
            beat_positions=[0.0, 0.5],
        ))
        session.add(WaveformData(
            audio_track_id=1,
            num_samples=100,
            duration=60.0,
            band_low=[0.1],
            band_mid=[0.2],
            band_high=[0.3],
        ))
        session.add(StructureSegment(
            audio_track_id=1,
            start_time=0.0,
            end_time=10.0,
            label="DROP",
            energy=0.8,
        ))
        session.commit()

    @contextmanager
    def _session():
        with Session(test_engine) as session:
            yield session

    monkeypatch.setattr(svc, "nullpool_session", _session)
    statements: list[str] = []

    def _before(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(test_engine, "before_cursor_execute", _before)
    try:
        svc.infer_many_from_db("audio", [1])
    finally:
        event.remove(test_engine, "before_cursor_execute", _before)

    status_selects = [
        statement for statement in statements
        if statement.lstrip().startswith("select") and "analysis_status" in statement
    ]
    assert len(status_selects) == 1

    with Session(test_engine) as session:
        rows = session.execute(
            select(AnalysisStatus).where(AnalysisStatus.media_type == "audio")
        ).scalars().all()
        actual = {row.step_key: row.value_summary for row in rows}

    assert actual == {
        "bpm_detection": {"bpm": 120.0, "beats": 2},
        "waveform_analysis": {"num_samples": 100},
        "key_detection": {"key": "8A", "confidence": 0.9},
        "lufs_analysis": {"lufs": -14.0},
        "mood_genre_classify": {"mood": "dark", "genre": "psy"},
        "spectral_analysis": {"bands": 2},
        "structure_detection": {"segments": 1},
        "stem_separation": {"stems": 1},
    }
