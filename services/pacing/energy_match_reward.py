"""Slice 1 / FR-S1-4: Energy-Curve-Match Reward.

Konvertiert die Cosine-Similarity zwischen Audio-RMS- und Video-Motion-
Curve in einen Reward ∈ [0, 1]. Wiederverwendet
`services.pacing.audio_video_curves.cosine_similarity_curves`.

Mapping: cos(-1) → 0.0, cos(0) → 0.5, cos(1) → 1.0. Silent-Curves
liefern 0.5 (neutral, statt false-positive 0.0).
"""
from __future__ import annotations

import numpy as np

from services.pacing.audio_video_curves import (
    EPS,
    align_lengths,
    cosine_similarity_curves,
)


def compute_energy_match_reward(
    rms: np.ndarray,
    motion: np.ndarray,
) -> float:
    """r_energy ∈ [0, 1].

    - silent (eine Curve all-zero): 0.5 (neutral)
    - perfekt aligned: 1.0
    - orthogonal: 0.5
    - perfekt anti-aligned: 0.0
    """
    if len(rms) == 0 or len(motion) == 0:
        return 0.5
    a, b = align_lengths(rms, motion)
    if float(np.linalg.norm(a)) < EPS or float(np.linalg.norm(b)) < EPS:
        return 0.5
    cos = cosine_similarity_curves(a, b)
    # Map [-1, 1] → [0, 1]
    return float(max(0.0, min(1.0, (cos + 1.0) / 2.0)))
