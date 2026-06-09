"""FR-S3-2 / Task-S3-2: Mood-Match-Score.

r_mood = cosine_sim(audio_mood_vec, clip.caption_emb), gemappt auf [0, 1].
"""
import numpy as np

from services.pacing.mood_match_score import compute_mood_match_score


def test_perfect_alignment_score_one():
    v = np.random.RandomState(1).standard_normal(1152).astype(np.float32)
    v /= np.linalg.norm(v)
    s = compute_mood_match_score(v, v)
    assert abs(s - 1.0) < 1e-5


def test_orthogonal_score_half():
    a = np.zeros(1152, dtype=np.float32); a[0] = 1.0
    b = np.zeros(1152, dtype=np.float32); b[1] = 1.0
    assert abs(compute_mood_match_score(a, b) - 0.5) < 1e-5


def test_anti_aligned_score_zero():
    a = np.zeros(1152, dtype=np.float32); a[0] = 1.0
    b = np.zeros(1152, dtype=np.float32); b[0] = -1.0
    assert abs(compute_mood_match_score(a, b)) < 1e-5


def test_zero_vector_returns_neutral():
    v = np.random.RandomState(2).standard_normal(1152).astype(np.float32)
    z = np.zeros(1152, dtype=np.float32)
    assert compute_mood_match_score(v, z) == 0.5
    assert compute_mood_match_score(z, v) == 0.5


def test_dim_mismatch_raises():
    import pytest
    a = np.zeros(1152, dtype=np.float32)
    b = np.zeros(512, dtype=np.float32)
    with pytest.raises(ValueError):
        compute_mood_match_score(a, b)


def test_b344_siglip2_768_vs_legacy_1152_dim_mismatch_raises():
    """B-344: 768-dim Brain-V3 vectors must not be scored against 1152 anchors."""
    import pytest
    legacy_mood_anchor = np.zeros(1152, dtype=np.float32)
    siglip2_video_embedding = np.zeros(768, dtype=np.float32)

    with pytest.raises(ValueError, match="dim mismatch"):
        compute_mood_match_score(legacy_mood_anchor, siglip2_video_embedding)


def test_bounded_zero_one():
    rng = np.random.default_rng(0)
    for _ in range(20):
        a = rng.standard_normal(1152).astype(np.float32)
        b = rng.standard_normal(1152).astype(np.float32)
        s = compute_mood_match_score(a, b)
        assert 0.0 <= s <= 1.0
