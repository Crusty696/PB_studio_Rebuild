from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace


def test_b408_lufs_worker_skips_soft_deleted_audio_track(db_session, audio_track):
    from workers.audio_analysis import LUFSAnalysisWorker

    audio_track.deleted_at = datetime.now(timezone.utc)
    db_session.commit()

    worker = LUFSAnalysisWorker(audio_track.id, audio_track.file_path)
    worker._save_to_db(SimpleNamespace(integrated=-9.25))

    db_session.refresh(audio_track)
    assert audio_track.lufs is None
