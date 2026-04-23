"""StyleBucketClusterer -- UMAP preprocessing + HDBSCAN clustering on SigLIP embeddings.

Pipeline (Research Q2): 1152-d SigLIP -> UMAP(10-d) -> HDBSCAN.
Reducer is persisted via pickle so new clips can be assigned without refitting.
"""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import numpy as np

# umap.UMAP has no type stubs; we use Any for the public API surface.
_UMAPReducer = Any


class StyleBucketClusterer:
    """Cluster SigLIP embeddings into style buckets via UMAP preprocessing + HDBSCAN.

    Pipeline (Research Q2): 1152-d SigLIP -> UMAP(10-d) -> HDBSCAN.
    Reducer is persisted via pickle so new clips can be assigned without refitting.
    """

    DEFAULT_N_COMPONENTS: int = 10
    DEFAULT_N_NEIGHBORS: int = 30
    DEFAULT_MIN_DIST: float = 0.0
    DEFAULT_METRIC: str = "cosine"
    DEFAULT_MIN_CLUSTER_SIZE: int = 8
    DEFAULT_MIN_SAMPLES: int = 5

    def __init__(
        self,
        n_components: int = DEFAULT_N_COMPONENTS,
        n_neighbors: int = DEFAULT_N_NEIGHBORS,
        min_dist: float = DEFAULT_MIN_DIST,
        metric: str = DEFAULT_METRIC,
        min_cluster_size: int = DEFAULT_MIN_CLUSTER_SIZE,
        min_samples: int = DEFAULT_MIN_SAMPLES,
        random_state: int = 42,
    ) -> None:
        self.n_components = n_components
        self.n_neighbors = n_neighbors
        self.min_dist = min_dist
        self.metric = metric
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.random_state = random_state

    def fit(
        self,
        embeddings: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, _UMAPReducer]:
        """Fit UMAP+HDBSCAN on embeddings; return (labels, centroids, reducer).

        labels:     shape (N,) int; -1 = noise (HDBSCAN convention).
        centroids:  shape (K, reduced_dim) float -- mean of REDUCED embeddings per
                    non-noise cluster. Ordered by ascending label id (0, 1, ..., K-1).
                    Excludes noise.
        reducer:    the fitted umap.UMAP instance. Pickleable.
        """
        import umap  # type: ignore[import-untyped]  # lazy -- keeps module import cheap
        from sklearn.cluster import HDBSCAN  # type: ignore[import-untyped]  # lazy

        n_samples = embeddings.shape[0]
        if n_samples < self.min_cluster_size:
            raise ValueError(
                f"Need at least {self.min_cluster_size} embeddings for clustering, "
                f"got {n_samples}"
            )

        reducer: _UMAPReducer = umap.UMAP(
            n_neighbors=self.n_neighbors,
            min_dist=self.min_dist,
            n_components=self.n_components,
            metric=self.metric,
            random_state=self.random_state,
        )
        reduced: np.ndarray = reducer.fit_transform(embeddings)

        hdbscan: Any = HDBSCAN(
            min_cluster_size=self.min_cluster_size,
            min_samples=self.min_samples,
            cluster_selection_method="eom",
        )
        labels: np.ndarray = hdbscan.fit_predict(reduced)

        # Compute centroids in reduced space for each non-noise cluster.
        non_noise_labels = sorted(set(labels.tolist()) - {-1})
        if not non_noise_labels:
            centroids = np.empty((0, self.n_components), dtype=np.float64)
        else:
            centroids = np.stack(
                [reduced[labels == k].mean(axis=0) for k in non_noise_labels],
                axis=0,
            )

        return labels, centroids, reducer

    def assign(
        self,
        embedding: np.ndarray,
        centroids: np.ndarray,
        reducer: _UMAPReducer,
    ) -> int:
        """Assign a single new embedding to the nearest centroid.

        Returns label id in [0, K-1] using euclidean distance in the reduced space.
        Raises ValueError if centroids is empty.
        """
        if centroids.shape[0] == 0:
            raise ValueError(
                "assign() called with empty centroids; no non-noise clusters exist"
            )
        reduced_point: np.ndarray = reducer.transform(
            [embedding]
        )  # shape (1, n_components)
        distances = np.linalg.norm(centroids - reduced_point, axis=1)
        return int(np.argmin(distances))

    @staticmethod
    def save_reducer(reducer: _UMAPReducer, path: Path | str) -> None:
        """Pickle the reducer to `path` (parent dirs must exist)."""
        with open(path, "wb") as f:
            pickle.dump(reducer, f)

    @staticmethod
    def load_reducer(path: Path | str) -> _UMAPReducer:
        """Load a pickled reducer. Raises FileNotFoundError with readable message if missing."""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(
                f"UMAP reducer not found at '{p}'. "
                "Run StyleBucketClusterer.fit() and save_reducer() first."
            )
        with open(p, "rb") as f:
            return pickle.load(f)  # noqa: S301
