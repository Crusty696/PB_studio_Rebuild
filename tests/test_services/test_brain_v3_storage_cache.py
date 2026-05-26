"""Tests fuer services.brain_v3.storage.embedding_cache + sqlite_init + migration_runner.

CPU-only — kein sqlite-vec, kein torch noetig. Nutzt isoliertes APPDATA via tmp_path.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from services.brain_v3.storage import sqlite_init
from services.brain_v3.storage.embedding_cache import EmbeddingCache, CacheEntry
from services.brain_v3.storage.migration_runner import migrate


HASH_AUDIO = "a" * 64
HASH_VIDEO = "b" * 64


@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    yield tmp_path


# ---------------------------------------------------------------------------
# sqlite_init
# ---------------------------------------------------------------------------
def test_init_connection_sets_wal_mode(tmp_path: Path):
    db = tmp_path / "x.db"
    conn = sqlite_init.open_connection(db)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.lower() == "wal"
        sync = conn.execute("PRAGMA synchronous").fetchone()[0]
        # NORMAL = 1
        assert int(sync) == 1
        fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert int(fk) == 1
    finally:
        conn.close()


def test_load_vec_extension_raises_clean_error_when_not_installed(tmp_path: Path,
                                                                  monkeypatch):
    """Wenn sqlite_vec nicht installiert ist, muss ImportError mit
    User-freundlicher Anweisung kommen — nicht ein generischer ModuleNotFoundError."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sqlite_vec":
            raise ImportError("simulated missing sqlite_vec")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    conn = sqlite3.connect(":memory:")
    try:
        with pytest.raises(ImportError) as exc_info:
            sqlite_init.load_vec_extension(conn)
        assert "sqlite-vec" in str(exc_info.value).lower()
        # Anweisung muss enthalten sein
        assert "pip install" in str(exc_info.value)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# migration_runner
# ---------------------------------------------------------------------------
def test_migrate_applies_scripts_in_order(tmp_path: Path):
    mig_dir = tmp_path / "mig"
    mig_dir.mkdir()
    (mig_dir / "001_first.sql").write_text(
        "CREATE TABLE t1 (id INTEGER PRIMARY KEY, value TEXT);"
    )
    (mig_dir / "002_second.sql").write_text(
        "CREATE TABLE t2 (id INTEGER PRIMARY KEY);"
    )

    db = tmp_path / "m.db"
    final_v = migrate(db, mig_dir)
    assert final_v == 2

    conn = sqlite3.connect(db)
    try:
        v = conn.execute("PRAGMA user_version").fetchone()[0]
        assert v == 2
        # Beide Tabellen existieren
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        assert {"t1", "t2"}.issubset(names)
    finally:
        conn.close()


def test_migrate_is_idempotent(tmp_path: Path):
    mig_dir = tmp_path / "mig"
    mig_dir.mkdir()
    (mig_dir / "001_init.sql").write_text("CREATE TABLE t (id INTEGER);")
    db = tmp_path / "i.db"

    v1 = migrate(db, mig_dir)
    v2 = migrate(db, mig_dir)
    assert v1 == v2 == 1


def test_migrate_failed_script_rolls_back(tmp_path: Path):
    mig_dir = tmp_path / "mig"
    mig_dir.mkdir()
    (mig_dir / "001_init.sql").write_text("CREATE TABLE t (id INTEGER);")
    (mig_dir / "002_broken.sql").write_text("THIS IS NOT VALID SQL;")

    db = tmp_path / "f.db"
    with pytest.raises(RuntimeError, match="002_broken"):
        migrate(db, mig_dir)

    # 001 muss durchgelaufen sein, 002 nicht
    conn = sqlite3.connect(db)
    try:
        v = conn.execute("PRAGMA user_version").fetchone()[0]
        assert v == 1
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# EmbeddingCache
# ---------------------------------------------------------------------------
def test_cache_lookup_miss_returns_none(isolated_appdata):
    cache = EmbeddingCache()
    assert cache.lookup(HASH_AUDIO, "model_x", "1.0") is None


def test_cache_store_and_lookup_round_trip(isolated_appdata):
    cache = EmbeddingCache()
    emb = np.random.randn(512).astype("float32")
    entry = cache.store(HASH_AUDIO, "audio", emb, "laion/larger_clap_music", "1.0")
    assert isinstance(entry, CacheEntry)
    assert entry.embedding_path.exists()

    found = cache.lookup(HASH_AUDIO, "laion/larger_clap_music", "1.0")
    assert found is not None
    loaded = found.load_embedding()
    assert loaded.shape == (512,)
    assert np.allclose(loaded, emb, atol=1e-6)


