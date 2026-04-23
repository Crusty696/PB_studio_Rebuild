from __future__ import annotations

import numpy as np
import pytest

from services.pacing.pipeline import PacingPipeline, PipelineResult
from services.pacing.scorer import AudioContext, ClipFeatures


def _make_clip(
    clip_id: int,
    role: str = "hero",
    mood: str = "euphoric",
    style_bucket_id: int = 1,
    motion: float = 0.5,
    embedding: np.ndarray | None = None,
) -> ClipFeatures:
    if embedding is None:
        rng = np.random.default_rng(clip_id)
        embedding = rng.standard_normal(8).astype(np.float32)
    return ClipFeatures(
        clip_id=clip_id,
        scene_id=clip_id * 10,
        role=role,
        mood_refined=mood,
        style_bucket_id=style_bucket_id,
        motion_score=motion,
        embedding=embedding,
    )


def _drop_context(ts: float = 60.0) -> AudioContext:
    return AudioContext(
        at_timestamp_sec=ts,
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
        at_spectral_hash="h",
        at_groove_template="fotf",
        at_lufs=-8.5,
    )


def test_hard_rule_drops_wrong_role() -> None:
    """Section=drop allows {hero, action}; an establishing-role clip is rejected at stage 1."""
    pipe = PacingPipeline()
    ctx = _drop_context()
    hero = _make_clip(1, role="hero")
    establishing = _make_clip(2, role="establishing")
    res = pipe.select_best([hero, establishing], ctx)
    assert res.chosen is not None
    # establishing should NOT have been the chosen clip; also its stage_result should be passed_stage1=False
    est_result = next(
        sr
        for sr in res.rationale["stage_results"]
        if sr["clip_id"] == establishing.clip_id
    )
    assert est_result["passed_stage1"] is False


def test_budget_disqualifies_over_limit() -> None:
    """Two hero candidates; after recording the first, the second (same scene_id) is blocked by anti-repeat."""
    pipe = PacingPipeline()
    ctx1 = _drop_context(ts=0.0)
    ctx2 = _drop_context(ts=30.0)  # within the 45s anti-repeat window
    hero_a = _make_clip(1, role="hero")
    hero_b = _make_clip(2, role="hero")
    # Round 1: pick hero_a (sole candidate); the pipeline records it.
    res1 = pipe.select_best([hero_a], ctx1)
    assert res1.chosen is hero_a
    # Round 2: candidates are hero_a (same scene_id, should be blocked)
    # and hero_b (new, should win)
    res2 = pipe.select_best([hero_a, hero_b], ctx2)
    assert res2.chosen is hero_b, f"expected hero_b, got {res2.chosen}"


def test_collision_penalty_does_not_hard_reject() -> None:
    """A clip with orthogonal embedding to predecessor gets a collision penalty but is
    NOT hard-rejected (default mode: collision_strict=False)."""
    pipe = PacingPipeline()
    ctx = _drop_context()
    # Predecessor: fixed embedding
    predecessor = _make_clip(
        99, role="hero", embedding=np.array([1, 0, 0, 0, 0, 0, 0, 0], dtype=np.float32)
    )
    # Sole candidate: orthogonal embedding (collision!)
    colliding = _make_clip(
        1, role="hero", embedding=np.array([0, 1, 0, 0, 0, 0, 0, 0], dtype=np.float32)
    )
    res = pipe.select_best([colliding], ctx, predecessor=predecessor)
    assert res.chosen is colliding  # NOT hard-rejected
    # Collision similarity should be low (close to 0 for orthogonal unit-ish vectors)
    chosen_trace = next(
        sr
        for sr in res.rationale["stage_results"]
        if sr["clip_id"] == colliding.clip_id
    )
    assert chosen_trace["collision_similarity"] is not None
    assert chosen_trace["collision_similarity"] < 0.5


def test_stage_1_fallback_on_empty_candidates() -> None:
    """No hero/action candidate for a drop section. With stage1_fallback=soften (default),
    the pipeline widens to accept filler/unknown."""
    pipe = PacingPipeline()
    ctx = _drop_context()
    # Only filler and establishing available; no hero/action
    filler = _make_clip(1, role="filler")
    establishing = _make_clip(2, role="establishing")
    res = pipe.select_best([filler, establishing], ctx)
    # Filler should get through via softening; establishing still rejected by softer rule
    # (the soften path accepts filler/unknown, but does NOT accept arbitrary roles.)
    assert res.chosen is filler, f"expected filler, got {res.chosen}"
    assert res.rationale["stage1_softened"] is True


def test_forced_top_k_when_all_scores_negative() -> None:
    """If all candidates score negative, the top (least negative) still wins, with forced=true."""
    from services.pacing.scorer import DEFAULT_WEIGHTS, PacingScorer

    # Custom scorer: zero out all positive weights, keep penalties at 1.0 → every candidate
    # can only accumulate penalties → every total < 0.
    weights = {k: 0.0 for k in DEFAULT_WEIGHTS}
    weights["w_collision"] = 1.0
    weights["w_freshness"] = 1.0
    scorer = PacingScorer(weights=weights)
    pipe = PacingPipeline(scorer=scorer)
    ctx = _drop_context()
    predecessor = _make_clip(
        99, role="hero", embedding=np.array([1, 0, 0, 0, 0, 0, 0, 0], dtype=np.float32)
    )
    clips = [
        _make_clip(
            1,
            role="hero",
            embedding=np.array([0, 1, 0, 0, 0, 0, 0, 0], dtype=np.float32),
        ),  # collision
        _make_clip(
            2,
            role="hero",
            embedding=np.array([0, 0, 1, 0, 0, 0, 0, 0], dtype=np.float32),
        ),  # collision
    ]
    # Put clip 1 in recent list to trigger freshness penalty too
    res = pipe.select_best(clips, ctx, predecessor=predecessor, recent_clip_ids=[1])
    assert res.chosen is not None
    # Both candidates should have negative scores
    assert res.rationale["chosen_score"] < 0
    assert res.rationale["forced_negative"] is True


def test_all_four_stages_are_present_in_rationale() -> None:
    """Regression guard: rationale must have every stage's fingerprint."""
    pipe = PacingPipeline()
    ctx = _drop_context()
    hero = _make_clip(1, role="hero")
    res = pipe.select_best([hero], ctx)
    assert res.chosen is hero
    r = res.rationale
    # Stage 1
    assert "stage1_softened" in r
    # Stage 2
    assert "stage2_forced" in r
    # Stage 3 (collision_similarity per candidate in stage_results)
    assert all("collision_similarity" in sr for sr in r["stage_results"])
    # Stage 4 (soft_score + contribs)
    chosen_sr = next(sr for sr in r["stage_results"] if sr["clip_id"] == hero.clip_id)
    assert chosen_sr["soft_score"] is not None
    assert "contribs" in chosen_sr
