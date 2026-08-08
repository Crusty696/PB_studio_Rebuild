"""B-729: Korpus-Kalibrierung des Rollen-Embedding-Klassifikators.

Messbefund (440 Szenen new_test_august, 2026-08-08): SigLIP-Text-
Prototypen haben pro Rolle systematisch verschiedene Basis-Naehe zu
allen Bildern (establishing mean-Cosine 0.047, action 0.004) — roher
argmax degeneriert zu establishing 317 / hero 120, action/detail/
filler/transition zusammen 3 von 440.

Vertraege:
1. Ohne set_corpus_calibration: Verhalten unveraendert.
2. Mit Kalibrierung: Rolle mit hohem Korpus-Bias verliert einen
   Grenzfall gegen die Rolle mit niedrigem Bias (score - alpha*mean).
3. alpha=0 == unkalibriert; alpha ausserhalb [0,1] -> ValueError.
4. Dim-/Leer-Korpus-Guards bleiben laut (ValueError).
5. classify_batch konsistent zu classify.
"""
from __future__ import annotations

import numpy as np
import pytest

from services.enrichment.role_embedding_classifier import RoleEmbeddingClassifier


@pytest.fixture()
def clf(tmp_path):
    # 3 orthogonale 8-d-Prototypen: a, b, c
    protos = {
        "role_a": np.eye(8, dtype=np.float32)[0],
        "role_b": np.eye(8, dtype=np.float32)[1],
        "role_c": np.eye(8, dtype=np.float32)[2],
    }
    path = tmp_path / "protos.npz"
    np.savez(path, **protos)
    return RoleEmbeddingClassifier(prototypes_path=path)


def _biased_corpus() -> np.ndarray:
    # Korpus liegt kollektiv nahe an role_a (Bias), gemischt zu b/c.
    rng = np.random.default_rng(729)
    base = np.zeros((50, 8), dtype=np.float32)
    base[:, 0] = 0.9                      # hoher a-Anteil ueberall
    base[:, 1] = rng.uniform(0, 0.3, 50)  # wenig b
    base[:, 2] = rng.uniform(0, 0.3, 50)  # wenig c
    return base


def test_uncalibrated_behavior_unchanged(clf):
    emb = np.array([0.8, 0.6, 0.0, 0, 0, 0, 0, 0], dtype=np.float32)
    role, conf = clf.classify(emb)
    assert role == "role_a"
    assert 0.0 < conf <= 1.0


def test_calibration_flips_biased_borderline_case(clf):
    emb = np.array([0.8, 0.6, 0.0, 0, 0, 0, 0, 0], dtype=np.float32)
    clf.set_corpus_calibration(_biased_corpus(), alpha=0.5)
    role, conf = clf.classify(emb)
    # role_a-Vorsprung (0.8 vs 0.6 roh) ist kleiner als der halbe
    # Korpus-Bias von role_a -> role_b gewinnt.
    assert role == "role_b"
    assert 0.0 < conf <= 1.0


def test_alpha_zero_equals_uncalibrated(clf):
    emb = np.array([0.8, 0.6, 0.0, 0, 0, 0, 0, 0], dtype=np.float32)
    before = clf.classify(emb)
    clf.set_corpus_calibration(_biased_corpus(), alpha=0.0)
    assert clf.classify(emb) == before


@pytest.mark.parametrize("alpha", [-0.1, 1.5])
def test_alpha_out_of_range_raises(clf, alpha):
    with pytest.raises(ValueError):
        clf.set_corpus_calibration(_biased_corpus(), alpha=alpha)


def test_corpus_guards(clf):
    with pytest.raises(ValueError):
        clf.set_corpus_calibration(np.zeros((0, 8), dtype=np.float32))
    with pytest.raises(ValueError):
        clf.set_corpus_calibration(np.ones((4, 5), dtype=np.float32))
    with pytest.raises(ValueError):
        clf.set_corpus_calibration(np.zeros((4, 8), dtype=np.float32))


def test_batch_matches_single(clf):
    clf.set_corpus_calibration(_biased_corpus(), alpha=0.5)
    embs = np.array([
        [0.8, 0.6, 0.0, 0, 0, 0, 0, 0],
        [0.0, 0.0, 1.0, 0, 0, 0, 0, 0],
    ], dtype=np.float32)
    batch = clf.classify_batch(embs)
    singles = [clf.classify(e) for e in embs]
    assert [b[0] for b in batch] == [s[0] for s in singles]
    for (_, cb), (_, cs) in zip(batch, singles):
        assert cb == pytest.approx(cs, abs=1e-5)
