from __future__ import annotations

from database import AnalysisStatus


def _status_row(session, audio_id: int, step_key: str) -> AnalysisStatus:
    return (
        session.query(AnalysisStatus)
        .filter(
            AnalysisStatus.media_type == "audio",
            AnalysisStatus.media_id == audio_id,
            AnalysisStatus.step_key == step_key,
        )
        .one()
    )


def test_b461_infer_reconciles_lufs_error_when_db_value_exists(db_session, audio_track):
    from services.analysis_status_service import _infer_audio_status

    audio_track.lufs = -13.76
    db_session.add(
        AnalysisStatus(
            media_type="audio",
            media_id=audio_track.id,
            step_key="lufs_analysis",
            status="error",
            error_message="FFmpeg-Timeout",
        )
    )
    db_session.commit()

    _infer_audio_status(db_session, audio_track.id)
    db_session.commit()

    db_session.expire_all()
    row = _status_row(db_session, audio_track.id, "lufs_analysis")
    assert row.status == "done"
    assert row.error_message is None
    assert row.value_summary == {"lufs": -13.76}


def test_b461_infer_reconciles_stem_running_when_stem_paths_exist(db_session, audio_track):
    from services.analysis_status_service import _infer_audio_status

    audio_track.stem_vocals_path = "storage/stems/vocals.wav"
    audio_track.stem_drums_path = "storage/stems/drums.wav"
    audio_track.stem_bass_path = "storage/stems/bass.wav"
    audio_track.stem_other_path = "storage/stems/other.wav"
    db_session.add(
        AnalysisStatus(
            media_type="audio",
            media_id=audio_track.id,
            step_key="stem_separation",
            status="running",
        )
    )
    db_session.commit()

    _infer_audio_status(db_session, audio_track.id)
    db_session.commit()

    db_session.expire_all()
    row = _status_row(db_session, audio_track.id, "stem_separation")
    assert row.status == "done"
    assert row.value_summary == {"stems": 4}
