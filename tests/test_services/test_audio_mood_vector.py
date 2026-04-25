"""FR-S3-1 / Task-S3-1: Audio-Mood-Vector.

Liefert einen 1152-dim Vektor im SigLIP-Embedding-Raum als gewichtete
Linear-Kombination der 4 Shot-Klassen-Centroids (FR-S2-1) plus
Section-Type-Anker. Deterministisch + L2-normalisiert.
"""
import numpy as np

from services.pacing.audio_mood_vector import compute_audio_mood_vector
from services.pacing.shot_type_classifier import SHOT_CLASSES


def _stub_centroids(seed: int = 0):
    rng = np.random.default_rng(seed)
    out = {}
    for cls in SHOT_CLASSES:
        v = rng.standard_normal(1152).astype(np.float32)
        v = v / (np.linalg.norm(v) + 1e-9)
        out[cls] = v
    return out


def test_shape_and_dtype():
    centroids = _stub_centroids(seed=1)
    stems = {"vocals": 0.5, "drums": 0.3, "bass": 0.1, "other": 0.1}
    v = compute_audio_mood_vector(stems, "chorus", centroids)
    assert v.shape == (1152,)
    assert v.dtype == np.float32


def test_l2_normalized():
    centroids = _stub_centroids(seed=2)
    stems = {"vocals": 0.4, "drums": 0.4, "bass": 0.1, "other": 0.1}
    v = compute_audio_mood_vector(stems, "drop", centroids)
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-4


def test_deterministic():
    centroids = _stub_centroids(seed=3)
    stems = {"vocals": 0.4, "drums": 0.3, "bass": 0.2, "other": 0.1}
    a = compute_audio_mood_vector(stems, "chorus", centroids)
    b = compute_audio_mood_vector(stems, "chorus", centroids)
    assert np.array_equal(a, b)


def test_vocal_dominant_pulls_toward_vocal_centroid():
    centroids = _stub_centroids(seed=4)
    stems = {"vocals": 0.95, "drums": 0.02, "bass": 0.02, "other": 0.01}
    v = compute_audio_mood_vector(stems, "chorus", centroids)
    cos_vocal = float(np.dot(v, centroids["vocal_dominant"]))
    cos_drum = float(np.dot(v, centroids["drum_dominant"]))
    assert cos_vocal > cos_drum


def test_zero_stems_falls_back_to_uniform():
    centroids = _stub_centroids(seed=5)
    v = compute_audio_mood_vector({}, "chorus", centroids)
    assert v.shape == (1152,)
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-4


def test_unknown_section_type_no_crash():
    centroids = _stub_centroids(seed=6)
    stems = {"vocals": 0.3, "drums": 0.4, "bass": 0.2, "other": 0.1}
    v = compute_audio_mood_vector(stems, "unbekannter_typ", centroids)
    assert v.shape == (1152,)
