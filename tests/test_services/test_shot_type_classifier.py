"""FR-S2-1 / Task-S2-1: Shot-Type-Classifier.

16-Prompt-Ensemble × 4 Klassen (vocal/drum/melody/bass dominant) →
Klassen-Centroids → classify(clip_embedding) liefert Konfidenzen.

PRE-3 Refinement: Drum-Prompts sind auf non-human Motion umgeschrieben,
um die Confusion mit Vocal-Prompts zu reduzieren.

GPU-Tests laufen separat (test_shot_type_centroids_e2e in tests/spikes).
Hier nur die pure-function-Logik mit injizierten Centroids.
"""
from __future__ import annotations

import numpy as np
import pytest

from services.pacing.shot_type_classifier import (
    SHOT_PROMPTS,
    SHOT_CLASSES,
    classify,
    centroids_finite,
)


def _stub_centroids(seed: int = 0) -> dict[str, np.ndarray]:
    """4 zufällige normierte 1152-Vektoren, deterministisch."""
    rng = np.random.default_rng(seed)
    out = {}
    for cls in SHOT_CLASSES:
        v = rng.standard_normal(1152).astype(np.float32)
        v = v / (np.linalg.norm(v) + 1e-9)
        out[cls] = v
    return out


def test_shot_classes_and_prompts_present():
    assert set(SHOT_CLASSES) == {
        "vocal_dominant",
        "drum_dominant",
        "melody_dominant",
        "bass_dominant",
    }
    for cls in SHOT_CLASSES:
        assert cls in SHOT_PROMPTS
        assert len(SHOT_PROMPTS[cls]) >= 4
        assert len(set(SHOT_PROMPTS[cls])) == len(SHOT_PROMPTS[cls])


def test_drum_prompts_non_human_after_pre3_refinement():
    """PRE-3: Drum-Prompts dürfen keine Menschen mehr enthalten."""
    blacklist = {"person", "people", "crowd", "human", "face", "dancer", "dancers", "dancing", "figure", "figures"}
    for p in SHOT_PROMPTS["drum_dominant"]:
        words = set(p.lower().replace(",", " ").split())
        offenders = words & blacklist
        assert not offenders, f"Drum-Prompt {p!r} enthält Menschen-Term: {offenders}"


def test_classify_returns_softmax_dict():
    centroids = _stub_centroids(seed=42)
    clip_emb = np.random.RandomState(7).standard_normal(1152).astype(np.float32)
    clip_emb /= (np.linalg.norm(clip_emb) + 1e-9)
    out = classify(clip_emb, centroids)
    assert set(out.keys()) == set(SHOT_CLASSES)
    s = sum(out.values())
    assert abs(s - 1.0) < 1e-4
    for v in out.values():
        assert 0.0 <= v <= 1.0


def test_classify_picks_matching_centroid():
    centroids = _stub_centroids(seed=99)
    target_class = "drum_dominant"
    clip_emb = centroids[target_class].copy()
    out = classify(clip_emb, centroids)
    assert max(out, key=out.get) == target_class
    assert out[target_class] > 0.30


def test_classify_handles_zero_embedding():
    centroids = _stub_centroids(seed=1)
    zero = np.zeros(1152, dtype=np.float32)
    out = classify(zero, centroids)
    # Bei Zero-Vector → uniform distribution
    for v in out.values():
        assert abs(v - 0.25) < 1e-3


def test_classify_dim_mismatch_raises():
    centroids = _stub_centroids()
    bad_emb = np.zeros(512, dtype=np.float32)
    with pytest.raises(ValueError, match="dim"):
        classify(bad_emb, centroids)


def test_centroids_finite_validates_dict():
    good = _stub_centroids()
    assert centroids_finite(good) is True
    bad = dict(good)
    bad["vocal_dominant"] = np.array([1.0, np.nan] + [0.0] * 1150, dtype=np.float32)
    assert centroids_finite(bad) is False


def test_classify_deterministic():
    centroids = _stub_centroids(seed=5)
    emb = np.random.RandomState(11).standard_normal(1152).astype(np.float32)
    emb /= np.linalg.norm(emb)
    a = classify(emb, centroids)
    b = classify(emb, centroids)
    assert a == b
