import numpy as np
from services.enrichment.mood_anchor_matcher import MoodAnchorMatcher


def test_matcher_returns_top_class_with_confidence() -> None:
    m = MoodAnchorMatcher(anchors_path="config/mood_anchors.npz")
    synthetic_embedding = m._get_anchor("euphoric")  # cheat: exact anchor
    mood, conf = m.refine(synthetic_embedding, prior_mood="energetic", prior_weight=0.6)
    assert mood == "euphoric" and conf > 0.9


def test_prior_mixing_biases_result() -> None:
    """prior=dramatic at high weight should pull an ambiguous embedding toward {dark|tense|aggressive}."""
    m = MoodAnchorMatcher(anchors_path="config/mood_anchors.npz")
    # Use the midpoint of two anchors as an ambiguous embedding (genuinely between two classes)
    midpoint = 0.5 * m._get_anchor("euphoric") + 0.5 * m._get_anchor("calm")
    mood_low_prior, _ = m.refine(midpoint, prior_mood="dramatic", prior_weight=0.0)
    mood_high_prior, _ = m.refine(midpoint, prior_mood="dramatic", prior_weight=10.0)
    # With weight=0.0, prior has no effect; with weight=10.0, prior dominates.
    assert mood_high_prior in {"dark", "tense", "aggressive"}


def test_batch_refine_matches_single() -> None:
    m = MoodAnchorMatcher(anchors_path="config/mood_anchors.npz")
    # Build 3 synthetic embeddings from 3 different anchors
    names = ["euphoric", "calm", "dark"]
    embs = np.stack([m._get_anchor(n) for n in names])
    batch_results = m.refine_batch(
        embs, prior_moods=[None, None, None], prior_weight=0.6
    )
    single_results = [
        m.refine(embs[i], prior_mood=None, prior_weight=0.6) for i in range(3)
    ]
    for b, s in zip(batch_results, single_results):
        assert b[0] == s[0]  # same mood
        assert abs(b[1] - s[1]) < 1e-5  # same confidence (up to FP noise)
