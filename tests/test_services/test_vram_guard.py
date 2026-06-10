"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17

T6.1 + T6.2: VRAM-Guard + adaptive chunk + Floor (R-10).
"""
from __future__ import annotations

from unittest.mock import patch
import pytest


def test_get_free_vram_mb_returns_none_when_cuda_unavailable():
    from services.audio_pipeline.vram_guard import get_free_vram_mb
    with patch("torch.cuda.is_available", return_value=False):
        assert get_free_vram_mb() is None


def test_assert_vram_available_passes_when_enough_free():
    from services.audio_pipeline.vram_guard import assert_vram_available
    with patch("services.audio_pipeline.vram_guard.get_free_vram_mb", return_value=5000):
        assert_vram_available(min_free_mb=4500)  # darf nicht raisen


def test_assert_vram_available_raises_when_below_threshold():
    from services.audio_pipeline.vram_guard import assert_vram_available, VRAMExhaustedError
    with patch("services.audio_pipeline.vram_guard.get_free_vram_mb", return_value=2000):
        with pytest.raises(VRAMExhaustedError):
            assert_vram_available(min_free_mb=4500)


def test_assert_vram_available_noop_when_cuda_unavailable():
    """CPU-Fallback: kein VRAM-Check -> no-op."""
    from services.audio_pipeline.vram_guard import assert_vram_available
    with patch("services.audio_pipeline.vram_guard.get_free_vram_mb", return_value=None):
        assert_vram_available(min_free_mb=4500)


def test_compute_adaptive_chunk_keeps_default_when_vram_ok():
    from services.audio_pipeline.vram_guard import compute_adaptive_chunk_seconds
    assert compute_adaptive_chunk_seconds(30.0, free_vram_mb=5000) == 30.0


def test_compute_adaptive_chunk_halves_on_vram_pressure():
    from services.audio_pipeline.vram_guard import compute_adaptive_chunk_seconds
    assert compute_adaptive_chunk_seconds(30.0, free_vram_mb=2000) == 15.0


def test_compute_adaptive_chunk_respects_floor():
    """R-10: nicht unter 15s (Demucs htdemucs_ft Receptive Field)."""
    from services.audio_pipeline.vram_guard import compute_adaptive_chunk_seconds, STEM_CHUNK_MIN_SECONDS
    # default 20s -> halved 10s waere < floor 15s -> clamped auf 15s
    result = compute_adaptive_chunk_seconds(20.0, free_vram_mb=2000)
    assert result >= STEM_CHUNK_MIN_SECONDS


def test_chunk_floor_default_is_15s():
    from services.audio_pipeline.vram_guard import STEM_CHUNK_MIN_SECONDS
    assert STEM_CHUNK_MIN_SECONDS == 15
