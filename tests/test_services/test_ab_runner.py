"""FR-S4-5 / Task-S4-5: A/B-Pacing-Runner.

Generiert zwei Cut-Listen mit verschiedenen Reward-Weight-Profilen aus
demselben Input. Deterministisch mit gleichem Seed.
"""
import numpy as np
import pytest

from services.pacing.ab_runner import run_ab, ABResult


def _stub_scorer(weights):
    """Liefert einen scorer-callable, der `r_energy * w_energy` zurückgibt."""
    w = float(weights.get("r_energy", 0.5))
    def _scorer(candidate, ctx):
        return float(candidate.get("r_energy", 0.0)) * w
    return _scorer


def test_ab_returns_two_results():
    candidates = [{"id": 1, "r_energy": 0.3}, {"id": 2, "r_energy": 0.9}, {"id": 3, "r_energy": 0.5}]
    weights_a = {"r_energy": 1.0}
    weights_b = {"r_energy": 0.0}
    result = run_ab(
        candidates,
        ctx={"section": "chorus"},
        weights_a=weights_a,
        weights_b=weights_b,
        scorer_factory=_stub_scorer,
        seed=42,
    )
    assert isinstance(result, ABResult)
    assert result.choice_a is not None
    assert result.choice_b is not None


def test_ab_high_weight_picks_high_energy():
    candidates = [{"id": 1, "r_energy": 0.1}, {"id": 2, "r_energy": 0.9}]
    result = run_ab(
        candidates,
        ctx={},
        weights_a={"r_energy": 1.0},
        weights_b={"r_energy": 1.0},
        scorer_factory=_stub_scorer,
        seed=0,
    )
    assert result.choice_a["id"] == 2
    assert result.choice_b["id"] == 2


def test_ab_deterministic():
    candidates = [{"id": i, "r_energy": float(i) / 10} for i in range(10)]
    weights = {"r_energy": 0.5}
    r1 = run_ab(candidates, ctx={}, weights_a=weights, weights_b=weights, scorer_factory=_stub_scorer, seed=7)
    r2 = run_ab(candidates, ctx={}, weights_a=weights, weights_b=weights, scorer_factory=_stub_scorer, seed=7)
    assert r1.choice_a == r2.choice_a
    assert r1.choice_b == r2.choice_b


def test_ab_empty_candidates():
    result = run_ab(
        [], ctx={}, weights_a={}, weights_b={}, scorer_factory=_stub_scorer, seed=0,
    )
    assert result.choice_a is None
    assert result.choice_b is None


def test_ab_records_scores():
    candidates = [{"id": 1, "r_energy": 0.3}, {"id": 2, "r_energy": 0.7}]
    result = run_ab(
        candidates, ctx={}, weights_a={"r_energy": 1.0}, weights_b={"r_energy": 0.5},
        scorer_factory=_stub_scorer, seed=0,
    )
    assert result.scores_a is not None and len(result.scores_a) == 2
    assert result.scores_b is not None and len(result.scores_b) == 2
