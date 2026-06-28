"""Smoke-Tests fuer VisualCurvesExtractor mit synthetischem Video.

Erzeugt ein 5-s-Video aus konstanten Frames (heller bzw. dunkler) und
verifiziert dass Brightness-Kurve sich entsprechend verhaelt.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_HAS_CV2 = importlib.util.find_spec("cv2") is not None

HASH64 = "b" * 64


def _write_synthetic_video(
    out_path: Path,
    n_frames: int,
    fps: int,
    frame_func,  # callable(idx) -> np.ndarray (H, W, 3) BGR uint8
    width: int = 64,
    height: int = 64,
) -> None:
    import cv2
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))
    try:
        for i in range(n_frames):
            writer.write(frame_func(i))
    finally:
        writer.release()


@pytest.fixture
def constant_bright_video(tmp_path: Path) -> Path:
    """5 s @ 10 fps, alle Frames hellgrau (180/255)."""
    if not _HAS_CV2:
        pytest.skip("opencv-python nicht installiert")
    out = tmp_path / "bright.mp4"
    _write_synthetic_video(
        out, n_frames=50, fps=10,
        frame_func=lambda i: np.full((64, 64, 3), 180, dtype=np.uint8),
    )
    return out


@pytest.fixture
def constant_dark_video(tmp_path: Path) -> Path:
    """5 s @ 10 fps, alle Frames dunkelgrau (40/255)."""
    if not _HAS_CV2:
        pytest.skip("opencv-python nicht installiert")
    out = tmp_path / "dark.mp4"
    _write_synthetic_video(
        out, n_frames=50, fps=10,
        frame_func=lambda i: np.full((64, 64, 3), 40, dtype=np.uint8),
    )
    return out


@pytest.fixture
def warm_video(tmp_path: Path) -> Path:
    """5 s @ 10 fps, alle Frames sehr rot (BGR (0, 50, 200) -> warm)."""
    if not _HAS_CV2:
        pytest.skip("opencv-python nicht installiert")
    out = tmp_path / "warm.mp4"
    def f(_i):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        frame[..., 0] = 30   # B niedrig
        frame[..., 1] = 50   # G
        frame[..., 2] = 200  # R hoch
        return frame
    _write_synthetic_video(out, n_frames=50, fps=10, frame_func=f)
    return out


@pytest.fixture
def cool_video(tmp_path: Path) -> Path:
    """5 s @ 10 fps, alle Frames sehr blau (BGR (200, 50, 30) -> kalt)."""
    if not _HAS_CV2:
        pytest.skip("opencv-python nicht installiert")
    out = tmp_path / "cool.mp4"
    def f(_i):
        frame = np.zeros((64, 64, 3), dtype=np.uint8)
        frame[..., 0] = 200  # B hoch
        frame[..., 1] = 50   # G
        frame[..., 2] = 30   # R niedrig
        return frame
    _write_synthetic_video(out, n_frames=50, fps=10, frame_func=f)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not _HAS_CV2, reason="opencv-python nicht installiert")
def test_extract_returns_correct_shape(constant_bright_video: Path):
    from services.brain.video.visual_curves import VisualCurvesExtractor
    ex = VisualCurvesExtractor(sample_rate_hz=1.0)
    res = ex.extract(constant_bright_video, video_hash=HASH64)

    assert res.video_hash == HASH64
    assert res.duration_seconds == pytest.approx(5.0, abs=0.5)
    # 5 s @ 1 Hz = 5 Samples
    assert 4 <= res.n_samples <= 6
    assert len(res.curves.brightness) == res.n_samples
    assert len(res.curves.saturation) == res.n_samples
    assert len(res.curves.color_temperature) == res.n_samples


@pytest.mark.skipif(not _HAS_CV2, reason="opencv-python nicht installiert")
def test_bright_video_has_high_brightness(constant_bright_video: Path):
    from services.brain.video.visual_curves import VisualCurvesExtractor
    ex = VisualCurvesExtractor()
    res = ex.extract(constant_bright_video, video_hash=HASH64)
    avg = np.mean([p.value for p in res.curves.brightness])
    assert avg > 0.6, f"180/255 Frame sollte brightness>0.6 ergeben, got {avg:.3f}"


@pytest.mark.skipif(not _HAS_CV2, reason="opencv-python nicht installiert")
def test_dark_video_has_low_brightness(constant_dark_video: Path):
    from services.brain.video.visual_curves import VisualCurvesExtractor
    ex = VisualCurvesExtractor()
    res = ex.extract(constant_dark_video, video_hash=HASH64)
    avg = np.mean([p.value for p in res.curves.brightness])
    assert avg < 0.3, f"40/255 Frame sollte brightness<0.3 ergeben, got {avg:.3f}"


@pytest.mark.skipif(not _HAS_CV2, reason="opencv-python nicht installiert")
def test_warm_video_has_positive_color_temp(warm_video: Path):
    """R/B>1 → log positiv → tanh positiv."""
    from services.brain.video.visual_curves import VisualCurvesExtractor
    ex = VisualCurvesExtractor()
    res = ex.extract(warm_video, video_hash=HASH64)
    avg = np.mean([p.value for p in res.curves.color_temperature])
    assert avg > 0.5, f"Warmer Frame sollte color_temp>0.5 ergeben, got {avg:.3f}"


@pytest.mark.skipif(not _HAS_CV2, reason="opencv-python nicht installiert")
def test_cool_video_has_negative_color_temp(cool_video: Path):
    """B/R>1 → log negativ → tanh negativ."""
    from services.brain.video.visual_curves import VisualCurvesExtractor
    ex = VisualCurvesExtractor()
    res = ex.extract(cool_video, video_hash=HASH64)
    avg = np.mean([p.value for p in res.curves.color_temperature])
    assert avg < -0.5, f"Kalter Frame sollte color_temp<-0.5 ergeben, got {avg:.3f}"


def test_invalid_sample_rate_rejected():
    from services.brain.video.visual_curves import VisualCurvesExtractor
    with pytest.raises(ValueError):
        VisualCurvesExtractor(sample_rate_hz=0.0)
    with pytest.raises(ValueError):
        VisualCurvesExtractor(sample_rate_hz=-1.0)


@pytest.mark.skipif(not _HAS_CV2, reason="opencv-python nicht installiert")
def test_metrics_computation_independent_of_io():
    """Direkt-Test der _compute_metrics-Statics ohne Video-IO."""
    import cv2
    from services.brain.video.visual_curves import VisualCurvesExtractor
    # Schwarz-Frame → brightness=0, saturation=0, color_temp ~0
    black = np.zeros((10, 10, 3), dtype=np.uint8)
    b, s, ct = VisualCurvesExtractor._compute_metrics(black, cv2)
    assert b == pytest.approx(0.0, abs=0.01)
    assert s == pytest.approx(0.0, abs=0.01)
    assert abs(ct) < 0.01

    # Weiss-Frame → brightness=1, saturation=0
    white = np.full((10, 10, 3), 255, dtype=np.uint8)
    b, s, ct = VisualCurvesExtractor._compute_metrics(white, cv2)
    assert b == pytest.approx(1.0, abs=0.01)
    assert s == pytest.approx(0.0, abs=0.05)
