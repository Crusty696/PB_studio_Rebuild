import pytest
import numpy as np
from services.enrichment.compat_graph_builder import build_edges

def test_build_edges_basic():
    """Ensure it returns the correct number of edges (top_k per scene)."""
    # 5 scenes, embeddings of size 10
    scene_ids = [101, 102, 103, 104, 105]
    embeddings = np.random.rand(5, 10).astype(np.float32)
    top_k = 2
    
    edges = build_edges(scene_ids, embeddings, top_k=top_k)
    
    # Each of the 5 scenes should have top_k neighbors
    assert len(edges) == 5 * top_k

def test_self_exclusion():
    """Ensure a scene is NOT its own neighbor in the graph."""
    scene_ids = [1, 2, 3]
    # Use identical embeddings to force high similarity
    embeddings = np.array([
        [1.0, 0.0],
        [1.0, 0.0],
        [1.0, 0.0]
    ], dtype=np.float32)
    
    edges = build_edges(scene_ids, embeddings, top_k=1)
    
    for edge in edges:
        assert edge["scene_id_a"] != edge["scene_id_b"]

def test_rank_order():
    """Ensure edges are correctly ranked by similarity."""
    scene_ids = [1, 2, 3, 4]
    # Scene 1 is identical to 2, and somewhat similar to 3
    embeddings = np.array([
        [1.0, 0.0, 0.0], # 1
        [1.0, 0.0, 0.0], # 2 (identical to 1)
        [0.7, 0.7, 0.0], # 3 (similar to 1)
        [0.0, 0.0, 1.0]  # 4 (different)
    ], dtype=np.float32)
    
    edges = build_edges(scene_ids, embeddings, top_k=2)
    
    # Filter edges for scene 1
    scene_1_edges = [e for e in edges if e["scene_id_a"] == 1]
    
    assert len(scene_1_edges) == 2
    # Rank 1 should be scene 2 (similarity 1.0)
    assert scene_1_edges[0]["scene_id_b"] == 2
    assert scene_1_edges[0]["rank_in_a"] == 1
    # Rank 2 should be scene 3
    assert scene_1_edges[1]["scene_id_b"] == 3
    assert scene_1_edges[1]["rank_in_a"] == 2
    
    # Check that rank 1 similarity is >= rank 2 similarity
    assert scene_1_edges[0]["cosine_similarity"] >= scene_1_edges[1]["cosine_similarity"]
