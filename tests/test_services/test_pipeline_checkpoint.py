"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17

T4.1: Checkpoint - Stage-Completion-Tracking ueberlappend mit stem_cache.
"""
from __future__ import annotations

from pathlib import Path
import pytest


def test_mark_stage_done_appends_to_stages_done(tmp_path, monkeypatch):
    from services.audio_pipeline import stem_cache, checkpoint
    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    checkpoint.mark_stage_done(track_id=1, stage_name="stem_gen")
    meta = stem_cache.load_cache_meta(track_id=1)
    assert "stem_gen" in meta.get("stages_done", [])


def test_mark_stage_done_idempotent(tmp_path, monkeypatch):
    from services.audio_pipeline import stem_cache, checkpoint
    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    checkpoint.mark_stage_done(track_id=1, stage_name="stem_gen")
    checkpoint.mark_stage_done(track_id=1, stage_name="stem_gen")
    meta = stem_cache.load_cache_meta(track_id=1)
    assert meta["stages_done"].count("stem_gen") == 1


def test_mark_stage_done_preserves_existing_meta(tmp_path, monkeypatch):
    from services.audio_pipeline import stem_cache, checkpoint
    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    stem_cache.save_cache_meta(1, {
        "version": 1,
        "original_hash": "abc",
        "stem_hashes": {"drums": "h"},
        "demucs_version": "htdemucs_ft",
        "wav_subtype": "PCM_24",
        "stages_done": ["stem_gen"],
    })
    checkpoint.mark_stage_done(track_id=1, stage_name="beat_grid")
    meta = stem_cache.load_cache_meta(1)
    assert meta["original_hash"] == "abc"
    assert "stem_gen" in meta["stages_done"]
    assert "beat_grid" in meta["stages_done"]


def test_is_stage_done(tmp_path, monkeypatch):
    from services.audio_pipeline import stem_cache, checkpoint
    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    assert checkpoint.is_stage_done(track_id=1, stage_name="stem_gen") is False
    checkpoint.mark_stage_done(track_id=1, stage_name="stem_gen")
    assert checkpoint.is_stage_done(track_id=1, stage_name="stem_gen") is True


def test_atomic_write_via_save_cache_meta(tmp_path, monkeypatch):
    """T4.1 atomic-write Pfad via stem_cache.save_cache_meta."""
    from services.audio_pipeline import stem_cache, checkpoint
    monkeypatch.setattr(stem_cache, "_STORAGE_ROOT", tmp_path)
    checkpoint.mark_stage_done(track_id=42, stage_name="lufs")
    final = stem_cache.cache_meta_path(42)
    assert final.exists()
    assert not final.with_suffix(final.suffix + ".tmp").exists()
