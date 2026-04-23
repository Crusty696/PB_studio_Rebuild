"""
Unit tests for scripts/build_test_fixture.py

Six plan-spec'd tests (T0.1a):
1. test_rms_variance_window_picks_dynamic_segment
2. test_beat_snap_aligns_to_downbeat
3. test_kmeans_clip_selection_covers_all_clusters
4. test_fallback_heuristic_uses_duration_motion_grid
5. test_deterministic_with_fixed_seed
6. test_dry_run_does_not_write_files
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.build_test_fixture import (
    AudioWindow,
    ClipInfo,
    select_audio_window_by_rms,
    select_clips_by_heuristic,
    select_clips_by_kmeans,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SR = 22050  # sample rate used throughout tests


def make_synthetic_audio(
    minutes: float,
    loud_range: tuple[float, float],
    sr: int = SR,
    loud_amplitude: float = 0.8,
    quiet_amplitude: float = 0.01,
) -> np.ndarray:
    """Return a float32 mono array of *minutes* duration.

    Everything outside *loud_range* (start_sec, end_sec) is near-silence;
    the region inside is a sine burst at *loud_amplitude*.
    """
    total_samples = int(minutes * 60 * sr)
    audio = np.full(total_samples, quiet_amplitude, dtype=np.float32)
    start_s, end_s = loud_range
    start_idx = int(start_s * sr)
    end_idx = int(end_s * sr)
    t = np.linspace(0, end_s - start_s, end_idx - start_idx, endpoint=False)
    audio[start_idx:end_idx] = (loud_amplitude * np.sin(2 * np.pi * 440 * t)).astype(
        np.float32
    )
    return audio


# ---------------------------------------------------------------------------
# Test 1 — RMS-variance window picks the dynamic segment
# ---------------------------------------------------------------------------


def test_rms_variance_window_picks_dynamic_segment(tmp_path: Path) -> None:
    """Synthetic audio: 55 min silence + 5 min loud burst → window locates the burst."""
    audio = make_synthetic_audio(minutes=60, loud_range=(50 * 60, 55 * 60))
    seg = select_audio_window_by_rms(audio, sr=SR, length_sec=300)
    # The selected window must start somewhere in the loud region
    assert (
        50 * 60 <= seg.start_sec <= 51 * 60
    ), f"Expected start in [3000, 3060] but got {seg.start_sec}"


# ---------------------------------------------------------------------------
# Test 2 — Beat-snap aligns window boundaries to detected beats
# ---------------------------------------------------------------------------


def test_beat_snap_aligns_to_downbeat() -> None:
    """Picked window start/end are within 50 ms of a detected beat."""
    import librosa

    # 120 BPM sine-drum tone — clear enough for beat tracker
    duration_sec = 60.0
    t = np.linspace(0, duration_sec, int(SR * duration_sec), endpoint=False)
    # One loud click every 0.5 s (120 BPM)
    beat_positions = np.arange(0, duration_sec, 0.5)
    audio = np.zeros_like(t)
    for bp in beat_positions:
        idx = int(bp * SR)
        if idx < len(audio):
            audio[idx : idx + 100] += 0.9  # short click

    audio = audio.astype(np.float32)
    seg = select_audio_window_by_rms(audio, sr=SR, length_sec=30)

    # Detect beats to verify snapping
    tempo, beat_frames = librosa.beat.beat_track(y=audio, sr=SR)
    beat_times = librosa.frames_to_time(beat_frames, sr=SR)

    if len(beat_times) == 0:
        pytest.skip("Beat tracker found no beats in synthetic audio — skip")

    def min_dist_to_beats(t: float) -> float:
        return float(np.min(np.abs(beat_times - t)))

    start_dist = min_dist_to_beats(seg.start_sec)
    end_dist = min_dist_to_beats(seg.end_sec)

    assert start_dist <= 0.05, f"Start not snapped: {start_dist:.4f}s off nearest beat"
    assert end_dist <= 0.05, f"End not snapped: {end_dist:.4f}s off nearest beat"


# ---------------------------------------------------------------------------
# Test 3 — K-means clip selection covers all clusters
# ---------------------------------------------------------------------------


def test_kmeans_clip_selection_covers_all_clusters() -> None:
    """Given 60 embeddings in 6 Gaussian clusters → 20-clip pick has >=3 per cluster."""
    rng = np.random.default_rng(42)
    n_clusters = 6
    n_per_cluster = 10
    dim = 64  # smaller than SigLIP 1152 but enough to test logic

    # Build well-separated clusters (large spread so k-means finds them cleanly)
    centers = rng.standard_normal((n_clusters, dim)) * 20.0
    embeddings = np.concatenate(
        [rng.standard_normal((n_per_cluster, dim)) * 0.1 + c for c in centers]
    )
    # True Gaussian group for each of the 60 embeddings
    labels_true = np.repeat(np.arange(n_clusters), n_per_cluster)

    clip_count = 20
    selected_indices = select_clips_by_kmeans(
        embeddings=embeddings,
        clip_count=clip_count,
        seed=42,
        n_clusters=n_clusters,
    )

    assert (
        len(selected_indices) == clip_count
    ), f"Expected {clip_count} clips, got {len(selected_indices)}"

    # Map selected indices back to their Gaussian group (not k-means cluster ID).
    # With very tight clusters (std=0.1) and large center separation (scale=20),
    # k-means will discover exactly the 6 Gaussian groups, so this is a valid check.
    selected_gaussian_groups = labels_true[selected_indices]
    counts_per_group = {
        g: int(np.sum(selected_gaussian_groups == g)) for g in range(n_clusters)
    }

    for group_id, count in counts_per_group.items():
        assert count >= 3, (
            f"Gaussian group {group_id} has only {count} clips in selection (expected >= 3). "
            f"Distribution: {counts_per_group}"
        )


# ---------------------------------------------------------------------------
# Test 4 — Fallback heuristic uses duration×motion grid
# ---------------------------------------------------------------------------


def test_fallback_heuristic_uses_duration_motion_grid() -> None:
    """Without DB entries, 3x3 bucket sampling produces varied duration+motion."""
    rng = np.random.default_rng(7)

    # Build 27 synthetic ClipInfo entries spread across the 3x3 grid
    clips: list[ClipInfo] = []
    for dur_tier in range(3):  # 0=short, 1=medium, 2=long
        for mot_tier in range(3):  # 0=low, 1=medium, 2=high
            for _ in range(3):  # 3 per cell → 27 total
                duration = (dur_tier * 10.0 + 2.0) + rng.uniform(0, 5)
                motion = mot_tier / 2.0 + rng.uniform(-0.1, 0.1)
                motion = float(np.clip(motion, 0.0, 1.0))
                clips.append(
                    ClipInfo(
                        path=Path(f"/fake/clip_{dur_tier}_{mot_tier}_{_}.mp4"),
                        duration=duration,
                        motion=motion,
                        resolution=(1920, 1080),
                    )
                )

    selected = select_clips_by_heuristic(clips=clips, clip_count=9, seed=42)

    assert len(selected) == 9, f"Expected 9 clips, got {len(selected)}"

    # Check varied durations and motions (not all from same bucket)
    durations = [c.duration for c in selected]
    motions = [c.motion for c in selected]

    dur_range = max(durations) - min(durations)
    mot_range = max(motions) - min(motions)

    assert (
        dur_range > 5.0
    ), f"Duration range too narrow ({dur_range:.2f}s) — heuristic not sampling diverse buckets"
    assert (
        mot_range > 0.3
    ), f"Motion range too narrow ({mot_range:.2f}) — heuristic not sampling diverse motion tiers"


# ---------------------------------------------------------------------------
# Test 5 — Deterministic with fixed seed
# ---------------------------------------------------------------------------


def test_deterministic_with_fixed_seed(tmp_path: Path) -> None:
    """Two runs with seed=42 produce identical selection_report.md contents."""
    import soundfile as sf

    from scripts.build_test_fixture import run_fixture_build

    # Create a minimal synthetic WAV (10 seconds)
    sr = SR
    duration = 10
    t = np.linspace(0, duration, sr * duration, endpoint=False).astype(np.float32)
    audio_data = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    audio_path = tmp_path / "test_mix.wav"
    sf.write(str(audio_path), audio_data, sr)

    # Create a fake clips folder with 5 minimal files
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    for i in range(5):
        clip_path = clips_dir / f"clip_{i:02d}.mp4"
        clip_path.write_bytes(
            b"FAKEMPEGDATA" + bytes([i])
        )  # not a real mp4 but path exists

    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"

    # Run twice with same seed
    for out_dir in (out1, out2):
        run_fixture_build(
            audio_path=audio_path,
            clips_folder=clips_dir,
            audio_length=8,
            clip_count=3,
            seed=42,
            output_dir=out_dir,
            dry_run=False,
        )

    report1 = (out1 / "golden_mix" / "selection_report.md").read_text()
    report2 = (out2 / "golden_mix" / "selection_report.md").read_text()

    assert report1 == report2, (
        "Audio selection_report.md differs between two runs with same seed!\n"
        f"Run 1:\n{report1}\n\nRun 2:\n{report2}"
    )

    clips_report1 = (out1 / "clips_3" / "selection_report.md").read_text()
    clips_report2 = (out2 / "clips_3" / "selection_report.md").read_text()

    assert (
        clips_report1 == clips_report2
    ), "Clips selection_report.md differs between two runs with same seed!"


# ---------------------------------------------------------------------------
# Test 6 — K-means determinism across calls
# ---------------------------------------------------------------------------


def test_kmeans_determinism_on_numpy_arrays() -> None:
    """Two calls to select_clips_by_kmeans with identical inputs + seed return identical index lists."""
    rng = np.random.default_rng(0)
    embeddings = rng.standard_normal((60, 1152)).astype(np.float32)
    result_a = select_clips_by_kmeans(
        embeddings=embeddings, clip_count=20, seed=42, n_clusters=6
    )
    result_b = select_clips_by_kmeans(
        embeddings=embeddings, clip_count=20, seed=42, n_clusters=6
    )
    assert (
        result_a == result_b
    ), "k-means selection is not deterministic across calls with same seed"
    assert len(result_a) == 20, f"Expected 20 clips, got {len(result_a)}"


# ---------------------------------------------------------------------------
# Test 7 — Dry-run does not write files
# ---------------------------------------------------------------------------


def test_dry_run_does_not_write_files(tmp_path: Path) -> None:
    """--dry-run prints the plan but creates no files in --output-dir."""
    import soundfile as sf

    from scripts.build_test_fixture import run_fixture_build

    sr = SR
    duration = 10
    t = np.linspace(0, duration, sr * duration, endpoint=False).astype(np.float32)
    audio_data = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)

    audio_path = tmp_path / "dry_mix.wav"
    sf.write(str(audio_path), audio_data, sr)

    clips_dir = tmp_path / "dry_clips"
    clips_dir.mkdir()
    for i in range(4):
        (clips_dir / f"clip_{i}.mp4").write_bytes(b"FAKEMP4" + bytes([i]))

    output_dir = tmp_path / "dry_output"
    # output_dir intentionally NOT created — dry-run must not create it

    run_fixture_build(
        audio_path=audio_path,
        clips_folder=clips_dir,
        audio_length=8,
        clip_count=3,
        seed=42,
        output_dir=output_dir,
        dry_run=True,
    )

    # Nothing should have been written
    assert (
        not output_dir.exists()
    ), f"--dry-run must not create output_dir, but it was created at {output_dir}"
