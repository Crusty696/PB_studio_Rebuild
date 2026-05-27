"""B-370 — DJ-mix pacing budget must be wired into the pipeline.

The pacing service builds ``PacingPipeline(...)`` for the Studio-Brain run.
Before the fix it never passed ``dj_mix``, so the global per-mix scene
repetition cap (``VariationsBudget.DJ_MIX_SCENE_ID_GLOBAL_MAX``) never engaged.

These tests assert the wiring is honoured at the PacingPipeline boundary
(no DB / GPU / audio decode needed).
"""
from __future__ import annotations

from services.pacing.pipeline import PacingPipeline
from services.pacing.scorer import AudioContext, ClipFeatures
from services.pacing.variations_budget import VariationsBudget


def _ctx(t: float) -> AudioContext:
    return AudioContext(
        at_timestamp_sec=t,
        at_beat_idx=None,
        at_section_type=None,
        at_bpm=128.0,
        at_energy=0.5,
        at_key=None,
        at_key_confidence=None,
        at_harmonic_tension=None,
        at_mood_audio=None,
        at_mood_video=None,
        at_genre=None,
        at_sub_genre=None,
        at_spectral_hash=None,
        at_groove_template=None,
        at_lufs=None,
    )


def _clip(scene_id: int) -> ClipFeatures:
    return ClipFeatures(
        clip_id=scene_id,
        scene_id=scene_id,
        role="hero",
        mood_refined="energetic",
        style_bucket_id=1,
        motion_score=0.5,
    )


def test_b370_dj_mix_true_enforces_global_scene_cap() -> None:
    """With dj_mix=True the global scene_id cap must block over-reuse."""
    pipe = PacingPipeline(rules_path="does/not/exist.yaml", dj_mix=True)
    budget: VariationsBudget = pipe._budget
    assert budget._dj_mix is True

    cap = VariationsBudget.DJ_MIX_SCENE_ID_GLOBAL_MAX
    # Far-apart timestamps so the per-window scene_id rule never blocks first;
    # only the global per-mix cap should be the limiter.
    for i in range(cap):
        t = float(i * 1000)
        res = pipe.select_best([_clip(7)], _ctx(t))
        assert res.chosen is not None and res.chosen.scene_id == 7

    # cap reached -> global counter blocks scene 7 in allow()
    assert budget.allow(float(cap * 1000), {"scene_id": 7}) is False


def test_b370_dj_mix_false_has_no_global_cap() -> None:
    """Default (non-DJ-mix) pipeline keeps dj_mix off — no global cap."""
    pipe = PacingPipeline(rules_path="does/not/exist.yaml", dj_mix=False)
    assert pipe._budget._dj_mix is False
    cap = VariationsBudget.DJ_MIX_SCENE_ID_GLOBAL_MAX
    # Even far beyond the cap, allow() must not trip the global guard when off.
    for i in range(cap + 3):
        assert pipe._budget.allow(float(i * 1000), {"scene_id": 7}) is True
        pipe._budget.record(float(i * 1000), {"scene_id": 7})
