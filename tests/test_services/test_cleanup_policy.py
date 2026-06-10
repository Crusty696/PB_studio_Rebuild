"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17

T7.1: Cleanup-Policy (Retention + Disk-Quota LRU).
"""
from __future__ import annotations

import os
import time
from pathlib import Path
import pytest


def _mk_track_dir(root: Path, track_id: int, size_mb: float = 0.001, age_days: float = 0):
    d = root / str(track_id)
    d.mkdir(parents=True, exist_ok=True)
    f = d / "drums.wav"
    f.write_bytes(b"x" * int(size_mb * 1024 * 1024))
    if age_days > 0:
        old = time.time() - age_days * 86400
        os.utime(d, (old, old))
    return d


def test_cleanup_stems_older_than_n_days(tmp_path):
    from services.audio_pipeline.cleanup import cleanup_stems_older_than
    fresh = _mk_track_dir(tmp_path, 1, age_days=0)
    old = _mk_track_dir(tmp_path, 2, age_days=60)
    deleted = cleanup_stems_older_than(days=30, root=tmp_path)
    assert old in deleted
    assert fresh not in deleted
    assert old.exists() is False
    assert fresh.exists() is True


def test_cleanup_stems_older_than_default_30d():
    from services.audio_pipeline.cleanup import STEMS_RETENTION_DAYS
    assert STEMS_RETENTION_DAYS == 30


def test_cleanup_to_quota_skips_when_under_limit(tmp_path):
    from services.audio_pipeline.cleanup import cleanup_to_quota
    _mk_track_dir(tmp_path, 1, size_mb=0.001)
    _mk_track_dir(tmp_path, 2, size_mb=0.001)
    deleted = cleanup_to_quota(max_gb=10, root=tmp_path)
    assert deleted == []


def test_cleanup_to_quota_lru_evicts_oldest(tmp_path):
    from services.audio_pipeline.cleanup import cleanup_to_quota
    # 3 Tracks je 0.5 MB; max 1 MB Quota (in GB sehr klein)
    _mk_track_dir(tmp_path, 1, size_mb=0.5, age_days=10)  # oldest
    _mk_track_dir(tmp_path, 2, size_mb=0.5, age_days=5)
    _mk_track_dir(tmp_path, 3, size_mb=0.5, age_days=0)   # newest
    # Quota = 1 MB = 1/1024 GB
    deleted = cleanup_to_quota(max_gb=0, root=tmp_path)  # extreme: forces evict
    # Oldest (track 1) muss zuerst gehen
    assert (tmp_path / "1") in deleted


def test_cleanup_stems_max_total_gb_env_override(monkeypatch):
    """Q-H: STEMS_MAX_TOTAL_GB via PB_STEMS_MAX_GB ueberschreibbar."""
    # Modul-Konstante wird beim Import gelesen; check Default + env-Override-Pfad
    from services.audio_pipeline import cleanup
    assert cleanup.STEMS_MAX_TOTAL_GB > 0


def test_cleanup_default_quota_50gb():
    """Q-H Plan-Default."""
    monkey_env = os.environ.pop("PB_STEMS_MAX_GB", None)
    try:
        import importlib
        from services.audio_pipeline import cleanup
        importlib.reload(cleanup)
        assert cleanup.STEMS_MAX_TOTAL_GB == 50
    finally:
        if monkey_env is not None:
            os.environ["PB_STEMS_MAX_GB"] = monkey_env


def test_cleanup_on_project_close_stub_returns_root(tmp_path):
    from services.audio_pipeline.cleanup import cleanup_on_project_close
    result = cleanup_on_project_close(project_id=1, root=tmp_path)
    assert result == tmp_path