def test_cache_overwrite_updates_index(isolated_appdata):
    cache = EmbeddingCache()
    emb1 = np.zeros(512, dtype="float32")
    emb2 = np.ones(512, dtype="float32")
    cache.store(HASH_AUDIO, "audio", emb1, "model_x", "1.0")
    cache.store(HASH_AUDIO, "audio", emb2, "model_x", "1.0")
    e = cache.lookup(HASH_AUDIO, "model_x", "1.0")
    loaded = e.load_embedding()
    assert np.all(loaded == 1.0)


def test_cache_lookup_different_model_version_misses(isolated_appdata):
    """Plan-Doc 07 R07: model_version-Mismatch → cache miss → re-compute."""
    cache = EmbeddingCache()
    emb = np.zeros(512, dtype="float32")
    cache.store(HASH_AUDIO, "audio", emb, "model_x", "1.0")

    assert cache.lookup(HASH_AUDIO, "model_x", "2.0") is None
    assert cache.lookup(HASH_AUDIO, "model_y", "1.0") is None
    assert cache.lookup(HASH_AUDIO, "model_x", "1.0") is not None


def test_cache_stores_multiple_model_variants_for_same_media_hash(isolated_appdata):
    cache = EmbeddingCache()
    emb_v1 = np.zeros(512, dtype="float32")
    emb_v2 = np.ones(512, dtype="float32")

    entry_v1 = cache.store(HASH_AUDIO, "audio", emb_v1, "model_x", "1.0")
    entry_v2 = cache.store(HASH_AUDIO, "audio", emb_v2, "model_x", "2.0")

    found_v1 = cache.lookup(HASH_AUDIO, "model_x", "1.0")
    found_v2 = cache.lookup(HASH_AUDIO, "model_x", "2.0")

    assert found_v1 is not None
    assert found_v2 is not None
    assert np.all(found_v1.load_embedding() == 0.0)
    assert np.all(found_v2.load_embedding() == 1.0)
    assert entry_v1.embedding_path != entry_v2.embedding_path
    assert cache.stats()["total"] == 2


def test_cache_delete_removes_index_and_file(isolated_appdata):
    cache = EmbeddingCache()
    emb = np.zeros(512, dtype="float32")
    entry = cache.store(HASH_AUDIO, "audio", emb, "model_x", "1.0")
    assert entry.embedding_path.exists()

    deleted = cache.delete(HASH_AUDIO)
    assert deleted is True
    assert cache.lookup(HASH_AUDIO, "model_x", "1.0") is None
    assert not entry.embedding_path.exists()


def test_cache_delete_returns_false_for_unknown_hash(isolated_appdata):
    cache = EmbeddingCache()
    assert cache.delete(HASH_AUDIO) is False


def test_cache_stats(isolated_appdata):
    cache = EmbeddingCache()
    emb = np.zeros(512, dtype="float32")
    emb_v = np.zeros(768, dtype="float32")
    cache.store(HASH_AUDIO, "audio", emb, "clap", "1.0")
    cache.store(HASH_VIDEO, "video", emb_v, "siglip2", "1.0")

    s = cache.stats()
    assert s == {"total": 2, "audio": 1, "video": 1}


def test_cache_rejects_invalid_media_type(isolated_appdata):
    cache = EmbeddingCache()
    with pytest.raises(ValueError):
        cache.store(HASH_AUDIO, "image", np.zeros(512, dtype="float32"),
                    "x", "1.0")


def test_cache_rejects_wrong_hash_length(isolated_appdata):
    cache = EmbeddingCache()
    with pytest.raises(ValueError):
        cache.store("too_short", "audio", np.zeros(512, dtype="float32"),
                    "x", "1.0")


def test_cache_path_separates_audio_video_and_model(isolated_appdata):
    cache = EmbeddingCache()
    p_a = cache._path_for(HASH_AUDIO, "audio", "laion/larger_clap_music", "1.0")
    p_v = cache._path_for(HASH_VIDEO, "video", "google/siglip2-base", "1.0")
    assert "audio" in str(p_a) and "video" in str(p_v)
    # Slash → __ ersetzt fuer Filesystem-Sicherheit
    assert "laion__larger_clap_music__1.0" in str(p_a)
    assert "google__siglip2-base__1.0" in str(p_v)
