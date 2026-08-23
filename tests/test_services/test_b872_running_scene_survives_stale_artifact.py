"""B-872: Alte Scenes duerfen laufende Reanalyse nicht als done markieren."""

from database import AnalysisStatus, Scene


def test_b872_running_scene_survives_stale_scene_rows(db_session, video_clip):
    from services.analysis_status_service import _infer_video_status

    db_session.add(
        Scene(
            video_clip_id=video_clip.id,
            scene_index=0,
            start_time=0.0,
            end_time=1.0,
        )
    )
    db_session.add(
        AnalysisStatus(
            media_type="video",
            media_id=video_clip.id,
            step_key="scene_detection",
            status="running",
        )
    )
    db_session.commit()

    _infer_video_status(db_session, video_clip.id)
    db_session.commit()
    db_session.expire_all()

    row = (
        db_session.query(AnalysisStatus)
        .filter_by(
            media_type="video",
            media_id=video_clip.id,
            step_key="scene_detection",
        )
        .one()
    )
    assert row.status == "running"
    assert row.completed_at is None

