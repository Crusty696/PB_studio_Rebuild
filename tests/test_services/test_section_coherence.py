"""FR-S3-4 / Task-S3-4: Section-Coherence.

Innerhalb einer Section sollen Mood-Sims ≥ 0.7 belohnt werden;
an Section-Boundaries ist ein Switch (niedrige Mood-Sim) gewünscht.
Liefert Score ∈ [0, 1].
"""
import numpy as np

from services.pacing.section_coherence import compute_section_coherence


def _vec(seed: int):
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(1152).astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-9)


def test_high_sim_inside_section_score_high():
    a = _vec(1)
    s = compute_section_coherence(prev_emb=a, candidate_emb=a, boundary_distance_sec=4.0)
    assert s >= 0.95


def test_low_sim_inside_section_score_low():
    a = _vec(2)
    b = -a  # anti-aligned
    s = compute_section_coherence(prev_emb=a, candidate_emb=b, boundary_distance_sec=4.0)
    assert s < 0.05


def test_low_sim_at_boundary_score_high():
    """An der Boundary ist ein Switch (low mood-sim) gut."""
    # Konstruiere ein deterministisches anti-aligned Paar
    a = np.zeros(1152, dtype=np.float32); a[0] = 1.0
    b = -a  # cos = -1.0
    s_inside = compute_section_coherence(prev_emb=a, candidate_emb=b, boundary_distance_sec=4.0)
    s_boundary = compute_section_coherence(prev_emb=a, candidate_emb=b, boundary_distance_sec=0.1)
    # An der Boundary wird der Switch belohnt → höher als s_inside
    assert s_boundary > s_inside


def test_high_sim_at_boundary_score_low():
    """An der Boundary ist hoher Mood-Sim NICHT gewünscht."""
    a = _vec(4)
    s_boundary = compute_section_coherence(prev_emb=a, candidate_emb=a, boundary_distance_sec=0.1)
    s_inside = compute_section_coherence(prev_emb=a, candidate_emb=a, boundary_distance_sec=4.0)
    assert s_boundary < s_inside


def test_no_predecessor_returns_neutral():
    a = _vec(5)
    s = compute_section_coherence(prev_emb=None, candidate_emb=a, boundary_distance_sec=4.0)
    assert s == 0.5


def test_score_bounded():
    rng = np.random.default_rng(7)
    for _ in range(20):
        a = rng.standard_normal(1152).astype(np.float32)
        b = rng.standard_normal(1152).astype(np.float32)
        d = float(rng.uniform(0.0, 10.0))
        s = compute_section_coherence(a, b, d)
        assert 0.0 <= s <= 1.0
