"""FR-S0-3 tests: stem_section_aggregator."""
import numpy as np

from services.pacing.stem_section_aggregator import (
    aggregate,
    dominant_stem,
    DEFAULT_STEM_NAMES,
)


class _Section:
    def __init__(self, id_, start_time, end_time):
        self.id = id_
        self.start_time = start_time
        self.end_time = end_time


def _make_stem(samples_per_sec: int, total_sec: float, amp: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(samples_per_sec * total_sec)
    return (rng.standard_normal(n) * amp).astype(np.float32)


def test_aggregate_returns_per_section():
    sr = 22050
    stems = {
        "vocals": _make_stem(sr, 4.0, amp=0.3, seed=1),
        "drums": _make_stem(sr, 4.0, amp=0.8, seed=2),
        "bass": _make_stem(sr, 4.0, amp=0.5, seed=3),
        "other": _make_stem(sr, 4.0, amp=0.1, seed=4),
    }
    sections = [_Section("verse", 0.0, 2.0), _Section("chorus", 2.0, 4.0)]
    result = aggregate(stems, sections, sr=sr)
    assert set(result.keys()) == {"verse", "chorus"}
    for sect_id, energies in result.items():
        assert set(energies.keys()) == set(DEFAULT_STEM_NAMES)
        # L1-normalized: sum to 1
        assert abs(sum(energies.values()) - 1.0) < 0.01


def test_aggregate_drums_dominate():
    """Drums are amplitude-loudest → should win in dominant_stem()."""
    sr = 22050
    stems = {
        "vocals": _make_stem(sr, 2.0, amp=0.1, seed=1),
        "drums": _make_stem(sr, 2.0, amp=1.0, seed=2),
        "bass": _make_stem(sr, 2.0, amp=0.3, seed=3),
        "other": _make_stem(sr, 2.0, amp=0.1, seed=4),
    }
    sections = [_Section(0, 0.0, 2.0)]
    result = aggregate(stems, sections, sr=sr)
    assert dominant_stem(result[0]) == "drums"


def test_aggregate_handles_silent_section():
    sr = 22050
    stems = {name: np.zeros(sr * 2, dtype=np.float32) for name in DEFAULT_STEM_NAMES}
    sections = [_Section(0, 0.0, 1.0)]
    result = aggregate(stems, sections, sr=sr)
    # All zeros — no normalization happens; dominant_stem returns None
    assert dominant_stem(result[0]) is None


def test_aggregate_deterministic():
    sr = 22050
    np.random.seed(99)
    samples = np.random.RandomState(99).standard_normal(sr * 3).astype(np.float32)
    stems = {name: samples.copy() for name in DEFAULT_STEM_NAMES}
    sections = [_Section(0, 0.0, 3.0)]
    r1 = aggregate(stems, sections, sr=sr)
    r2 = aggregate(stems, sections, sr=sr)
    assert r1 == r2


def test_dominant_stem_threshold():
    # No stem above threshold → None
    energies = {"vocals": 0.30, "drums": 0.30, "bass": 0.20, "other": 0.20}
    assert dominant_stem(energies, threshold=0.35) is None
    # One stem clearly above
    energies2 = {"vocals": 0.50, "drums": 0.20, "bass": 0.20, "other": 0.10}
    assert dominant_stem(energies2, threshold=0.35) == "vocals"
