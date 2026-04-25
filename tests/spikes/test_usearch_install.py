"""PRE-5 Spike: USearch wheel availability + smoke test on Win/Py3.10/3.11."""
import numpy as np


def test_usearch_imports():
    import usearch
    assert hasattr(usearch, "__version__")


def test_usearch_index_basic():
    from usearch.index import Index

    idx = Index(ndim=128, metric="cos")
    vec = np.random.rand(128).astype("float32")
    idx.add(0, vec)
    assert len(idx) == 1

    matches = idx.search(vec, count=1)
    assert matches.keys[0] == 0


def test_usearch_siglip_dim():
    """Smoke-test with PB Studio's actual embedding dimension (1152)."""
    from usearch.index import Index

    idx = Index(ndim=1152, metric="cos")
    n = 100
    rng = np.random.default_rng(seed=42)
    vecs = rng.standard_normal((n, 1152)).astype("float32")
    for i, v in enumerate(vecs):
        idx.add(i, v)

    assert len(idx) == n
    matches = idx.search(vecs[0], count=5)
    assert matches.keys[0] == 0  # closest is itself
