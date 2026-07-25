"""B-706/S2-Neufund: Classify-/Spectral-Worker schreiben nicht auf soft-geloeschte Rows.

Der Key-/LUFS-Worker filterte bereits ``deleted_at.is_(None)``; Classify- und
Spectral-Worker nutzten ``session.get(AudioTrack, id)`` ohne Filter -> Tombstone-
Write auf eine waehrend der Analyse soft-geloeschte Row. Jetzt filtern alle.
"""
from __future__ import annotations

import datetime as _dt
from types import SimpleNamespace

from sqlalchemy.orm import Session

from database import AudioTrack, Project


def _soft_deleted_track(test_engine):
    with Session(test_engine) as session:
        project = Project(name="P", path=".")
        session.add(project)
        session.commit()
        track = AudioTrack(
            project_id=project.id, file_path="/tmp/a.wav", title="t",
            deleted_at=_dt.datetime.now(),
        )
        session.add(track)
        session.commit()
        return track.id


def test_b706_s2_classify_worker_skips_soft_deleted(test_engine):
    from workers.audio_analysis import AudioClassifyWorker

    tid = _soft_deleted_track(test_engine)
    worker = AudioClassifyWorker(tid, "/tmp/a.wav")
    result = SimpleNamespace(mood="happy", genre="psy", sub_genre=None, is_dj_mix=False)
    worker._save_to_db(result)

    with Session(test_engine) as session:
        track = session.get(AudioTrack, tid)
        assert track.mood is None, "Classify darf nicht auf soft-geloeschte Row schreiben (B-706/S2)"
        assert track.genre is None


def test_b706_s2_spectral_worker_skips_soft_deleted(test_engine):
    from workers.audio_analysis import SpectralAnalysisWorker

    tid = _soft_deleted_track(test_engine)
    worker = SpectralAnalysisWorker(tid, "/tmp/a.wav")
    worker._svc = SimpleNamespace(get_bands_json=lambda _r: "{}")
    worker._save_to_db(SimpleNamespace())

    with Session(test_engine) as session:
        track = session.get(AudioTrack, tid)
        assert track.spectral_bands is None, (
            "Spectral darf nicht auf soft-geloeschte Row schreiben (B-706/S2)"
        )
