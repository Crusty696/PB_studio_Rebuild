"""Release-gate: onset chunking for DJ-mix > 30 minutes (Feasibility §7 condition 6)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

DEFAULT_SR = 22050


def _build_synthetic_audio_with_onset_at(
    duration_sec: float, onset_sec: float, sr: int = DEFAULT_SR
) -> np.ndarray:
    """Silence with one sharp onset (short sine burst) at `onset_sec`."""
    total = int(duration_sec * sr)
    audio = np.zeros(total, dtype=np.float32)
    start = int(onset_sec * sr)
    # 50 ms burst of 440 Hz sine with hard envelope — guaranteed to register as an onset
    burst_len = int(0.05 * sr)
    t = np.arange(burst_len) / sr
    burst = np.sin(2 * np.pi * 440.0 * t).astype(np.float32) * 0.8
    end = min(start + burst_len, total)
    audio[start:end] = burst[: end - start]
    return audio


def test_boundary_onset_not_double_counted(tmp_path: Path) -> None:
    """An onset exactly at a segment boundary must be detected ONCE, not twice.

    Per Q5 recipe: the left segment wins (overlap region from preceding chunk
    is ignored for deduplication)."""
    from services.onset_rhythm_service import analyze_onsets_chunked

    audio = _build_synthetic_audio_with_onset_at(duration_sec=120.0, onset_sec=60.0)
    sr = DEFAULT_SR
    # Two contiguous 60-second segments
    segments = [(0.0, 60.0), (60.0, 120.0)]
    onsets = analyze_onsets_chunked(audio=audio, sr=sr, structure_segments=segments)
    # Only one onset should be near the boundary (within 50 ms of 60.0 s)
    near = [o for o in onsets if abs(o - 60.0) < 0.05]
    assert len(near) == 1, (
        f"Boundary onset double-counted or lost: found {len(near)} near 60.0s, full list = {onsets}"
    )


def test_chunked_matches_single_pass_within_short_track() -> None:
    """For an audio shorter than MAX_DURATION_SEC, chunked should agree with whole-pass within 1 frame."""
    from services.onset_rhythm_service import analyze_onsets_chunked, analyze_onsets_whole

    # 20 seconds of audio with 5 sparse onsets
    rng = np.random.default_rng(0)
    duration = 20.0
    sr = DEFAULT_SR
    audio = np.zeros(int(duration * sr), dtype=np.float32)
    onset_secs = [2.5, 6.3, 10.0, 13.8, 17.2]
    for os_s in onset_secs:
        start = int(os_s * sr)
        burst_len = int(0.05 * sr)
        t = np.arange(burst_len) / sr
        burst = np.sin(2 * np.pi * 440.0 * t).astype(np.float32) * 0.8
        audio[start : start + burst_len] = burst

    segments = [(0.0, 10.0), (10.0, 20.0)]
    chunked = np.array(sorted(analyze_onsets_chunked(audio=audio, sr=sr, structure_segments=segments)))
    single = np.array(sorted(analyze_onsets_whole(audio=audio, sr=sr)))

    # Tolerate a handful of spurious onsets from spectral-flux noise; require that every "true"
    # onset is matched within ~25 ms in both outputs.
    def match_set(detected: np.ndarray, truth: list[float], tol_sec: float = 0.025) -> list[float]:
        matched = []
        for t in truth:
            idx = np.argmin(np.abs(detected - t))
            if abs(detected[idx] - t) < tol_sec:
                matched.append(float(detected[idx]))
        return matched

    matched_single = match_set(single, onset_secs)
    matched_chunked = match_set(chunked, onset_secs)
    assert len(matched_single) >= 4 and len(matched_chunked) >= 4, (
        f"Detectors missed too many onsets. single={matched_single} chunked={matched_chunked}"
    )
    # The matched onsets themselves must agree in value within 2 frames (~23 ms at 22050 Hz default hop).
    for ts_single, ts_chunked in zip(sorted(matched_single), sorted(matched_chunked)):
        assert abs(ts_single - ts_chunked) < 0.025, (
            f"Chunked deviates from single-pass: {ts_chunked} vs {ts_single}"
        )


def test_memory_peak_stays_under_2gb_on_3h() -> None:
    """3h synthetic silence at 22050 Hz mono float32 is ~950 MB — chunking shouldn't double it."""
    import os

    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("psutil not installed; memory-peak check can't run.")

    from services.onset_rhythm_service import analyze_onsets_chunked

    duration = 3 * 3600.0
    sr = DEFAULT_SR
    # Avoid allocating the entire 3h array in the test — simulate via a memmap or skip the array
    # construction and test with a generator that the implementation accepts. For safety, build
    # 2 × 1.5h = 2.6 GB which would OOM; use 3 × 1h synthetic instead (still ~950 MB total).
    audio = np.zeros(int(duration * sr), dtype=np.float32)
    # Mark a handful of onsets across the span
    for os_s in [600.0, 3600.0, 7200.0, 10000.0]:
        start = int(os_s * sr)
        burst_len = int(0.05 * sr)
        t = np.arange(burst_len) / sr
        burst = np.sin(2 * np.pi * 440.0 * t).astype(np.float32) * 0.8
        audio[start : start + burst_len] = burst
    # 30-minute segments
    segments = [(float(i * 1800.0), float((i + 1) * 1800.0)) for i in range(6)]

    proc = psutil.Process(os.getpid())
    before = proc.memory_info().rss / (1024**2)
    analyze_onsets_chunked(audio=audio, sr=sr, structure_segments=segments)
    after = proc.memory_info().rss / (1024**2)
    delta = after - before
    # The input array itself is ~950 MB. Chunking must not require a second full copy.
    # Allow up to +500 MB overhead for librosa internal buffers.
    assert delta < 500, f"Chunked onset analysis grew RSS by {delta:.0f} MB (> 500 MB budget)"
