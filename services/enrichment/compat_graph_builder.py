"""CompatGraphBuilder — Top-K cosine-nearest-neighbour edge builder for SigLIP embeddings."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CompatEdge:
    """One directed edge from source scene `a` to neighbour `b`, with its rank among a's top-K."""

    scene_id_a: int
    scene_id_b: int
    cosine_similarity: float
    rank_in_a: int  # 1-based: 1 = closest neighbour


class CompatGraphBuilder:
    """Build Top-K cosine-nearest-neighbour edges on SigLIP embeddings.

    Usage:
        builder = CompatGraphBuilder(top_k=20)
        edges = builder.build(embeddings, scene_ids)

    `embeddings` is (N, D) float, `scene_ids` is a list of len N of ints.
    Returns a list of CompatEdge tuples, both directions stored
    (so the table rows are (a→b, rank_in_a) and (b→a, rank_in_b) as
    separate entries — see Design §5.2 Step 4).
    """

    DEFAULT_TOP_K: int = 20

    def __init__(self, top_k: int = DEFAULT_TOP_K) -> None:
        self.top_k = top_k

    def build(
        self,
        embeddings: np.ndarray,
        scene_ids: list[int],
    ) -> list[CompatEdge]:
        """Build and return directed compat edges for all scenes.

        Args:
            embeddings: (N, D) float array of SigLIP embeddings.
            scene_ids: List of N integer scene IDs (no duplicates).

        Returns:
            List of CompatEdge objects (both directions stored as separate entries).

        Raises:
            ValueError: If embeddings.shape[0] != len(scene_ids) or scene_ids has duplicates.
        """
        n = embeddings.shape[0]

        # Validate shape
        if n != len(scene_ids):
            raise ValueError(
                f"embeddings.shape[0]={n} != len(scene_ids)={len(scene_ids)}"
            )

        # Validate no duplicate scene_ids
        if len(set(scene_ids)) != len(scene_ids):
            raise ValueError("scene_ids must not contain duplicates")

        # Edge case: 0 or 1 scenes — no neighbours possible
        if n <= 1:
            return []

        # Step 3: Compute L2-normalized matrix and cosine similarity matrix
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        # Avoid division by zero for zero-norm rows
        norms = np.where(norms == 0.0, 1.0, norms)
        e_hat = embeddings / norms

        # S[i, j] = cosine similarity between scene i and scene j
        s: np.ndarray = e_hat @ e_hat.T

        # Suppress diagonal so each row never picks itself
        np.fill_diagonal(s, -np.inf)

        # Step 4: For each row, find the K highest-similarity indices
        k = min(self.top_k, n - 1)

        edges: list[CompatEdge] = []

        for i in range(n):
            row = s[i]

            # argpartition gives us the K highest indices (unordered within the partition)
            top_k_indices: np.ndarray = np.argpartition(-row, k)[:k]

            # Sort those K by descending similarity for deterministic, correct ranking
            top_k_indices = top_k_indices[np.argsort(-row[top_k_indices])]

            for rank, j in enumerate(top_k_indices.tolist(), start=1):
                similarity = float(np.clip(float(s[i, j]), -1.0, 1.0))
                edges.append(
                    CompatEdge(
                        scene_id_a=scene_ids[i],
                        scene_id_b=scene_ids[int(j)],
                        cosine_similarity=similarity,
                        rank_in_a=rank,
                    )
                )

        return edges
