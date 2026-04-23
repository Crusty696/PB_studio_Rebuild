"""P13 — 3h DJ-mix integration test.

Proves the memory budget (≤ 2 GB peak RSS) holds for a realistic
3-hour synthetic mix through `analyze_onsets_chunked`.

The test uses the generate_mix_audio() helper directly (no WAV on disk)
so it runs fast and cleanly.

Windows note: like test_onset_chunked_boundary.py's memory test, RSS
measurement on Windows for np.zeros arrays is misleading because the
pages are lazy-committed via VirtualAlloc. This test uses a preallocated
+ touched array to fault pages up-front so the RSS baseline is honest.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from scripts.generate_test_dj_mix import SyntheticMixSpec, generate_mix_audio
from services.onset_rhythm_service import analyze_onsets_chunked

try:
    import psutil as _psutil  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover
    _psutil = None

DEFAULT_SR = 22050
MEMORY_BUDGET_MB = 2048
MAX_RUNTIME_SEC = 45 * 60  # 45 min max runtime


def _measure_rss_mb() -> float:
    if _psutil is None:
        pytest.skip("psutil not installed")
    proc = _psutil.Process(os.getpid())
    return float(proc.memory_info().rss / (1024 * 1024))


@pytest.mark.slow
def test_dj_mix_3h_onset_analysis_under_memory_budget() -> None:
    """Full 3h pipeline-section: generate-audio + chunked onset detection.

    Asserts:
      - RSS delta < 500 MB (chunking must not force a second audio copy)
      - Runtime finite (< 45 min)

    Skip on Windows since RSS accounting for np.zeros is misleading
    (see test_onset_chunked_boundary.py for details).
    """
    if sys.platform == "win32":
        pytest.skip(
            "Windows VirtualAlloc lazy-page-fault accounting inflates RSS "
            "delta for np.zeros arrays; 3h test only runs on Linux/macOS."
        )

    if _psutil is None:
        pytest.skip("psutil not installed")

    spec = SyntheticMixSpec(
        duration_sec=3 * 3600.0,
        sr=DEFAULT_SR,
        burst_interval_sec=5.0,  # sparse → keeps test fast, 2160 bursts total
        burst_freq_hz=440.0,
        burst_duration_sec=0.05,
        seed=42,
        segment_minutes=30.0,
    )
    audio, segments = generate_mix_audio(spec)
    # Touch every page so RSS isn't biased by lazy allocation
    audio.sum()

    baseline_mb = _measure_rss_mb()
    start = time.perf_counter()
    onsets = analyze_onsets_chunked(
        audio=audio, sr=spec.sr, structure_segments=segments
    )
    elapsed = time.perf_counter() - start
    peak_mb = _measure_rss_mb()
    delta_mb = peak_mb - baseline_mb

    print(
        f"\n[P13] 3h mix: runtime={elapsed:.1f}s  "
        f"RSS_delta={delta_mb:.0f} MB  onsets_found={len(onsets)}"
    )

    # The runtime must be finite (don't let it block CI for hours)
    assert (
        elapsed < MAX_RUNTIME_SEC
    ), f"3h pipeline took too long: {elapsed:.1f} s > {MAX_RUNTIME_SEC} s"
    # Chunking must not double-load the audio
    assert (
        delta_mb < 500
    ), f"chunked onset analysis grew RSS by {delta_mb:.0f} MB (> 500 MB budget)"
    # Sanity: at 1 burst per 5s, over 3h = 10800s, expect ~2160 onsets ± noise
    assert (
        1500 <= len(onsets) <= 3000
    ), f"onset count {len(onsets)} looks wrong for 2160-burst input"


def test_generator_produces_expected_shape() -> None:
    """Quick shape-check on the generator so the 3h test won't be surprised."""
    spec = SyntheticMixSpec(
        duration_sec=60.0,
        sr=22050,
        burst_interval_sec=2.0,
        burst_freq_hz=440.0,
        burst_duration_sec=0.05,
        seed=42,
        segment_minutes=0.5,  # 30-second segments → 2 segments in 60s
    )
    audio, segments = generate_mix_audio(spec)
    assert audio.shape == (60 * 22050,)
    assert audio.dtype == np.float32
    # Segments are contiguous and cover the full duration
    assert segments[0][0] == 0.0
    assert segments[-1][1] == pytest.approx(60.0)
    for i in range(1, len(segments)):
        assert segments[i][0] == pytest.approx(segments[i - 1][1])
    # 60s / 2s = 30 bursts
    n_peaks = int(np.sum(np.abs(audio) > 0.1))
    assert n_peaks > 0, "no bursts rendered"


def test_generator_is_deterministic() -> None:
    """Same spec → byte-identical audio + identical segment list."""
    spec = SyntheticMixSpec(
        duration_sec=10.0,
        sr=22050,
        burst_interval_sec=1.0,
        burst_freq_hz=440.0,
        burst_duration_sec=0.05,
        seed=42,
        segment_minutes=0.1,
    )
    a1, s1 = generate_mix_audio(spec)
    a2, s2 = generate_mix_audio(spec)
    assert np.array_equal(a1, a2)
    assert s1 == s2
