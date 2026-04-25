"""Slice 3 / FR-S3-4: Section-Coherence.

Innerhalb einer Section: hohe Mood-Sim → hoher Score (Coherence).
An Section-Boundary (boundary_distance_sec klein): NIEDRIGE Mood-Sim ist
gewünscht (Switch).

Ergebnis ∈ [0, 1].
"""
from __future__ import annotations

import numpy as np

EPS = 1e-9
BOUNDARY_BAND_SEC = 1.0  # Innerhalb dieses Bandes gilt Boundary-Logik


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na < EPS or nb < EPS:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def compute_section_coherence(
    prev_emb: np.ndarray | None,
    candidate_emb: np.ndarray,
    boundary_distance_sec: float,
    boundary_band_sec: float = BOUNDARY_BAND_SEC,
) -> float:
    """Score in [0, 1] — kombiniert Coherence-innerhalb mit Switch-an-Boundary.

    Im Section-Inneren (boundary_distance >= boundary_band):
        score = (cos + 1) / 2  → hohe Coherence belohnt
    An Boundary (boundary_distance < boundary_band):
        score = 1 - (cos + 1) / 2  → Switch belohnt

    Linear-blend zwischen beiden im Übergang.
    """
    if prev_emb is None:
        return 0.5
    cos = _cosine(prev_emb.astype(np.float64), candidate_emb.astype(np.float64))
    coh = (cos + 1.0) / 2.0
    switch = 1.0 - coh

    # Blend-Faktor: 0 (=ganz Boundary) ↔ 1 (=ganz Inneres)
    if boundary_band_sec <= 0:
        alpha = 1.0 if boundary_distance_sec >= 0 else 0.0
    else:
        alpha = min(1.0, max(0.0, boundary_distance_sec / boundary_band_sec))

    score = alpha * coh + (1.0 - alpha) * switch
    return float(max(0.0, min(1.0, score)))
