"""Audit-Regression: leeres shot_confidences darf den Auto-Edit nicht killen.

Ohne den Fix warf ``compute_stem_class_bonus`` ``max() arg is an empty
sequence``, sobald eine Section eine dominante Stem hatte und der Kandidat
keine Shot-Konfidenzen mitbrachte (SigLIP nicht ladbar -> ``{}`` aus
``shot_centroids.get_shot_class_centroids``).  Die Exception verliess
``PacingScorer.score`` und damit ``select_best``; der Legacy-Fallback in
``pacing_service`` faengt nur (ImportError, RuntimeError, AttributeError,
KeyError) und greift deshalb nicht.
"""
from __future__ import annotations

import numpy as np

from services.pacing.scorer import AudioContext, ClipFeatures, PacingScorer
from services.pacing.stem_class_bonus import compute_stem_class_bonus


def _clip_without_shot_confidences() -> ClipFeatures:
    return ClipFeatures(
        clip_id=1,
        scene_id=10,
        role="hero",
        mood_refined="euphoric",
        style_bucket_id=0,
        motion_score=0.5,
        embedding=np.zeros(4, dtype=np.float32),
    )


def _ctx_with_dominant_stem(stem: str) -> AudioContext:
    return AudioContext(
        at_timestamp_sec=60.0,
        at_beat_idx=120,
        at_section_type="drop",
        at_bpm=140.0,
        at_energy=0.8,
        at_key="Am",
        at_key_confidence=0.9,
        at_harmonic_tension=0.75,
        at_mood_audio="energetic",
        at_mood_video="energetic",
        at_genre="psytrance",
        at_sub_genre="dark_psy",
        at_spectral_hash="hash_abc",
        at_groove_template="four_on_the_floor",
        at_lufs=-8.5,
        at_dominant_stem=stem,
    )


def test_empty_shot_confidences_returns_zero_bonus() -> None:
    # RED ohne Fix: ValueError: max() arg is an empty sequence
    for stem in ("drums", "bass", "vocals"):
        assert compute_stem_class_bonus(stem, {}) == 0.0


def test_scorer_survives_candidate_without_shot_confidences() -> None:
    # RED ohne Fix: ValueError verlaesst score() und damit select_best()
    scorer = PacingScorer(weights_profile="default")
    clip = _clip_without_shot_confidences()
    assert not clip.shot_confidences  # Vorbedingung: wirklich leer
    total, contribs = scorer.score(clip, _ctx_with_dominant_stem("drums"))
    assert isinstance(total, float)
    assert contribs["stem_class"] == 0.0


def test_populated_shot_confidences_still_scores_bonus() -> None:
    # Gegenprobe: der eigentliche Bonus-Pfad bleibt unveraendert.
    from services.pacing.shot_type_classifier import STEM_TO_CLASS

    target = STEM_TO_CLASS["drums"]
    assert compute_stem_class_bonus("drums", {target: 0.9}) == 0.15
    assert compute_stem_class_bonus("drums", {target: 0.1}) == 0.0
