"""B-619 — Unit-Test fuer den neuen Dialog-Anker-Sync-Pfad.

Prueft, dass sync_dialog_anchors() Dialog-Anker paarweise korrekt in
AudioVideoAnchor persistiert (Scene.id -> video_clip_id/start_time) und
idempotent ist.
"""

import importlib
from contextlib import contextmanager

import pytest

from sqlalchemy.orm import Session

import database
from database import AudioVideoAnchor


@pytest.fixture
def _patched_service(test_engine, monkeypatch):
    """Patcht die nullpool_session-Referenz im anchor_sync_service auf die Test-Engine.

    B-628: Der Service nutzt jetzt ``nullpool_session()`` (robustes Write-Muster
    mit busy_timeout) statt ``DBSession(engine)``. Der Test leitet die Session
    auf die In-Memory-Test-Engine um.
    """
    mod = importlib.import_module("services.anchor_sync_service")

    @contextmanager
    def _test_nullpool():
        with Session(test_engine) as s:
            yield s

    monkeypatch.setattr(mod, "nullpool_session", _test_nullpool)
    return mod


@pytest.fixture
def _two_scenes(db_session, video_clip):
    """Zwei Szenen S1/S2 auf demselben VideoClip."""
    s1 = database.Scene(video_clip_id=video_clip.id, start_time=1.5, end_time=3.0, label="S1")
    s2 = database.Scene(video_clip_id=video_clip.id, start_time=4.0, end_time=6.5, label="S2")
    db_session.add_all([s1, s2])
    db_session.commit()
    db_session.refresh(s1)
    db_session.refresh(s2)
    return video_clip, s1, s2


def test_sync_dialog_anchors_persists_pairwise(_patched_service, db_session, audio_track, _two_scenes):
    video_clip, s1, s2 = _two_scenes

    anchors = [
        {"audio_time": 10.0, "scene_id": str(s1.id)},
        {"audio_time": 25.5, "scene_id": str(s2.id)},
    ]

    count = _patched_service.sync_dialog_anchors(audio_track.id, anchors)
    assert count == 2

    rows = (
        db_session.query(AudioVideoAnchor)
        .filter(AudioVideoAnchor.audio_track_id == audio_track.id)
        .order_by(AudioVideoAnchor.audio_time)
        .all()
    )
    assert len(rows) == 2

    r1, r2 = rows
    # T1 -> S1
    assert r1.audio_time == 10.0
    assert r1.video_clip_id == video_clip.id
    assert r1.video_time == pytest.approx(1.5)
    assert r1.anchor_type == "dialog"
    # T2 -> S2
    assert r2.audio_time == 25.5
    assert r2.video_clip_id == video_clip.id
    assert r2.video_time == pytest.approx(4.0)
    assert r2.anchor_type == "dialog"


def test_sync_dialog_anchors_idempotent(_patched_service, db_session, audio_track, _two_scenes):
    video_clip, s1, s2 = _two_scenes
    anchors = [
        {"audio_time": 10.0, "scene_id": str(s1.id)},
        {"audio_time": 25.5, "scene_id": str(s2.id)},
    ]
    _patched_service.sync_dialog_anchors(audio_track.id, anchors)
    # Zweiter Lauf darf nicht duplizieren.
    _patched_service.sync_dialog_anchors(audio_track.id, anchors)

    rows = (
        db_session.query(AudioVideoAnchor)
        .filter(AudioVideoAnchor.audio_track_id == audio_track.id)
        .all()
    )
    assert len(rows) == 2


def test_sync_dialog_anchors_clip_form(_patched_service, db_session, audio_track, video_clip):
    """'clip_<id>' -> ganzer Clip, video_time = 0.0."""
    anchors = [{"audio_time": 5.0, "scene_id": f"clip_{video_clip.id}"}]
    count = _patched_service.sync_dialog_anchors(audio_track.id, anchors)
    assert count == 1

    row = db_session.query(AudioVideoAnchor).filter(
        AudioVideoAnchor.audio_track_id == audio_track.id
    ).one()
    assert row.video_clip_id == video_clip.id
    assert row.video_time == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# B-628: DB-Lock-Robustheit
# ---------------------------------------------------------------------------

def test_sync_dialog_anchors_uses_robust_session(_patched_service, monkeypatch, audio_track):
    """B-628: Der Service muss die robuste nullpool_session() nutzen, nicht
    ein nacktes DBSession(engine). Beweist, dass der Write ueber die
    busy_timeout-Engine laeuft statt ueber den gepoolten Zugriff, der bei
    Lock-Contention crashte."""
    mod = _patched_service
    real_ctx = mod.nullpool_session
    calls = {"n": 0}

    def _spy():
        calls["n"] += 1
        return real_ctx()

    monkeypatch.setattr(mod, "nullpool_session", _spy)

    mod.sync_dialog_anchors(audio_track.id, [])
    assert calls["n"] == 1, "sync_dialog_anchors muss ueber nullpool_session() laufen"


def test_nullpool_engine_sets_busy_timeout():
    """B-628: Die vom Service genutzte NullPool-Engine setzt busy_timeout=120s,
    damit Writes bei Lock-Contention warten statt sofort mit
    'database is locked' zu crashen (database/session.py:198)."""
    from sqlalchemy import text
    from database.session import make_nullpool_engine
    from services.timeout_constants import DB_BUSY_TIMEOUT_ANALYSIS_MS

    eng = make_nullpool_engine("sqlite:///:memory:", enable_foreign_keys=True)
    try:
        with eng.connect() as conn:
            busy = conn.execute(text("PRAGMA busy_timeout")).scalar()
        assert busy == DB_BUSY_TIMEOUT_ANALYSIS_MS
    finally:
        eng.dispose()
