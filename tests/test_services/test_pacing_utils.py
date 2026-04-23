import pytest
from services.pacing_utils import wilson_lower_bound

def test_wilson_zero_samples():
    """(0, 0) should return 0.0."""
    assert wilson_lower_bound(0, 0) == 0.0

def test_wilson_perfect_score_low_n():
    """(2, 2) should return a small value (around 0.34)."""
    # Calculation for 2/2, confidence 0.95
    # z approx 1.96
    # p_hat = 1.0, n = 2
    # lower bound approx 0.3424
    result = wilson_lower_bound(2, 2)
    assert 0.33 < result < 0.35

def test_wilson_perfect_score_high_n():
    """(100, 100) should return a high value (around 0.96)."""
    # Calculation for 100/100, confidence 0.95
    # z approx 1.96
    # p_hat = 1.0, n = 100
    # lower bound approx 0.963
    result = wilson_lower_bound(100, 100)
    assert 0.95 < result < 0.97

def test_wilson_mixed_score():
    """(70, 100) should return a value around 0.6."""
    # Calculation for 70/100, confidence 0.95
    # lower bound approx 0.604
    result = wilson_lower_bound(70, 100)
    assert 0.59 < result < 0.62

def test_wilson_invalid_input():
    """(5, 2) should raise ValueError."""
    with pytest.raises(ValueError, match="cannot exceed total samples"):
        wilson_lower_bound(5, 2)

def test_wilson_negative_input():
    """Negative values should raise ValueError."""
    with pytest.raises(ValueError):
        wilson_lower_bound(-1, 10)
    with pytest.raises(ValueError):
        wilson_lower_bound(5, -10)

def test_wilson_confidence_levels():
    """Verify different confidence levels."""
    # (100, 100) at 99.9% confidence should have a lower bound than 95%
    high_conf = wilson_lower_bound(100, 100, confidence=0.999)
    std_conf = wilson_lower_bound(100, 100, confidence=0.95)
    assert high_conf < std_conf
