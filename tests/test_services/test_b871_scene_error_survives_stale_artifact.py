"""B-871: Alte Scenes duerfen aktuellen Reanalysefehler nicht verdecken."""

from database import AnalysisStatus, Scene


def test_b871_scene_error_survives_stale_scene_rows(db_session, video_clip):
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
            status="error",
            error_message="Scene detection failed: unreadable input",
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
    assert row.status == "error"
    assert row.error_message == "Scene detection failed: unreadable input"

