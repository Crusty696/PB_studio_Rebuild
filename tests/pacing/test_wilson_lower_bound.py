import pytest

from services.stats.wilson_lower_bound import wilson_lower_bound


def test_zero_out_of_zero_returns_neutral_half():
    assert wilson_lower_bound(accepts=0, total=0) == 0.5


def test_all_accept_n10_below_1_above_50pct():
    wlb = wilson_lower_bound(10, 10)
    assert 0.5 < wlb < 1.0


def test_all_reject_n10_below_50pct():
    assert wilson_lower_bound(0, 10) < 0.5


def test_small_n_pulls_toward_center():
    # 1/1 should be closer to 0.5 than 10/10
    assert wilson_lower_bound(1, 1) < wilson_lower_bound(10, 10)


def test_z_parameter_affects_conservatism():
    # higher z → more conservative → lower bound
    assert wilson_lower_bound(5, 10, z=2.576) < wilson_lower_bound(5, 10, z=1.96)


def test_default_z_is_1_96():
    # documented behavior
    assert wilson_lower_bound(5, 10) == wilson_lower_bound(5, 10, z=1.96)


# Additional tests for 100% coverage of error branches
def test_accepts_greater_than_total_raises():
    with pytest.raises(ValueError):
        wilson_lower_bound(accepts=5, total=3)


def test_negative_accepts_raises():
    with pytest.raises(ValueError):
        wilson_lower_bound(accepts=-1, total=5)


def test_negative_total_raises():
    with pytest.raises(ValueError):
        wilson_lower_bound(accepts=0, total=-1)
