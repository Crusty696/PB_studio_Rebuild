"""FR-S4-1 / Task-S4-1: RL-Reward-Function (7 Komponenten)."""
import pytest

from services.pacing.rl_reward import compute_reward, RewardComponents, REWARD_KEYS


def test_uniform_components_yields_known_value():
    comps = RewardComponents(
        r_energy=0.5, r_mood=0.5, r_stem_class=0.5, r_section=0.5,
        r_freshness=0.5, r_collision=0.5, r_user=0.5,
    )
    r = compute_reward(comps)
    # 7 Komponenten je 0.5 mit Default-Gewichten (Summe=1) → 0.5
    assert abs(r - 0.5) < 1e-6


def test_max_reward_is_one():
    comps = RewardComponents(1, 1, 1, 1, 1, 1, 1)
    assert compute_reward(comps) == 1.0


def test_zero_reward():
    comps = RewardComponents(0, 0, 0, 0, 0, 0, 0)
    assert compute_reward(comps) == 0.0


def test_out_of_range_raises():
    comps = RewardComponents(1.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5)
    with pytest.raises(ValueError):
        compute_reward(comps)


def test_negative_raises():
    comps = RewardComponents(-0.1, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5)
    with pytest.raises(ValueError):
        compute_reward(comps)


def test_user_verdict_overrides_user_component():
    comps = RewardComponents(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5)
    r_default = compute_reward(comps)
    r_thumbs_up = compute_reward(comps, user_verdict="good")
    r_thumbs_down = compute_reward(comps, user_verdict="bad")
    assert r_thumbs_up > r_default > r_thumbs_down


def test_unknown_verdict_ignored():
    comps = RewardComponents(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5)
    r = compute_reward(comps, user_verdict="unknown")
    assert abs(r - 0.5) < 1e-6


def test_custom_weights_normalized():
    comps = RewardComponents(1, 0, 0, 0, 0, 0, 0)
    r = compute_reward(comps, weights={"r_energy": 1.0})  # nur energy
    assert r == 1.0


def test_unknown_weight_key_raises():
    comps = RewardComponents(0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5)
    with pytest.raises(ValueError):
        compute_reward(comps, weights={"r_unknown": 0.5})


def test_reward_keys_constant():
    assert set(REWARD_KEYS) == {"r_energy", "r_mood", "r_stem_class", "r_section", "r_freshness", "r_collision", "r_user"}
