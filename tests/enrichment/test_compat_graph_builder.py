import numpy as np
from services.enrichment.compat_graph_builder import CompatGraphBuilder, CompatEdge


def _orthonormal_basis_embeddings(n: int, dim: int = 1152) -> np.ndarray:
    """Each row is a distinct random-but-deterministic unit vector."""
    rng = np.random.default_rng(42)
    mat = rng.standard_normal((n, dim)).astype(np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    return mat / norms


def test_top_k_correctness_on_small_set() -> None:
    """5 embeddings, K=2 → each scene yields exactly 2 outgoing edges, no self-edges."""
    embeddings = _orthonormal_basis_embeddings(5)
    scene_ids = [10, 20, 30, 40, 50]
    builder = CompatGraphBuilder(top_k=2)
    edges = builder.build(embeddings, scene_ids)

    # Each of 5 sources emits 2 edges: 10 total
    assert len(edges) == 10
    # Each source appears exactly top_k times as scene_id_a
    from collections import Counter

    a_counts = Counter(e.scene_id_a for e in edges)
    assert all(count == 2 for count in a_counts.values())
    assert set(a_counts.keys()) == set(scene_ids)
    # No self-edges
    assert all(e.scene_id_a != e.scene_id_b for e in edges)


def test_rank_in_a_is_sorted_1_to_k() -> None:
    """Edges for a single source must have rank_in_a = 1..K in similarity-descending order."""
    embeddings = _orthonormal_basis_embeddings(8)
    scene_ids = list(range(8))
    builder = CompatGraphBuilder(top_k=3)
    edges = builder.build(embeddings, scene_ids)

    # Group by source; verify ranks
    for src in scene_ids:
        source_edges = [e for e in edges if e.scene_id_a == src]
        source_edges.sort(key=lambda e: e.rank_in_a)
        ranks = [e.rank_in_a for e in source_edges]
        assert ranks == [1, 2, 3], f"Source {src}: ranks = {ranks}"
        # similarity strictly non-increasing with rank
        sims = [e.cosine_similarity for e in source_edges]
        assert sims == sorted(
            sims, reverse=True
        ), f"Source {src}: sims not sorted desc: {sims}"


def test_symmetry_directions_stored_both_ways() -> None:
    """When a is in b's top-K AND b is in a's top-K, two separate edges are stored with their own rank_in_a."""
    # Construct 3 embeddings where 0 and 1 are each other's closest neighbour
    embeddings = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0],  # near row 0
            [0.0, 0.0, 1.0],  # far from both
        ],
        dtype=np.float32,
    )
    scene_ids = [100, 200, 300]
    builder = CompatGraphBuilder(top_k=2)
    edges = builder.build(embeddings, scene_ids)

    # Look for 100→200 AND 200→100 — both must be present, each with their own rank.
    ab = [e for e in edges if e.scene_id_a == 100 and e.scene_id_b == 200]
    ba = [e for e in edges if e.scene_id_a == 200 and e.scene_id_b == 100]
    assert len(ab) == 1 and len(ba) == 1
    # Both should be rank 1 (since 100 and 200 are each other's closest non-self)
    assert ab[0].rank_in_a == 1
    assert ba[0].rank_in_a == 1


def test_self_edges_excluded() -> None:
    """Never emit (a, a) edges — diagonal is suppressed."""
    embeddings = _orthonormal_basis_embeddings(10)
    scene_ids = list(range(10))
    builder = CompatGraphBuilder(top_k=9)  # K = N-1, would include self if not filtered
    edges = builder.build(embeddings, scene_ids)
    assert all(e.scene_id_a != e.scene_id_b for e in edges)
    # Per source we expect exactly N-1 = 9 edges
    from collections import Counter

    a_counts = Counter(e.scene_id_a for e in edges)
    assert all(count == 9 for count in a_counts.values())
