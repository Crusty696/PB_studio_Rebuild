"""tests/enrichment/test_role_embedding_classifier.py

Beweispflicht: die Rolle muss ueber Clips VARIIEREN. Der urspruengliche Bug
(27/27 Szenen ``filler``, ``role_confidence`` konstant 0.3) waere von einem
reinen Existenztest nicht gefangen worden — deshalb pruefen die Tests hier
explizit "Anzahl distinkter Rollen > 1" und "max-min der Konfidenz > 0".

Run:
    python -m pytest tests/enrichment/test_role_embedding_classifier.py -p no:randomly -q
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from services.enrichment.role_classifier import classify_role, classify_role_detail
from services.enrichment.role_embedding_classifier import (
    DEFAULT_PROTOTYPES_PATH,
    RoleEmbeddingClassifier,
    RolePrototypesUnavailable,
)

_HAS_PROTOTYPES = DEFAULT_PROTOTYPES_PATH.exists()
_needs_prototypes = pytest.mark.skipif(
    not _HAS_PROTOTYPES,
    reason=(
        "config/role_prototypes.npz fehlt — erzeugen mit "
        "python scripts/generate_role_prototypes.py"
    ),
)


# ---------------------------------------------------------------------------
# Ausfall-Verhalten: ehrlich statt still falsch
# ---------------------------------------------------------------------------
def test_missing_prototypes_raise_instead_of_silent_filler(tmp_path):
    with pytest.raises(RolePrototypesUnavailable):
        RoleEmbeddingClassifier(prototypes_path=tmp_path / "nope.npz")
    assert RoleEmbeddingClassifier.available(tmp_path / "nope.npz") is False


def test_empty_npz_raises(tmp_path):
    p = tmp_path / "empty.npz"
    np.savez(str(p))
    with pytest.raises(RolePrototypesUnavailable):
        RoleEmbeddingClassifier(prototypes_path=p)


def test_zero_vector_prototype_raises(tmp_path):
    p = tmp_path / "zero.npz"
    np.savez(str(p), a=np.zeros(8, dtype=np.float32), b=np.ones(8, dtype=np.float32))
    with pytest.raises(RolePrototypesUnavailable):
        RoleEmbeddingClassifier(prototypes_path=p)


# ---------------------------------------------------------------------------
# Synthetische Prototypen — deterministische Kernlogik
# ---------------------------------------------------------------------------
@pytest.fixture()
def synthetic(tmp_path) -> RoleEmbeddingClassifier:
    """4 orthogonale Prototypen in 8-d — Zuordnung ist damit eindeutig."""
    p = tmp_path / "proto.npz"
    eye = np.eye(4, 8, dtype=np.float32)
    np.savez(
        str(p),
        action=eye[0],
        detail=eye[1],
        establishing=eye[2],
        hero=eye[3],
    )
    return RoleEmbeddingClassifier(prototypes_path=p, temperature=0.05)


def test_nearest_prototype_wins(synthetic):
    for i, name in enumerate(["action", "detail", "establishing", "hero"]):
        emb = np.zeros(8, dtype=np.float32)
        emb[i] = 1.0
        role, conf = synthetic.classify(emb)
        assert role == name
        assert 0.0 < conf <= 1.0


def test_confidence_drops_when_the_embedding_is_ambiguous(synthetic):
    sharp_role, sharp_conf = synthetic.classify(
        np.array([1, 0, 0, 0, 0, 0, 0, 0], dtype=np.float32)
    )
    _amb_role, amb_conf = synthetic.classify(
        np.array([1, 1, 0, 0, 0, 0, 0, 0], dtype=np.float32)
    )
    assert sharp_role == "action"
    assert amb_conf < sharp_conf


def test_dim_mismatch_is_loud(synthetic):
    with pytest.raises(ValueError, match="dim"):
        synthetic.classify(np.ones(1152, dtype=np.float32))


def test_zero_norm_embedding_is_loud(synthetic):
    with pytest.raises(ValueError, match="zero L2 norm"):
        synthetic.classify(np.zeros(8, dtype=np.float32))


def test_batch_matches_single(synthetic):
    embs = np.eye(4, 8, dtype=np.float32)
    batch = synthetic.classify_batch(embs)
    single = [synthetic.classify(e) for e in embs]
    assert [r for r, _ in batch] == [r for r, _ in single]
    for (_, cb), (_, cs) in zip(batch, single):
        assert cb == pytest.approx(cs)


def test_batch_produces_varying_roles_and_confidences(tmp_path):
    """Der eigentliche Regressionsschutz gegen 'alles dieselbe Rolle'.

    Temperatur hier bewusst hoeher als der Default: bei exakt orthogonalen
    Synthetik-Prototypen saettigt der Softmax sonst auf glatte 1.0 und die
    Konfidenz-Varianz waere ein Artefakt der Testdaten, nicht der Logik.
    Realdaten-Verhalten deckt
    ``test_real_prototypes_yield_varying_roles_over_a_library`` ab.
    """
    p = tmp_path / "proto.npz"
    eye = np.eye(4, 8, dtype=np.float32)
    np.savez(str(p), action=eye[0], detail=eye[1], establishing=eye[2], hero=eye[3])
    clf = RoleEmbeddingClassifier(prototypes_path=p, temperature=0.5)

    rng = np.random.default_rng(7)
    embs = np.eye(4, 8, dtype=np.float32).repeat(5, axis=0)
    embs = embs + rng.standard_normal(embs.shape).astype(np.float32) * 0.05
    out = clf.classify_batch(embs)

    roles = {r for r, _ in out}
    confs = [c for _, c in out]
    assert len(roles) == 4, f"nur {len(roles)} distinkte Rollen: {roles}"
    assert max(confs) - min(confs) > 0.0
    assert len({round(c, 6) for c in confs}) > 1


# ---------------------------------------------------------------------------
# Echte, im Repo eingecheckte Prototypen
# ---------------------------------------------------------------------------
@_needs_prototypes
def test_real_prototypes_shape_and_roles():
    clf = RoleEmbeddingClassifier()
    # Muss zum Vector-Store passen (services/vector_db_service.EMBEDDING_DIM).
    assert clf.dim == 1152
    assert set(clf.roles) >= {"establishing", "action", "detail", "transition", "filler"}


@_needs_prototypes
def test_real_prototypes_are_not_degenerate():
    """Zwei Rollen duerfen nicht auf denselben Vektor zusammenfallen."""
    clf = RoleEmbeddingClassifier()
    protos = np.stack([clf._get_prototype(r) for r in clf.roles], axis=0)
    sims = protos @ protos.T
    off_diag = sims[~np.eye(len(clf.roles), dtype=bool)]
    assert off_diag.max() < 0.98, "zwei Rollen-Prototypen sind praktisch identisch"


@_needs_prototypes
def test_each_real_role_is_reachable():
    """Jede Rolle gewinnt fuer ihr eigenes Prototyp-Embedding."""
    clf = RoleEmbeddingClassifier()
    for role in clf.roles:
        got, conf = clf.classify(clf._get_prototype(role))
        assert got == role
        assert conf > 0.0


@_needs_prototypes
def test_real_prototypes_yield_varying_roles_over_a_library():
    """Ueber eine gemischte 'Library' entstehen mehrere Rollen + Konfidenzen."""
    clf = RoleEmbeddingClassifier()
    rng = np.random.default_rng(11)
    rows = []
    for role in clf.roles:
        base = clf._get_prototype(role)
        for _ in range(4):
            rows.append(base + rng.standard_normal(clf.dim).astype(np.float32) * 0.02)
    out = clf.classify_batch(np.stack(rows, axis=0))

    roles = {r for r, _ in out}
    confs = [c for _, c in out]
    assert len(roles) == len(clf.roles)
    assert max(confs) - min(confs) > 0.0
    assert len({round(c, 6) for c in confs}) > 1


# ---------------------------------------------------------------------------
# Regel-Pfad bleibt Vorrang-Override
# ---------------------------------------------------------------------------
def test_rule_path_reports_when_it_really_matched():
    role, conf, matched = classify_role_detail(
        motion=0.8, duration=0.5, tags={"blur"}
    )
    assert matched is True
    assert role == "transition"
    # Alte API unveraendert
    assert classify_role(motion=0.8, duration=0.5, tags={"blur"}) == (role, conf)


def test_rule_path_reports_fallback_as_not_matched():
    """Genau die Situation aus dem Befund: VLM-Tags treffen keine Regel."""
    role, conf, matched = classify_role_detail(
        motion=0.5,
        duration=7.4,
        tags={"jungle", "bioluminescent", "dancer", "mystical"},
    )
    assert matched is False
    assert (role, conf) == ("filler", 0.3)  # der stille Default von frueher


def test_repo_rules_file_still_present():
    """Die Regel-Datei bleibt als Override-Pfad erhalten, wird nicht geloescht."""
    rules = Path(__file__).resolve().parents[2] / "config" / "enrichment_rules.yaml"
    assert rules.exists()
