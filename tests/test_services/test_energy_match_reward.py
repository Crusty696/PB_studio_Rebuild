"""FR-S1-4 / Task-S1-4: Energy-Curve-Match Reward.

Aufbauend auf services/pacing/audio_video_curves.py:cosine_similarity_curves.
Liefert einen normalisierten Reward-Term r_energy ∈ [0, 1] für die
Pacing-Entscheidung.
"""
import numpy as np

from services.pacing.energy_match_reward import compute_energy_match_reward


def test_perfect_curve_match_reward_one():
    a = np.array([0.1, 0.5, 1.0, 0.5, 0.1], dtype=np.float32)
    r = compute_energy_match_reward(a, a)
    assert abs(r - 1.0) < 1e-5


def test_orthogonal_curves_reward_half():
    """Cosine 0 → r_energy = 0.5 (neutral), nicht negativ."""
    a = np.array([1.0, 0.0, 1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0, 0.0, 1.0], dtype=np.float32)
    r = compute_energy_match_reward(a, b)
    assert abs(r - 0.5) < 1e-5


def test_silent_returns_neutral():
    a = np.array([1.0, 1.0, 1.0], dtype=np.float32)
    b = np.zeros(3, dtype=np.float32)
    r = compute_energy_match_reward(a, b)
    assert r == 0.5


def test_reward_bounded_zero_one():
    rng = np.random.default_rng(42)
    for _ in range(20):
        a = rng.standard_normal(50).astype(np.float32)
        b = rng.standard_normal(50).astype(np.float32)
        r = compute_energy_match_reward(a, b)
        assert 0.0 <= r <= 1.0


def test_deterministic():
    a = np.array([0.2, 0.7, 0.5, 0.9, 0.3], dtype=np.float32)
    b = np.array([0.1, 0.8, 0.4, 0.95, 0.25], dtype=np.float32)
    r1 = compute_energy_match_reward(a, b)
    r2 = compute_energy_match_reward(a, b)
    assert r1 == r2
