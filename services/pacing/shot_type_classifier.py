"""Slice 2 / FR-S2-1: Shot-Type-Classifier.

16-Prompt-Ensemble × 4 Klassen. Klassen-Centroids werden einmal pro App-Start
über den SigLIP-Text-Tower (D-024) embedded und gecacht.
classify(clip_embedding, centroids) → softmax-Konfidenzen pro Klasse.

PRE-3-Refinement: Drum-Prompts auf non-human Motion umgeschrieben (vocal/
drum-Confusion war 0.725 cosine wegen menschlicher Subjekte in beiden
Klassen).
"""
from __future__ import annotations

from typing import Mapping

import numpy as np

EPS = 1e-9

SHOT_CLASSES: tuple[str, ...] = (
    "vocal_dominant",
    "drum_dominant",
    "melody_dominant",
    "bass_dominant",
)

# Mapping Stem-Name → Shot-Class. Wird in stem_class_bonus konsumiert.
STEM_TO_CLASS: dict[str, str] = {
    "vocals": "vocal_dominant",
    "drums": "drum_dominant",
    "other": "melody_dominant",  # Hinweis: 'other' ist kein eindeutiger Match
    "bass": "bass_dominant",
}


SHOT_PROMPTS: dict[str, list[str]] = {
    "vocal_dominant": [
        "human singer face close-up with microphone",
        "expressive vocalist mouth and eyes portrait",
        "front-lit performer singing into microphone",
        "intimate concert singer portrait shot",
    ],
    "drum_dominant": [
        # PRE-3 Refinement: keine Menschen, nur abstrakte Bewegung.
        "abstract light trails motion",
        "blurred neon lights in motion",
        "rapid camera movement abstract pattern",
        "kinetic geometric motion blur",
    ],
    "melody_dominant": [
        "wide cinematic landscape shot",
        "sweeping camera movement over scenery",
        "atmospheric environment with depth",
        "drone shot of expansive vista",
    ],
    "bass_dominant": [
        "dark heavy subwoofer speaker cone close-up",
        "massive low-frequency sound system wall",
        "deep bass vibration on speaker membrane",
        "black industrial sub bass cabinet texture",
    ],
}


def centroids_finite(centroids: Mapping[str, np.ndarray]) -> bool:
    """True wenn alle Centroids endlich (kein NaN/Inf)."""
    for v in centroids.values():
        if not np.all(np.isfinite(v)):
            return False
    return True


def classify(
    clip_embedding: np.ndarray,
    centroids: Mapping[str, np.ndarray],
) -> dict[str, float]:
    """Softmax-Konfidenzen pro Klasse.

    Args:
        clip_embedding: 1D-Vektor (idealerweise L2-normiert).
        centroids: dict[class_name, 1D-Vektor]. Klassen müssen SHOT_CLASSES
            entsprechen; Dimension muss zum clip_embedding passen.

    Returns:
        dict[class_name, prob] mit prob ∈ [0,1] und sum=1.
        Bei Zero-Embedding wird uniform (1/N) zurückgegeben.
    """
    if clip_embedding.ndim != 1:
        clip_embedding = clip_embedding.reshape(-1)
    n_classes = len(SHOT_CLASSES)

    # Dim-Check
    for cls in SHOT_CLASSES:
        if cls not in centroids:
            raise ValueError(f"Centroid für {cls!r} fehlt")
        if centroids[cls].shape[0] != clip_embedding.shape[0]:
            raise ValueError(
                f"dim mismatch: clip={clip_embedding.shape[0]}, "
                f"centroid[{cls}]={centroids[cls].shape[0]}"
            )

    norm_clip = float(np.linalg.norm(clip_embedding))
    if norm_clip < EPS:
        uniform = 1.0 / n_classes
        return {cls: uniform for cls in SHOT_CLASSES}

    sims = np.zeros(n_classes, dtype=np.float64)
    for i, cls in enumerate(SHOT_CLASSES):
        c = centroids[cls].astype(np.float64)
        nc = float(np.linalg.norm(c))
        if nc < EPS:
            sims[i] = 0.0
        else:
            sims[i] = float(np.dot(clip_embedding, c)) / (norm_clip * nc)

    # Softmax mit numerischer Stabilität
    sims -= sims.max()
    exp = np.exp(sims)
    probs = exp / exp.sum()
    return {cls: float(probs[i]) for i, cls in enumerate(SHOT_CLASSES)}
