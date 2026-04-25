"""D-023 P2: Hybrid k-NN-Backend.

Strategie aus D-025:
- N < 10K  → numpy-BLAS (vollständig + brute-force, ohne Index-Overhead)
- N ≥ 10K  → USearch HNSW
- N > 50K  → ValueError (Hard-Cap, sonst geht VRAM/RAM kaputt)
"""
from __future__ import annotations

from typing import Literal

import numpy as np

# PRE-5 validiert: USearch-Wheel ist verfügbar auf Win64/Py3.11
try:
    import usearch.index as _usearch_index  # noqa: F401
    USEARCH_AVAILABLE = True
except ImportError:
    USEARCH_AVAILABLE = False

EPS = 1e-9

NUMPY_THRESHOLD = 10_000
HARD_CAP = 50_000


def pick_backend_strategy(n_items: int) -> Literal["numpy", "usearch"]:
    """Wählt das Backend abhängig von Index-Größe.

    Raises:
        ValueError: wenn n_items > HARD_CAP.
    """
    if n_items > HARD_CAP:
        raise ValueError(
            f"n_items={n_items} > HARD_CAP={HARD_CAP}. "
            "Index zu groß für GTX 1060 6GB. "
            "Sharding oder externes Storage nötig."
        )
    if n_items < NUMPY_THRESHOLD:
        return "numpy"
    if USEARCH_AVAILABLE:
        return "usearch"
    return "numpy"


class KnnBackend:
    """Wrapper-Klasse mit beiden Strategien.

    Achtung: numpy-Strategie ist brute-force-Linear, das ist für N<10K
    schneller als HNSW-Index-Build, ab 10K dreht das Verhältnis.
    """

    def __init__(self, strategy: Literal["numpy", "usearch"] | None = None):
        self._strategy: Literal["numpy", "usearch"] = strategy or "numpy"
        self._index_np: np.ndarray | None = None
        self._index_usearch = None

    def fit(self, embeddings: np.ndarray) -> None:
        """Index aufbauen. embeddings shape (N, D), float32."""
        if embeddings.size == 0:
            raise ValueError("Cannot fit on empty embeddings")
        if embeddings.ndim != 2:
            raise ValueError(f"Expected 2D embeddings, got shape {embeddings.shape}")
        if self._strategy == "numpy":
            # L2-normalize for cosine via dot
            arr = embeddings.astype(np.float32)
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            norms[norms < EPS] = 1.0
            self._index_np = arr / norms
        elif self._strategy == "usearch":
            if not USEARCH_AVAILABLE:
                raise RuntimeError("USearch not installed; fall back to numpy.")
            from usearch.index import Index
            n, d = embeddings.shape
            self._index_usearch = Index(ndim=d, metric="cos")
            keys = np.arange(n, dtype=np.int64)
            self._index_usearch.add(keys, embeddings.astype(np.float32))
        else:
            raise ValueError(f"Unknown strategy: {self._strategy}")

    def query(
        self,
        query: np.ndarray,
        k: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """k nächste Nachbarn. Liefert (distances[Q,k], indices[Q,k]).

        - distances sind Cosine-Distanzen ∈ [0, 2] (0 = perfekt match).
        - k wird automatisch auf N gecappt.
        """
        if query.ndim != 2:
            query = query.reshape(1, -1)
        if self._strategy == "numpy":
            if self._index_np is None:
                raise RuntimeError("Index not fitted")
            if query.shape[1] != self._index_np.shape[1]:
                raise ValueError(
                    f"dim mismatch: query={query.shape[1]}, "
                    f"index={self._index_np.shape[1]}"
                )
            n = self._index_np.shape[0]
            k = min(k, n)
            qn = query.astype(np.float32)
            qnorms = np.linalg.norm(qn, axis=1, keepdims=True)
            qnorms[qnorms < EPS] = 1.0
            qn = qn / qnorms
            sims = qn @ self._index_np.T  # (Q, N)
            dists = 1.0 - sims
            # argpartition + sort top-k
            top_k_idx = np.argpartition(dists, kth=min(k - 1, n - 1), axis=1)[:, :k]
            # Sort by actual distance (asc)
            sorted_idx_within = np.argsort(np.take_along_axis(dists, top_k_idx, axis=1), axis=1)
            top_k_idx = np.take_along_axis(top_k_idx, sorted_idx_within, axis=1)
            top_k_dists = np.take_along_axis(dists, top_k_idx, axis=1)
            return top_k_dists.astype(np.float32), top_k_idx.astype(np.int64)
        if self._strategy == "usearch":
            if self._index_usearch is None:
                raise RuntimeError("Index not fitted")
            results = self._index_usearch.search(query.astype(np.float32), k)
            return results.distances.astype(np.float32), results.keys.astype(np.int64)
        raise ValueError(f"Unknown strategy: {self._strategy}")
