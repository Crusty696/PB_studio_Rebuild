from __future__ import annotations

from services.pacing.variations_budget import VariationsBudget, BudgetRule


def test_single_budget_counts_window_correctly() -> None:
    b = VariationsBudget(
        {"style_bucket": BudgetRule(max_per_window=3, window_sec=30.0)}
    )
    for t in [0.0, 5.0, 10.0]:
        assert b.allow(t, {"style_bucket": "urban"})
        b.record(t, {"style_bucket": "urban"})
    # 3 uses recorded; next use (t=15) hits count==max=3 → blocked
    assert not b.allow(15.0, {"style_bucket": "urban"})


def test_window_expiry_releases_budget() -> None:
    """Entries outside the sliding window no longer count."""
    b = VariationsBudget(
        {"style_bucket": BudgetRule(max_per_window=2, window_sec=10.0)}
    )
    b.record(0.0, {"style_bucket": "urban"})
    b.record(1.0, {"style_bucket": "urban"})
    # At t=2.0, both cuts are in the 10s window → budget full
    assert not b.allow(2.0, {"style_bucket": "urban"})
    # At t=12.0, the entry at t=0.0 has fallen out (window is (2.0, 12.0])
    # leaving only the t=1.0 entry. Budget: 1 <= 2, so allowed.
    assert b.allow(12.0, {"style_bucket": "urban"})


def test_dj_mix_segment_reset() -> None:
    """segment_boundary() clears per-bucket counters but keeps scene_id_global."""
    b = VariationsBudget(
        {"style_bucket": BudgetRule(max_per_window=1, window_sec=30.0)},
        dj_mix=True,
    )
    b.record(10.0, {"style_bucket": "urban"})
    # within 30s → blocked
    assert not b.allow(20.0, {"style_bucket": "urban"})
    # segment boundary resets per-segment state
    b.segment_boundary(at_time=60.0)
    # after reset → allowed again
    assert b.allow(70.0, {"style_bucket": "urban"})


def test_anti_repeat_scene_id_45s() -> None:
    """Same scene_id within 45s is never allowed (max_per_window=1 on scene_id)."""
    b = VariationsBudget()  # use DEFAULT_BUDGETS
    b.record(
        0.0,
        {
            "scene_id": 42,
            "style_bucket": "urban",
            "mood_refined": "calm",
            "role": "hero",
        },
    )
    # 44s later: still within the 45s window → blocked
    assert not b.allow(44.0, {"scene_id": 42})
    # 46s later: outside window → allowed
    assert b.allow(46.0, {"scene_id": 42})


def test_dj_mix_global_scene_id_cap() -> None:
    """dj_mix=True + scene_id_global max=5: 6th use of same clip is blocked EVEN
    after segment_boundary resets."""
    b = VariationsBudget(dj_mix=True)
    for i in range(5):
        # Each use well outside the 45s window + with a segment boundary in between
        b.record(i * 100.0, {"scene_id": 99})
        b.segment_boundary(at_time=i * 100.0 + 50.0)
    # 6th attempt at t=600 — global cap hit
    assert not b.allow(600.0, {"scene_id": 99})
    # Different scene_id still fine
    assert b.allow(600.0, {"scene_id": 7})


def test_allow_is_non_mutating() -> None:
    """allow() must be a pure query — repeated calls at the same t must return the same result."""
    b = VariationsBudget()
    b.record(
        0.0,
        {
            "scene_id": 1,
            "style_bucket": "urban",
            "mood_refined": "calm",
            "role": "hero",
        },
    )
    buckets = {
        "scene_id": 1,
        "style_bucket": "urban",
        "mood_refined": "calm",
        "role": "hero",
    }
    first = b.allow(30.0, buckets)
    second = b.allow(30.0, buckets)
    third = b.allow(30.0, buckets)
    assert first == second == third


def test_segment_boundary_noop_without_dj_mix() -> None:
    """When dj_mix=False, segment_boundary() must NOT reset anything."""
    b = VariationsBudget(
        {"style_bucket": BudgetRule(max_per_window=1, window_sec=30.0)}
    )
    b.record(10.0, {"style_bucket": "urban"})
    b.segment_boundary(at_time=60.0)
    # Still blocked despite the boundary call, because dj_mix=False
    assert not b.allow(20.0, {"style_bucket": "urban"})
    # But far enough outside the window is fine (normal window behaviour)
    assert b.allow(41.0, {"style_bucket": "urban"})
