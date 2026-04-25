"""D-023 P3: Graph-Service (NetworkX)."""
import numpy as np
import pytest

from services.graph.graph_service import GraphService


def test_add_node():
    g = GraphService()
    g.add_node(node_id="audio_1", node_type="audio", title="Track 1")
    assert g.has_node("audio_1")
    n = g.get_node("audio_1")
    assert n["node_type"] == "audio"
    assert n["title"] == "Track 1"


def test_add_edge_with_weight():
    g = GraphService()
    g.add_node("a", "audio", "A")
    g.add_node("b", "audio", "B")
    g.add_edge("a", "b", edge_type="similar", weight=0.85)
    assert g.has_edge("a", "b")
    e = g.get_edge("a", "b")
    assert e["weight"] == 0.85
    assert e["edge_type"] == "similar"


def test_add_edge_unknown_node_raises():
    g = GraphService()
    g.add_node("a", "audio", "A")
    with pytest.raises(KeyError):
        g.add_edge("a", "ghost", edge_type="similar", weight=0.5)


def test_neighbors():
    g = GraphService()
    for i in range(5):
        g.add_node(f"n{i}", "video", f"Clip {i}")
    g.add_edge("n0", "n1", "similar", 0.9)
    g.add_edge("n0", "n2", "similar", 0.7)
    g.add_edge("n0", "n3", "different", 0.3)
    neighbors = g.neighbors("n0")
    assert {x["target"] for x in neighbors} == {"n1", "n2", "n3"}


def test_neighbors_filter_by_edge_type():
    g = GraphService()
    g.add_node("a", "video", "a")
    g.add_node("b", "video", "b")
    g.add_node("c", "video", "c")
    g.add_edge("a", "b", "similar", 0.9)
    g.add_edge("a", "c", "different", 0.3)
    similar = g.neighbors("a", edge_type="similar")
    assert {x["target"] for x in similar} == {"b"}


def test_top_k_neighbors_by_weight():
    g = GraphService()
    g.add_node("a", "video", "a")
    for i, w in enumerate([0.3, 0.9, 0.5, 0.95, 0.1]):
        g.add_node(f"n{i}", "video", f"n{i}")
        g.add_edge("a", f"n{i}", "similar", w)
    top = g.top_k_neighbors("a", k=3)
    targets = [n["target"] for n in top]
    assert targets == ["n3", "n1", "n2"]  # weights 0.95, 0.9, 0.5


def test_build_from_embeddings_creates_similar_edges():
    rng = np.random.default_rng(42)
    embeddings = rng.standard_normal((10, 32)).astype(np.float32)
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    node_ids = [f"v{i}" for i in range(10)]
    g = GraphService()
    for nid in node_ids:
        g.add_node(nid, "video", nid)
    g.build_similarity_edges(node_ids, embeddings, k=3, min_similarity=0.0)
    n = g.neighbors("v0")
    # Self ist nicht in den Edges
    assert "v0" not in {x["target"] for x in n}
    assert len(n) >= 1


def test_node_count_and_edge_count():
    g = GraphService()
    g.add_node("a", "audio", "a")
    g.add_node("b", "audio", "b")
    g.add_edge("a", "b", "similar", 0.5)
    assert g.node_count() == 2
    assert g.edge_count() == 1
