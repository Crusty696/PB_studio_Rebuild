"""NEUBAU-VOLLINTEGRATION T2.5.5 (FR-S2-1): shot_type_classifier verdrahtet.

Vorher: classify() nur von Tests/Demo erreicht; ClipFeatures hatten weder
Embedding (Cycle-12-deferred) noch Shot-Konfidenzen.
"""
import numpy as np

from services.pacing.bridge_mapping import build_clip_features
from services.pacing.shot_type_classifier import classify


def _centroids():
    rng = np.random.default_rng(7)
    cents = {}
    for k in ("vocal_dominant", "drum_dominant", "melody_dominant",
              "bass_dominant"):
        v = rng.normal(size=16).astype(np.float32)
        cents[k] = v / np.linalg.norm(v)
    return cents


class _Scene:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class TestBuildClipFeaturesShotConf:
    def test_precomputed_confidences_pass_through(self):
        conf = {"drum_dominant": 0.7, "vocal_dominant": 0.1,
                "melody_dominant": 0.1, "bass_dominant": 0.1}
        cf = build_clip_features(1, _Scene(
            id=10, motion_score=0.5, ai_mood="energetic", role="action",
            style_bucket_id=0, embedding=None, shot_confidences=conf))
        assert cf.shot_confidences == conf

    def test_classified_from_embedding_when_missing(self, monkeypatch):
        cents = _centroids()
        import services.pacing.shot_centroids as sc
        monkeypatch.setattr(sc, "get_shot_class_centroids", lambda: cents)
        emb = cents["drum_dominant"] * 2.0  # eindeutig drum-nah
        cf = build_clip_features(1, _Scene(
            id=10, motion_score=0.5, ai_mood=None, role=None,
            style_bucket_id=None, embedding=emb))
        assert cf.shot_confidences is not None
        assert max(cf.shot_confidences, key=cf.shot_confidences.get) == \
               "drum_dominant"
        assert abs(sum(cf.shot_confidences.values()) - 1.0) < 1e-6

    def test_none_without_embedding_and_conf(self, monkeypatch):
        import services.pacing.shot_centroids as sc
        monkeypatch.setattr(sc, "get_shot_class_centroids", lambda: _centroids())
        cf = build_clip_features(1, _Scene(
            id=10, motion_score=0.5, ai_mood=None, role=None,
            style_bucket_id=None, embedding=None))
        assert cf.shot_confidences is None
        assert cf.embedding is None


def test_classify_contract():
    cents = _centroids()
    conf = classify(cents["vocal_dominant"], cents)
    assert set(conf) == set(cents)
    assert max(conf, key=conf.get) == "vocal_dominant"
