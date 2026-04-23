from __future__ import annotations

import numpy as np
import pytest

from services.pacing.scorer import (
    PacingScorer,
    ClipFeatures,
    AudioContext,
    DEFAULT_WEIGHTS,
    CANONICAL_TERM_KEYS,
)


def _make_clip(
    clip_id: int = 1,
    role: str = "hero",
    mood: str = "euphoric",
    bucket: int = 0,
    motion: float = 0.5,
    embedding_dim: int = 4,
) -> ClipFeatures:
    rng = np.random.default_rng(clip_id)
    return ClipFeatures(
        clip_id=clip_id,
        scene_id=clip_id * 10,
        role=role,
        mood_refined=mood,
        style_bucket_id=bucket,
        motion_score=motion,
        embedding=rng.standard_normal(embedding_dim).astype(np.float32),
    )


def _make_ctx() -> AudioContext:
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
    )


def test_term_contributions_sum_to_total_score() -> None:
    clip = _make_clip()
    pred = _make_clip(clip_id=2, role="detail")
    ctx = _make_ctx()
    scorer = PacingScorer(weights_profile="default")
    total, contribs = scorer.score(clip, ctx, predecessor=pred)
    assert set(contribs.keys()) == set(CANONICAL_TERM_KEYS)
    assert abs(total - sum(contribs.values())) < 1e-6


def test_weight_zero_disables_term() -> None:
    """Setting w_mood_video=0.0 must zero out the mood_video contribution."""
    clip = _make_clip()
    pred = _make_clip(clip_id=2, role="detail")
    ctx = _make_ctx()
    weights = dict(DEFAULT_WEIGHTS)
    weights["w_mood_video"] = 0.0
    scorer = PacingScorer(weights=weights)
    total, contribs = scorer.score(clip, ctx, predecessor=pred)
    assert contribs["mood_video"] == 0.0


def test_collision_penalty_reduces_score() -> None:
    """Predecessor with nearly-orthogonal embedding → low style_compat → high collision_penalty → lower total."""
    ctx = _make_ctx()
    clip = _make_clip()
    # compatible predecessor: make its embedding (nearly) equal to clip's
    pred_compat = ClipFeatures(
        clip_id=2,
        scene_id=20,
        role="detail",
        mood_refined="calm",
        style_bucket_id=0,
        motion_score=0.5,
        embedding=clip.embedding,
    )
    # incompatible predecessor: negate the embedding to force cosine near -1
    pred_incompat = ClipFeatures(
        clip_id=3,
        scene_id=30,
        role="detail",
        mood_refined="calm",
        style_bucket_id=0,
        motion_score=0.5,
        embedding=-clip.embedding,
    )
    scorer = PacingScorer(weights_profile="default")
    total_compat, _ = scorer.score(clip, ctx, predecessor=pred_compat)
    total_incompat, _ = scorer.score(clip, ctx, predecessor=pred_incompat)
    assert total_incompat < total_compat, (
        f"collision-incompatible predecessor should lower the score: "
        f"compat={total_compat}, incompat={total_incompat}"
    )


def test_negative_score_allowed() -> None:
    """If we force only penalty weights, a candidate's total can go below 0."""
    ctx = _make_ctx()
    clip = _make_clip()
    pred_incompat = ClipFeatures(
        clip_id=2,
        scene_id=20,
        role="detail",
        mood_refined="calm",
        style_bucket_id=0,
        motion_score=0.5,
        embedding=-clip.embedding,
    )
    # Zero out all positive weights and keep penalties
    weights = {k: 0.0 for k in DEFAULT_WEIGHTS}
    weights["w_collision"] = 1.0
    weights["w_freshness"] = 1.0
    scorer = PacingScorer(weights=weights)
    # Put the clip in the recent list so freshness penalty triggers
    total, contribs = scorer.score(
        clip, ctx, predecessor=pred_incompat, recent_clip_ids=[clip.clip_id]
    )
    assert total < 0, f"Expected negative total, got {total} with contribs {contribs}"


def test_batch_score_matches_single() -> None:
    ctx = _make_ctx()
    clips = [_make_clip(clip_id=i, role="hero") for i in range(5)]
    pred = _make_clip(clip_id=99, role="detail")
    scorer = PacingScorer(weights_profile="default")
    batch = scorer.score_batch(clips, ctx, predecessor=pred)
    singles = [scorer.score(c, ctx, predecessor=pred) for c in clips]
    assert len(batch) == len(singles) == 5
    for (bt, bc), (st, sc) in zip(batch, singles):
        assert abs(bt - st) < 1e-9
        assert bc.keys() == sc.keys()
        for k in bc:
            assert abs(bc[k] - sc[k]) < 1e-9


def test_historical_accept_rate_neutral_for_unseen_clip() -> None:
    """With pattern_lookup returning (0, 0), Wilson says 0.5 — not 0."""
    ctx = _make_ctx()
    clip = _make_clip()

    def zero_lookup(*args: object) -> tuple[int, int]:
        return (0, 0)

    def zero_prior_lookup(*args: object) -> float:
        # Wilson fallback is for historical_accept_rate; priors (genre/key/spectral)
        # can also return 0.5 for "unseen" — that's the same neutral.
        return 0.5

    # The scorer passes ONE callable for pattern_lookup, which is dispatched
    # inside the helpers. A zero_lookup callable that returns (0, 0) for 2-tuple
    # lookups and 0.5 for scalar lookups covers both.
    def dispatching_lookup(kind: str, *keys: object) -> tuple[int, int] | float:
        if kind == "memory":
            return (0, 0)
        return 0.5

    # Simpler: check that the contribs["memory"] uses the wilson fallback 0.5
    # without needing the full dispatch machinery — via historical_accept_rate directly.
    from services.pacing.scorer import historical_accept_rate

    v = historical_accept_rate(
        ("x", "y", "140"), clip, pattern_lookup=lambda fp, cid: (0, 0)
    )
    assert v == 0.5
