import numpy as np
from typing import List, Dict

def build_edges(scene_ids: List[int], embeddings: np.ndarray, top_k: int = 20) -> List[Dict]:
    """
    Build a compatibility graph by identifying the Top-K nearest neighbors for each video scene 
    based on SigLIP embeddings using Cosine Similarity.
    
    Args:
        scene_ids: List of database IDs for each scene.
        embeddings: Numpy array of shape (N, D) where N is number of scenes and D is embedding dimension.
        top_k: Number of nearest neighbors to find for each scene.
        
    Returns:
        List of dictionaries containing edge information:
        {"scene_id_a": int, "scene_id_b": int, "cosine_similarity": float, "rank_in_a": int}
    """
    if len(scene_ids) == 0:
        return []
        
    n_scenes = len(scene_ids)
    # Ensure top_k is not larger than available neighbors (n_scenes - 1)
    actual_k = min(top_k, n_scenes - 1)
    
    if actual_k <= 0:
        return []

    # 1. Normalize embeddings to unit length for Cosine Similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    # Avoid division by zero
    norms[norms == 0] = 1.0
    norm_embeddings = embeddings / norms
    
    # 2. Compute Cosine Similarity Matrix (Punktprodukt normalisierter Vektoren)
    # Resulting matrix S where S[i, j] is similarity between scene i and j
    similarity_matrix = np.dot(norm_embeddings, norm_embeddings.T)
    
    # 3. Exclude self-similarity by setting diagonal to a very low value
    np.fill_diagonal(similarity_matrix, -1.0)
    
    edges = []
    
    # 4. Extract Top-K for each scene
    for i in range(n_scenes):
        scene_id_a = scene_ids[i]
        
        # Get similarities for current scene i
        similarities = similarity_matrix[i]
        
        # Get indices of top_k similarities
        # np.argsort returns indices that would sort an array. We want the largest, so we take the last ones.
        # However, np.argpartition is faster for just top_k
        top_indices = np.argpartition(similarities, -actual_k)[-actual_k:]
        
        # Sort these top_indices by similarity descending
        top_indices = top_indices[np.argsort(similarities[top_indices])[::-1]]
        
        for rank, idx_b in enumerate(top_indices, 1):
            edges.append({
                "scene_id_a": int(scene_id_a),
                "scene_id_b": int(scene_ids[idx_b]),
                "cosine_similarity": float(similarities[idx_b]),
                "rank_in_a": int(rank)
            })
            
    return edges
