"""FR-S4-2 / Task-S4-2: Per-Section Policy via tabellarische Value-Iteration."""
import pytest

from services.pacing.rl_policy import SectionPolicy


def test_policy_falls_back_to_default_when_no_history():
    p = SectionPolicy(min_decisions=5)
    # Empty history → default value (=0.5 neutral)
    assert p.value(section="chorus", state=("v", "d", "b")) == 0.5


def test_policy_learns_from_decisions():
    p = SectionPolicy(min_decisions=2, learning_rate=0.5)
    # 3 Entscheidungen für (chorus, ("v","d","b")), reward=1.0
    for _ in range(5):
        p.update(section="chorus", state=("v", "d", "b"), reward=1.0)
    v = p.value(section="chorus", state=("v", "d", "b"))
    assert v > 0.5  # gelernt → höher als neutral


def test_policy_separates_sections():
    p = SectionPolicy(min_decisions=1, learning_rate=0.5)
    p.update("chorus", ("a",), reward=1.0)
    p.update("verse", ("a",), reward=0.0)
    assert p.value("chorus", ("a",)) > p.value("verse", ("a",))


def test_policy_converges():
    p = SectionPolicy(min_decisions=1, learning_rate=0.3)
    state = ("x",)
    for _ in range(100):
        p.update("drop", state, reward=0.8)
    v = p.value("drop", state)
    assert abs(v - 0.8) < 0.05  # konvergiert nahe target


def test_invalid_reward_raises():
    p = SectionPolicy()
    with pytest.raises(ValueError):
        p.update("chorus", ("x",), reward=1.5)
    with pytest.raises(ValueError):
        p.update("chorus", ("x",), reward=-0.1)


def test_policy_decisions_count():
    p = SectionPolicy()
    assert p.n_decisions("chorus") == 0
    p.update("chorus", ("a",), reward=0.5)
    p.update("chorus", ("b",), reward=0.5)
    assert p.n_decisions("chorus") == 2


def test_default_value_returned_below_min():
    p = SectionPolicy(min_decisions=10, default_value=0.3)
    p.update("chorus", ("x",), reward=1.0)  # nur 1 < 10
    assert p.value("chorus", ("x",)) == 0.3
