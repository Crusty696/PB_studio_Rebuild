"""Tests fuer services.brain_v3.storage.embedding_repository (sqlite-vec).

Wenn sqlite-vec NICHT installiert: alle Tests werden SKIPPED, nicht failed.
sqlite-vec>=0.1.6 ist feste Dependency in requirements-py310-cu113.txt; nach
`pip install -r requirements-py310-cu113.txt` laufen diese Tests.
"""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import numpy as np
import pytest


_HAS_SQLITE_VEC = importlib.util.find_spec("sqlite_vec") is not None


pytestmark = pytest.mark.skipif(
    not _HAS_SQLITE_VEC,
    reason="sqlite-vec nicht installiert. "
           "pip install -r requirements-py310-cu113.txt",
)


HASH = "c" * 64


def test_embedding_repository_console_log_messages_are_ascii_safe():
    from services.brain_v3.storage.embedding_repository import EmbeddingRepository

    src = inspect.getsource(EmbeddingRepository._apply_migrations)
    assert "→" not in src
    assert "-> user_version=%d" in src


@pytest.fixture
def repo(tmp_path: Path):
    from services.brain_v3.storage.embedding_repository import EmbeddingRepository
    return EmbeddingRepository(project_root=tmp_path / "proj")


def test_repo_init_creates_db_and_schema(repo, tmp_path: Path):
    db_path = tmp_path / "proj" / "brain_v3" / "embeddings.db"
    assert db_path.exists()

    import sqlite3
    from services.brain_v3.storage.sqlite_init import open_connection
    conn = open_connection(db_path, load_sqlite_vec=True)
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        )}
        # audio_units, video_units regular tables
        assert "audio_units" in names
        assert "video_units" in names
    finally:
        conn.close()


def test_audio_unit_round_trip(repo):
    from services.brain_v3.storage.embedding_repository import AudioUnit, CLAP_DIM
    unit = AudioUnit(
        level="window", media_id=1, media_hash=HASH,
        start_time=0.0, end_time=10.0,
    )
    saved = repo.add_audio_unit(unit)
    assert saved.id is not None and saved.id > 0

    emb = np.random.randn(CLAP_DIM).astype("float32")
    repo.add_audio_embedding(saved.id, emb)

    # KNN gegen sich selbst → distance 0 fuer das Insert
    hits = repo.knn_audio(emb, k=1)
    assert len(hits) == 1
    assert hits[0].unit_id == saved.id
    assert hits[0].distance < 1e-3


def test_audio_knn_returns_correct_order(repo):
    from services.brain_v3.storage.embedding_repository import AudioUnit, CLAP_DIM
    a = repo.add_audio_unit(AudioUnit(
        level="window", media_id=1, media_hash=HASH, start_time=0, end_time=10,
    ))
    b = repo.add_audio_unit(AudioUnit(
        level="window", media_id=2, media_hash=HASH, start_time=10, end_time=20,
    ))
    e_a = np.array([1.0] + [0.0] * 511, dtype="float32")
    e_b = np.array([0.0] + [1.0] + [0.0] * 510, dtype="float32")
    repo.add_audio_embedding(a.id, e_a)
    repo.add_audio_embedding(b.id, e_b)

    # Query nahe an e_a
    hits = repo.knn_audio(e_a, k=2)
    assert len(hits) == 2
    assert hits[0].unit_id == a.id  # nearest
    assert hits[1].unit_id == b.id


def test_audio_knn_filtered_by_level(repo):
    from services.brain_v3.storage.embedding_repository import AudioUnit, CLAP_DIM
    win = repo.add_audio_unit(AudioUnit(
        level="window", media_id=1, media_hash=HASH, start_time=0, end_time=10,
    ))
    sec = repo.add_audio_unit(AudioUnit(
        level="section", media_id=1, media_hash=HASH, start_time=0, end_time=30,
    ))
    e = np.random.randn(CLAP_DIM).astype("float32")
    repo.add_audio_embedding(win.id, e)
    repo.add_audio_embedding(sec.id, e)

    hits_window = repo.knn_audio(e, k=10, level="window")
    assert all(h.unit_id == win.id for h in hits_window)
    hits_section = repo.knn_audio(e, k=10, level="section")
    assert all(h.unit_id == sec.id for h in hits_section)


def test_video_unit_round_trip(repo):
    from services.brain_v3.storage.embedding_repository import VideoUnit, SIGLIP_DIM
    unit = VideoUnit(
        level="scene", media_id=42, media_hash=HASH,
        start_time=0.0, end_time=5.0,
        motion_score=0.5, brightness=0.7, saturation=0.4, color_temp=0.1,
    )
    saved = repo.add_video_unit(unit)
    assert saved.id is not None

    emb = np.random.randn(SIGLIP_DIM).astype("float32")
    repo.add_video_embedding(saved.id, emb)

    hits = repo.knn_video(emb, k=1)
    assert len(hits) == 1
    assert hits[0].unit_id == saved.id


def test_dim_mismatch_raises(repo):
    from services.brain_v3.storage.embedding_repository import AudioUnit, VideoUnit
    a = repo.add_audio_unit(AudioUnit(
        level="window", media_id=1, media_hash=HASH, start_time=0, end_time=10,
    ))
    with pytest.raises(ValueError):
        repo.add_audio_embedding(a.id, np.zeros(768, dtype="float32"))

    v = repo.add_video_unit(VideoUnit(
        level="scene", media_id=1, media_hash=HASH, start_time=0, end_time=5,
    ))
    with pytest.raises(ValueError):
        repo.add_video_embedding(v.id, np.zeros(512, dtype="float32"))
