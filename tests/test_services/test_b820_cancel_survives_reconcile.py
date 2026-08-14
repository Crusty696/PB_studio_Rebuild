"""B-820: Ein per User-Cancel abgebrochener Schritt darf vom Status-Reconciler
nicht auf ``done`` gehoben werden.

Live-Befund 2026-08-14 (W3 Audio V2, Run 20260814T0405-w3-audio-v2): der Nutzer
brach die Analyse waehrend der Stage ``beat_grid`` ab. ``mark_cancelled()``
schrieb korrekt ``status='error'`` / ``error_message='cancelled'``. In derselben
Sekunde hob ``_ensure_status_done()`` den Eintrag wieder auf ``done`` und
loeschte die ``error_message``, weil das Beatgrid vor dem Cancel-Check bereits
persistiert worden war.

Abgrenzung zu B-461: ein *echter* Fehler (z.B. FFmpeg-Timeout) soll weiterhin
reconciled werden, wenn der Wert nachweislich in der DB steht. Nur die bewusste
Abbruch-Absicht des Nutzers ist geschuetzt.
"""

from __future__ import annotations

from database import AnalysisStatus, Beatgrid, Scene


def _row(session, media_type: str, media_id: int, step_key: str) -> AnalysisStatus:
    return (
        session.query(AnalysisStatus)
        .filter(
            AnalysisStatus.media_type == media_type,
            AnalysisStatus.media_id == media_id,
            AnalysisStatus.step_key == step_key,
        )
        .one()
    )


def test_b820_cancelled_audio_step_survives_infer(db_session, audio_track):
    """Der Live-Fall: Beatgrid liegt vor, Schritt wurde aber abgebrochen."""
    from services.analysis_status_service import _infer_audio_status

    db_session.add(
        Beatgrid(
            audio_track_id=audio_track.id,
            bpm=130.4,
            beat_positions=[0.1 * i for i in range(99)],
        )
    )
    db_session.add(
        AnalysisStatus(
            media_type="audio",
            media_id=audio_track.id,
            step_key="bpm_detection",
            status="error",
            error_message="cancelled",
        )
    )
    db_session.commit()

    _infer_audio_status(db_session, audio_track.id)
    db_session.commit()
    db_session.expire_all()

    row = _row(db_session, "audio", audio_track.id, "bpm_detection")
    assert row.status == "error"
    assert row.error_message == "cancelled"
    assert row.completed_at is None


def test_b820_cancelled_video_step_survives_infer(db_session, video_clip):
    """Gleiche Zusage fuer den Video-Pfad — dieselbe Hilfsfunktion."""
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
            error_message="cancelled",
        )
    )
    db_session.commit()

    _infer_video_status(db_session, video_clip.id)
    db_session.commit()
    db_session.expire_all()

    row = _row(db_session, "video", video_clip.id, "scene_detection")
    assert row.status == "error"
    assert row.error_message == "cancelled"


def test_b820_real_error_is_still_reconciled(db_session, audio_track):
    """B-461-Regression: echte Fehler bleiben reconcilebar."""
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

    row = _row(db_session, "audio", audio_track.id, "lufs_analysis")
    assert row.status == "done"
    assert row.error_message is None


def test_b820_mark_cancelled_then_infer_end_to_end(db_session, audio_track):
    """Verkettung wie live: erst mark_cancelled, dann Status-Refresh.

    Nutzt bewusst die oeffentliche API statt eines handgesetzten Rows, damit
    der Marker aus ``mark_cancelled()`` und die Schutzbedingung im Reconciler
    nicht auseinanderlaufen koennen.
    """
    from services.analysis_status_service import (
        _infer_audio_status,
        mark_cancelled,
        mark_done,
    )

    db_session.add(
        Beatgrid(
            audio_track_id=audio_track.id,
            bpm=130.4,
            beat_positions=[0.1 * i for i in range(99)],
        )
    )
    db_session.commit()

    mark_done("audio", audio_track.id, "bpm_detection", {"bpm": 130.4})
    mark_cancelled("audio", audio_track.id, "bpm_detection")

    _infer_audio_status(db_session, audio_track.id)
    db_session.commit()
    db_session.expire_all()

    row = _row(db_session, "audio", audio_track.id, "bpm_detection")
    assert row.status == "error"
    assert row.error_message == "cancelled"
