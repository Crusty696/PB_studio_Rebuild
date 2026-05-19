"""Phase 16 — Coverage-Guard RED.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 16 (Tier 2 Building-Blocks)
"""
from __future__ import annotations

import pytest


def test_full_coverage_no_gaps():
    from services.video_pipeline.primitives.coverage_guard import (
        compute_coverage,
    )
    times = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    rep = compute_coverage(times, duration_s=5.0, max_gap_s=2.0)
    assert rep.max_gap_s == pytest.approx(1.0)
    assert rep.percent_covered >= 99.5
    assert rep.gaps == []


def test_finds_single_gap():
    from services.video_pipeline.primitives.coverage_guard import (
        compute_coverage,
    )
    # Luecke zwischen 2.0 und 8.0
    times = [0.0, 1.0, 2.0, 8.0, 9.0, 10.0]
    rep = compute_coverage(times, duration_s=10.0, max_gap_s=2.0)
    assert rep.max_gap_s == pytest.approx(6.0)
    assert len(rep.gaps) == 1
    assert rep.gaps[0] == pytest.approx((2.0, 8.0))


def test_assert_complete_raises_on_gap():
    from services.video_pipeline.primitives.coverage_guard import (
        assert_coverage_complete, IncompleteCoverage,
    )
    times = [0.0, 5.0, 10.0]  # 5s gap
    with pytest.raises(IncompleteCoverage):
        assert_coverage_complete(times, duration_s=10.0, max_gap_s=2.0)


def test_assert_complete_passes():
    from services.video_pipeline.primitives.coverage_guard import (
        assert_coverage_complete,
    )
    times = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    # Should not raise
    assert_coverage_complete(times, duration_s=5.0, max_gap_s=2.0)


def test_unsorted_times_handled():
    from services.video_pipeline.primitives.coverage_guard import compute_coverage
    times = [3.0, 0.0, 5.0, 2.0, 1.0, 4.0]
    rep = compute_coverage(times, duration_s=5.0, max_gap_s=2.0)
    assert rep.max_gap_s == pytest.approx(1.0)


def test_empty_times_returns_full_gap():
    from services.video_pipeline.primitives.coverage_guard import compute_coverage
    rep = compute_coverage([], duration_s=10.0, max_gap_s=2.0)
    assert rep.percent_covered == 0.0
    assert len(rep.gaps) == 1
    assert rep.gaps[0] == (0.0, 10.0)
