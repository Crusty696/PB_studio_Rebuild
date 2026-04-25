"""Slice 3 / FR-S3-2: Mood-Match-Score.

r_mood = (cos(audio_mood_vec, clip.caption_emb) + 1) / 2 ∈ [0, 1].
"""
from __future__ import annotations

import numpy as np

EPS = 1e-9


def compute_mood_match_score(
    audio_mood: np.ndarray,
    clip_caption_emb: np.ndarray,
) -> float:
    """Gemappte Cosine-Similarity ∈ [0, 1].

    - perfekt aligned → 1.0
    - orthogonal → 0.5
    - anti-aligned → 0.0
    - Zero-Vector → 0.5 (neutral)
    """
    if audio_mood.shape != clip_caption_emb.shape:
        raise ValueError(
            f"dim mismatch: audio_mood={audio_mood.shape}, "
            f"clip_caption_emb={clip_caption_emb.shape}"
        )
    a = audio_mood.astype(np.float64)
    b = clip_caption_emb.astype(np.float64)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < EPS or nb < EPS:
        return 0.5
    cos = float(np.dot(a, b) / (na * nb))
    return float(max(0.0, min(1.0, (cos + 1.0) / 2.0)))
