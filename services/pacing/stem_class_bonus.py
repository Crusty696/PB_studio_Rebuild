"""Slice 2 / FR-S2-2: Stem-Class-Bonus-Scorer.

Bonus +0.15 wenn die dominante Stem einer Section mit der Top-Shot-Klasse
des Kandidaten übereinstimmt UND die Klassen-Konfidenz ≥ min_confidence ist.
"""
from __future__ import annotations

from typing import Mapping

from services.pacing.shot_type_classifier import (
    SHOT_CLASSES,
    STEM_TO_CLASS,
)


def compute_stem_class_bonus(
    dominant_stem: str | None,
    shot_confidences: Mapping[str, float],
    bonus_amount: float = 0.15,
    min_confidence: float = 0.30,
) -> float:
    """0.0 oder bonus_amount.

    Args:
        dominant_stem: "vocals" / "drums" / "bass" / "other" / None.
            'other' triggert nie Bonus (kein eindeutiger Mapping).
        shot_confidences: Output von shot_type_classifier.classify().
        bonus_amount: Bonus-Höhe wenn Match.
        min_confidence: Mindest-Konfidenz für die Top-Klasse.

    Raises:
        ValueError: bei unbekanntem Stem-Namen.
    """
    if dominant_stem is None:
        return 0.0
    if dominant_stem == "other":
        return 0.0
    if dominant_stem not in STEM_TO_CLASS:
        raise ValueError(f"Unknown stem: {dominant_stem!r}")
    target_class = STEM_TO_CLASS[dominant_stem]
    top_class = max(shot_confidences, key=shot_confidences.get)
    if top_class != target_class:
        return 0.0
    if shot_confidences[top_class] < min_confidence:
        return 0.0
    return float(bonus_amount)
