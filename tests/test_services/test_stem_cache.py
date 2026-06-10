"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17

T3.1: stem_cache - Audio-Hash + Stem-WAV-Hash + cache_meta_path.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest


def _write_bytes(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)


def test_compute_audio_hash_stable_for_same_file(tmp_path):
    from services.audio_pipeline.stem_cache import compute_audio_hash
    p = tmp_path / "a.wav"
    _write_bytes(p, b"x" * 50_000)
    h1 = compute_audio_hash(str(p))
    h2 = compute_audio_hash(str(p))
    assert h1 == h2
    assert isinstance(h1, str) and len(h1) == 64  # sha256 hex


def test_compute_audio_hash_changes_on_file_change(tmp_path):
    from services.audio_pipeline.stem_cache import compute_audio_hash
    p = tmp_path / "a.wav"
    _write_bytes(p, b"x" * 50_000)
    h1 = compute_audio_hash(str(p))
    _write_bytes(p, b"y" * 50_000)
    h2 = compute_audio_hash(str(p))
    assert h1 != h2


def test_compute_stem_wav_hash_distinct_symbol(tmp_path):
    """T3.1: compute_stem_wav_hash existiert als separate Funktion (Klarheit)."""
    from services.audio_pipeline.stem_cache import compute_stem_wav_hash
    p = tmp_path / "stem.wav"
    _write_bytes(p, b"z" * 50_000)
    h = compute_stem_wav_hash(str(p))
    assert isinstance(h, str) and len(h) == 64


def test_cache_meta_path_under_track_id(tmp_path, monkeypatch):
    from services.audio_pipeline import stem_cache
    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    p = stem_cache.cache_meta_path(track_id=42)
    assert str(p).endswith("42.json")
    assert "pipeline_state" in str(p)


def test_load_save_cache_meta_roundtrip(tmp_path, monkeypatch):
    from services.audio_pipeline import stem_cache
    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    data = {
        "version": 1,
        "original_hash": "abc",
        "stem_hashes": {"drums": "h1", "bass": "h2", "vocals": "h3", "other": "h4"},
        "demucs_version": "htdemucs_ft-v1",
        "wav_subtype": "PCM_24",
        "stages_done": ["stem_gen"],
    }
    stem_cache.save_cache_meta(track_id=1, meta=data)
    loaded = stem_cache.load_cache_meta(track_id=1)
    assert loaded == data


def test_load_cache_meta_returns_none_when_missing(tmp_path, monkeypatch):
    from services.audio_pipeline import stem_cache
    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    assert stem_cache.load_cache_meta(track_id=999) is None


def test_save_cache_meta_atomic_tmp_then_rename(tmp_path, monkeypatch):
    from services.audio_pipeline import stem_cache
    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    stem_cache.save_cache_meta(track_id=2, meta={"k": "v"})
    final = stem_cache.cache_meta_path(track_id=2)
    assert final.exists()
    # tmp wurde geraeumt
    tmp_path_candidate = final.with_suffix(final.suffix + ".tmp")
    assert not tmp_path_candidate.exists()
