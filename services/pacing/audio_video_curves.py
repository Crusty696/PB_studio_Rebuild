"""Foundation Slice 0 / FR-S0-2: Audio-RMS + Video-Motion Curves on common time grid.

Provides reusable helper for Slice 1 C.1 (Energy-Curve-Match-Reward) and
Slice 4 E.1 (Multi-Objective-Reward `r_energy` term).

Output: two numpy arrays of shape (N,) where N = ceil(duration_sec / bin_sec).
Both arrays are L1-normalized to [0, 1] within their own range.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

DEFAULT_BIN_MS = 100  # 10 Hz curves — fine enough for sub-beat alignment
EPS = 1e-9


@dataclass(frozen=True)
class Curves:
    rms: np.ndarray            # shape (N,), float32, [0, 1]
    motion: np.ndarray         # shape (N,), float32, [0, 1]
    bin_sec: float             # 0.1 by default
    duration_sec: float


def compute_audio_rms_curve(
    audio_samples: np.ndarray,
    sr: int,
    bin_ms: int = DEFAULT_BIN_MS,
) -> np.ndarray:
    """RMS-energy curve binned on `bin_ms`-grid, normalized to [0, 1]."""
    if audio_samples.ndim > 1:
        audio_samples = audio_samples.mean(axis=1)
    bin_samples = max(1, int(sr * bin_ms / 1000))
    n_bins = int(np.ceil(len(audio_samples) / bin_samples))
    if n_bins == 0:
        return np.zeros((0,), dtype=np.float32)

    padded = np.pad(audio_samples, (0, n_bins * bin_samples - len(audio_samples)))
    frames = padded.reshape(n_bins, bin_samples)
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1)).astype(np.float32)
    if rms.max() > EPS:
        rms = rms / rms.max()
    return rms


def compute_motion_curve_from_scenes(
    scene_infos: Sequence[object],
    duration_sec: float,
    bin_ms: int = DEFAULT_BIN_MS,
) -> np.ndarray:
    """Motion-score curve binned on `bin_ms`-grid.

    Each scene has `start_time`, `end_time`, `motion_score` (0..1).
    Bins inside a scene are filled with the scene's motion_score.
    Bins between scenes are 0.
    """
    bin_sec = bin_ms / 1000.0
    n_bins = max(1, int(np.ceil(duration_sec / bin_sec)))
    curve = np.zeros(n_bins, dtype=np.float32)

    for scene in scene_infos:
        start = float(getattr(scene, "start_time", 0.0))
        end = float(getattr(scene, "end_time", 0.0))
        score = float(getattr(scene, "motion_score", 0.0) or 0.0)
        i0 = max(0, int(start / bin_sec))
        i1 = min(n_bins, int(np.ceil(end / bin_sec)))
        if i1 > i0:
            curve[i0:i1] = score

    if curve.max() > EPS:
        curve = curve / curve.max()
    return curve


def align_lengths(rms: np.ndarray, motion: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Pad/truncate both arrays to the SAME length (use min)."""
    n = min(len(rms), len(motion))
    return rms[:n], motion[:n]


def cosine_similarity_curves(rms: np.ndarray, motion: np.ndarray) -> float:
    """Cosine sim between aligned curves. Returns 0.0 if either is silent."""
    if len(rms) == 0 or len(motion) == 0:
        return 0.0
    rms_a, motion_a = align_lengths(rms, motion)
    rms_n = np.linalg.norm(rms_a)
    mot_n = np.linalg.norm(motion_a)
    if rms_n < EPS or mot_n < EPS:
        return 0.0
    return float(np.dot(rms_a, motion_a) / (rms_n * mot_n))


def compute_curves(
    audio_samples: np.ndarray,
    sr: int,
    scene_infos: Sequence[object],
    duration_sec: float,
    bin_ms: int = DEFAULT_BIN_MS,
) -> Curves:
    """Convenience: build both curves on common grid + return Curves dataclass."""
    rms = compute_audio_rms_curve(audio_samples, sr, bin_ms)
    motion = compute_motion_curve_from_scenes(scene_infos, duration_sec, bin_ms)
    rms, motion = align_lengths(rms, motion)
    return Curves(rms=rms, motion=motion, bin_sec=bin_ms / 1000.0, duration_sec=duration_sec)
