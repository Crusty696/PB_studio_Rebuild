"""Slice 3 / FR-S3-1: Audio-Mood-Vector.

Liefert einen 1152-dim Vektor im SigLIP-Embedding-Raum, der den Mood
einer Section zusammenfasst. Berechnet als gewichtete Linear-Kombination
der 4 Shot-Klassen-Centroids (FR-S2-1) — die Stem-Verteilung gibt die
Gewichte vor — plus ein optionaler Section-Type-Bias.

Output ist L2-normalisiert (cos-similarity-kompatibel zum Image-Tower).
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

from services.pacing.shot_type_classifier import (
    SHOT_CLASSES,
    STEM_TO_CLASS,
)

EPS = 1e-9

# Section-Bias auf einzelne Klassen — Hintergrund: Drops verlangen Drum-Shots,
# Build-Ups eher Vocal/Melody-Shots, etc.
_SECTION_BIAS: dict[str, dict[str, float]] = {
    "drop": {"drum_dominant": 0.30, "bass_dominant": 0.10},
    "buildup": {"vocal_dominant": 0.20, "melody_dominant": 0.20},
    "build_up": {"vocal_dominant": 0.20, "melody_dominant": 0.20},
    "chorus": {"vocal_dominant": 0.20},
    "verse": {"vocal_dominant": 0.10, "melody_dominant": 0.05},
    "intro": {"melody_dominant": 0.20},
    "outro": {"melody_dominant": 0.15},
    "breakdown": {"melody_dominant": 0.20, "vocal_dominant": 0.05},
    "bridge": {"melody_dominant": 0.10},
    "transition": {},
}


def compute_audio_mood_vector(
    stem_energies: Mapping[str, float],
    section_type: str | None,
    centroids: Mapping[str, np.ndarray],
) -> np.ndarray:
    """Gewichtete Centroid-Mittelung → L2-normiert.

    Args:
        stem_energies: {"vocals": .., "drums": .., "bass": .., "other": ..}.
        section_type: Section-Typ (case-insensitive); steuert _SECTION_BIAS.
        centroids: {class_name: 1152-dim Vektor} aus shot_type_classifier.

    Returns:
        np.ndarray(1152,) float32, L2-norm == 1.
    """
    # Stem → Class-Weights aufsetzen
    class_weights = {cls: 0.0 for cls in SHOT_CLASSES}
    if stem_energies:
        total = float(sum(stem_energies.values())) + EPS
        for stem_name, energy in stem_energies.items():
            cls = STEM_TO_CLASS.get(stem_name)
            if cls is None or cls not in class_weights:
                continue
            class_weights[cls] += float(energy) / total

    # Section-Bias dazu addieren
    if section_type:
        key = section_type.strip().lower().replace("-", "_")
        for cls, bias in _SECTION_BIAS.get(key, {}).items():
            class_weights[cls] += float(bias)

    # Linear-Kombination der Centroids
    dim = next(iter(centroids.values())).shape[0]
    out = np.zeros(dim, dtype=np.float64)
    weight_sum = 0.0
    for cls in SHOT_CLASSES:
        w = class_weights[cls]
        if w <= 0.0:
            continue
        c = centroids[cls].astype(np.float64)
        out += w * c
        weight_sum += w

    if weight_sum < EPS:
        # Fallback: uniform mean
        for cls in SHOT_CLASSES:
            out += centroids[cls].astype(np.float64)
        weight_sum = float(len(SHOT_CLASSES))

    out /= weight_sum
    norm = float(np.linalg.norm(out))
    if norm < EPS:
        # Degenerate centroids → unit-vector
        out = np.zeros(dim, dtype=np.float64)
        out[0] = 1.0
        norm = 1.0
    out /= norm
    return out.astype(np.float32)
