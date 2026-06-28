"""Tests fuer services.brain.storage.media_hash_registry (Phase 1 App-Sync).

CPU-only, isoliertes APPDATA via tmp_path.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from services.brain.storage.media_hash_registry import (
    MediaHashRegistry,
    HashEntry,
    RegistrationResult,
)


@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    yield tmp_path


@pytest.fixture
def sample_audio(tmp_path: Path) -> Path:
    p = tmp_path / "sample_audio.wav"
    p.write_bytes(b"RIFF\x00\x00\x00\x00WAVE" + b"\xab" * 1024)
    return p


@pytest.fixture
def sample_video(tmp_path: Path) -> Path:
    p = tmp_path / "sample_video.mp4"
    p.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\xcd" * 2048)
    return p


def test_register_new_audio_returns_is_new_true(isolated_appdata, sample_audio):
    reg = MediaHashRegistry()
    result = reg.register(sample_audio, "audio")
    assert isinstance(result, RegistrationResult)
    assert result.is_new is True
    assert isinstance(result.entry, HashEntry)
    assert result.entry.media_type == "audio"
    assert len(result.entry.media_hash) == 64
    assert result.entry.file_size_bytes == sample_audio.stat().st_size
    assert result.entry.source_path == str(sample_audio.resolve())


def test_register_same_file_twice_returns_is_new_false(isolated_appdata, sample_audio):
    reg = MediaHashRegistry()
    first = reg.register(sample_audio, "audio")
    second = reg.register(sample_audio, "audio")
    assert first.is_new is True
    assert second.is_new is False
    assert first.entry.media_hash == second.entry.media_hash


def test_lookup_returns_entry_after_register(isolated_appdata, sample_video):
    reg = MediaHashRegistry()
    result = reg.register(sample_video, "video")
    found = reg.lookup(result.entry.media_hash)
    assert found is not None
    assert found.media_hash == result.entry.media_hash
    assert found.media_type == "video"


def test_lookup_returns_none_for_unknown_hash(isolated_appdata):
    reg = MediaHashRegistry()
    assert reg.lookup("0" * 64) is None


def test_lookup_by_path_returns_entry(isolated_appdata, sample_audio):
    reg = MediaHashRegistry()
    reg.register(sample_audio, "audio")
    found = reg.lookup_by_path(sample_audio)
    assert found is not None
    assert found.source_path == str(sample_audio.resolve())


def test_invalid_media_type_raises(isolated_appdata, sample_audio):
    reg = MediaHashRegistry()
    with pytest.raises(ValueError):
        reg.register(sample_audio, "image")


def test_stats_counts_audio_and_video(isolated_appdata, sample_audio, sample_video):
    reg = MediaHashRegistry()
    reg.register(sample_audio, "audio")
    reg.register(sample_video, "video")
    stats = reg.stats()
    assert stats == {"total": 2, "audio": 1, "video": 1}


def test_migration_creates_media_hashes_table(isolated_appdata, sample_audio):
    reg = MediaHashRegistry()
    reg.register(sample_audio, "audio")
    import sqlite3
    conn = sqlite3.connect(str(reg.db_path))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='media_hashes'"
        ).fetchall()
        assert rows, "media_hashes table should exist after first register()"
        cols = {r[1] for r in conn.execute("PRAGMA table_info(media_hashes)")}
        assert {"media_hash", "media_type", "source_path",
                "file_size_bytes", "computed_at"} <= cols
    finally:
        conn.close()


def test_register_same_content_different_path_idempotent(isolated_appdata, tmp_path):
    """Identischer Inhalt → identischer Hash → is_new=False beim 2. Pfad."""
    content = b"identical-bytes-" * 256
    p1 = tmp_path / "first.wav"
    p2 = tmp_path / "second.wav"
    p1.write_bytes(content)
    p2.write_bytes(content)
    reg = MediaHashRegistry()
    r1 = reg.register(p1, "audio")
    r2 = reg.register(p2, "audio")
    assert r1.is_new is True
    assert r2.is_new is False
    assert r1.entry.media_hash == r2.entry.media_hash
