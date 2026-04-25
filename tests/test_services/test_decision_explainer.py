"""FR-S4-4 (Logik-Layer): Decision-Explainer."""
from services.pacing.decision_explainer import explain_decision
from services.pacing.rl_reward import RewardComponents


def test_explain_returns_top_n_components():
    comps = RewardComponents(0.9, 0.1, 0.5, 0.5, 0.5, 0.5, 0.5)
    out = explain_decision(comps, top_n=3)
    assert "total_reward" in out
    assert "top_components" in out
    assert len(out["top_components"]) == 3
    # r_energy mit value=0.9 sollte unter den top sein
    keys = [c["key"] for c in out["top_components"]]
    assert "r_energy" in keys


def test_explain_breakdown_contains_all_keys():
    comps = RewardComponents(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5)
    out = explain_decision(comps, top_n=3)
    assert set(out["breakdown"].keys()) == {
        "r_energy", "r_mood", "r_stem_class", "r_section", "r_freshness", "r_collision", "r_user"
    }


def test_explain_total_matches_reward():
    comps = RewardComponents(0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7)
    out = explain_decision(comps)
    assert abs(out["total_reward"] - 0.7) < 1e-6


def test_user_verdict_propagates():
    comps = RewardComponents(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5)
    out_good = explain_decision(comps, user_verdict="good")
    out_bad = explain_decision(comps, user_verdict="bad")
    assert out_good["total_reward"] > out_bad["total_reward"]
    assert out_good["user_verdict"] == "good"


def test_top_n_clamped():
    comps = RewardComponents(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5)
    out = explain_decision(comps, top_n=99)
    assert len(out["top_components"]) <= 7
