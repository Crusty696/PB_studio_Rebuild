"""D-023 P2: Graph k-NN Backend (hybrid numpy<10K + USearch≥10K)."""
import numpy as np
import pytest

from services.graph.knn_backend import (
    KnnBackend,
    USEARCH_AVAILABLE,
    pick_backend_strategy,
)


def test_pick_strategy_numpy_for_small_n():
    assert pick_backend_strategy(n_items=500) == "numpy"
    assert pick_backend_strategy(n_items=9999) == "numpy"


def test_pick_strategy_usearch_for_large_n():
    expected = "usearch" if USEARCH_AVAILABLE else "numpy"
    assert pick_backend_strategy(n_items=10_000) == expected
    assert pick_backend_strategy(n_items=49_999) == expected


def test_pick_strategy_hard_cap_50k():
    """N > 50K → hart capped auf USearch oder ValueError."""
    with pytest.raises(ValueError):
        pick_backend_strategy(n_items=50_001)


def test_knn_numpy_self_search():
    rng = np.random.default_rng(42)
    embeddings = rng.standard_normal((100, 128)).astype(np.float32)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    backend = KnnBackend(strategy="numpy")
    backend.fit(embeddings)
    distances, indices = backend.query(embeddings[7:8], k=5)
    assert indices.shape == (1, 5)
    assert int(indices[0, 0]) == 7  # nearest to self == self


def test_knn_numpy_k_capped_at_n():
    rng = np.random.default_rng(0)
    embeddings = rng.standard_normal((10, 128)).astype(np.float32)
    backend = KnnBackend(strategy="numpy")
    backend.fit(embeddings)
    _, indices = backend.query(embeddings[:1], k=20)
    assert indices.shape[1] == 10  # k auto-capped


def test_knn_dim_mismatch_raises():
    embeddings = np.zeros((5, 64), dtype=np.float32)
    backend = KnnBackend(strategy="numpy")
    backend.fit(embeddings)
    bad_query = np.zeros((1, 32), dtype=np.float32)
    with pytest.raises(ValueError):
        backend.query(bad_query, k=3)


def test_knn_empty_index():
    backend = KnnBackend(strategy="numpy")
    with pytest.raises(RuntimeError):
        backend.query(np.zeros((1, 128), dtype=np.float32), k=3)


def test_knn_deterministic():
    rng = np.random.default_rng(99)
    embeddings = rng.standard_normal((50, 64)).astype(np.float32)
    backend1 = KnnBackend(strategy="numpy"); backend1.fit(embeddings)
    backend2 = KnnBackend(strategy="numpy"); backend2.fit(embeddings)
    d1, i1 = backend1.query(embeddings[10:11], k=5)
    d2, i2 = backend2.query(embeddings[10:11], k=5)
    assert np.array_equal(i1, i2)
