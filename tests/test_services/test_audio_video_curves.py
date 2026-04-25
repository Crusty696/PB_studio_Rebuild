"""FR-S0-2 tests: audio_video_curves helper."""
import numpy as np

from services.pacing.audio_video_curves import (
    compute_audio_rms_curve,
    compute_motion_curve_from_scenes,
    cosine_similarity_curves,
    compute_curves,
    Curves,
    align_lengths,
)


class _Scene:
    def __init__(self, start_time, end_time, motion_score):
        self.start_time = start_time
        self.end_time = end_time
        self.motion_score = motion_score


def test_rms_curve_shape_100ms_bins():
    sr = 22050
    duration = 5.0
    samples = np.random.RandomState(42).standard_normal(int(sr * duration)).astype(np.float32)
    curve = compute_audio_rms_curve(samples, sr=sr, bin_ms=100)
    assert curve.dtype == np.float32
    assert curve.shape == (50,)  # 5 sec * 10 Hz
    assert 0.0 <= curve.min() and curve.max() <= 1.0


def test_rms_curve_silent_input_returns_zeros():
    sr = 22050
    samples = np.zeros(sr, dtype=np.float32)  # 1 sec silence
    curve = compute_audio_rms_curve(samples, sr=sr)
    assert curve.shape == (10,)
    assert curve.max() == 0.0


def test_motion_curve_from_scenes():
    scenes = [_Scene(0.0, 1.0, 0.3), _Scene(1.0, 2.5, 0.9), _Scene(2.5, 4.0, 0.1)]
    curve = compute_motion_curve_from_scenes(scenes, duration_sec=4.0, bin_ms=100)
    assert curve.shape == (40,)
    # Bin 5 (=0.5s) should have 0.3 normalized → 0.3/0.9 ≈ 0.333
    assert abs(curve[5] - 0.3 / 0.9) < 0.01
    # Bin 15 (=1.5s) should be 0.9 → normalized 1.0
    assert abs(curve[15] - 1.0) < 0.01
    # Bin 35 (=3.5s) should be 0.1 → normalized ≈ 0.111
    assert abs(curve[35] - 0.1 / 0.9) < 0.05


def test_align_lengths_truncates_to_min():
    a = np.arange(10, dtype=np.float32)
    b = np.arange(7, dtype=np.float32)
    a2, b2 = align_lengths(a, b)
    assert a2.shape == b2.shape == (7,)


def test_cosine_similarity_perfect_match():
    a = np.array([1.0, 0.5, 1.0, 0.0, 1.0], dtype=np.float32)
    sim = cosine_similarity_curves(a, a)
    assert abs(sim - 1.0) < 1e-6


def test_cosine_similarity_orthogonal():
    a = np.array([1.0, 0.0, 1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0, 0.0, 1.0], dtype=np.float32)
    sim = cosine_similarity_curves(a, b)
    assert abs(sim) < 1e-6


def test_cosine_similarity_silent_returns_zero():
    a = np.array([1.0, 1.0, 1.0], dtype=np.float32)
    b = np.zeros(3, dtype=np.float32)
    sim = cosine_similarity_curves(a, b)
    assert sim == 0.0


def test_compute_curves_integration():
    sr = 22050
    duration = 3.0
    samples = np.random.RandomState(7).standard_normal(int(sr * duration)).astype(np.float32)
    scenes = [_Scene(0.0, 1.5, 0.7), _Scene(1.5, 3.0, 0.4)]
    curves = compute_curves(samples, sr=sr, scene_infos=scenes, duration_sec=duration)
    assert isinstance(curves, Curves)
    assert curves.rms.shape == curves.motion.shape
    assert curves.bin_sec == 0.1


def test_compute_curves_deterministic():
    """Same input + seed → bit-identical output (NFR-5)."""
    sr = 22050
    samples = np.random.RandomState(123).standard_normal(sr).astype(np.float32)
    scenes = [_Scene(0.0, 1.0, 0.5)]
    c1 = compute_curves(samples, sr=sr, scene_infos=scenes, duration_sec=1.0)
    c2 = compute_curves(samples, sr=sr, scene_infos=scenes, duration_sec=1.0)
    assert np.array_equal(c1.rms, c2.rms)
    assert np.array_equal(c1.motion, c2.motion)
