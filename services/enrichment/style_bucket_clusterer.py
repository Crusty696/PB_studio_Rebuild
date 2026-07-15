"""StyleBucketClusterer -- UMAP preprocessing + HDBSCAN clustering on SigLIP embeddings.

Pipeline (Research Q2): 1152-d SigLIP -> UMAP(10-d) -> HDBSCAN.
Reducer is persisted via pickle so new clips can be assigned without refitting.
"""

from __future__ import annotations

import logging
import os
import pickle
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# umap.UMAP has no type stubs; we use Any for the public API surface.
_UMAPReducer = Any

# ---------------------------------------------------------------------------
# B-618: Numba-JIT-Kaltstart-Warmup
#
# Der Lazy-Import von ``umap`` (direkt in ``fit()`` bzw. indirekt via
# ``pickle.load`` in ``load_reducer()`` — Unpickling des UMAP-Reducers
# importiert das umap-Modul) loest bei KALTEM Numba-Disk-Cache
# JIT-Kompilierung aus (pynndescent/distances.py). Diese haelt den GIL des
# App-Prozesses so lange, dass der Qt-Main-Thread eskalierend blockiert
# (Watchdog-Stacks 19.9s -> 24.0s -> 26.7s) und der Prozess ohne Traceback
# starb (live-belegt 2026-07-13). Bei warmem Cache dauert derselbe Pfad nur
# noch 1.5-4.7s und ist stabil (Warmlauf-Nachtest, 8x ausgeloest).
#
# Fix: Vor dem In-Process-Import einmalig einen Mini-``fit()`` in einem
# SEPARATEN Subprocess ausfuehren (``_WARMUP_SNIPPET``). Der Subprocess fuellt
# den Numba-Disk-Cache, ohne den GIL des App-Prozesses zu halten; der
# anschliessende In-Process-Import trifft dann den warmen Cache.
#
# Korrektur 2026-07-15: Frueher lief hier nur ``import umap``. Der Frozen-Verify
# zeigte, dass NUMBA_CACHE_DIR danach LEER blieb — Numba kompiliert die
# pynndescent-Kernel lazy, also erst beim ersten fit(). Der Warmup waermte den
# relevanten Cache also nicht. Siehe ``_WARMUP_SNIPPET``.
# ---------------------------------------------------------------------------
_WARMUP_TIMEOUT_S: float = 600.0
_WARMUP_LOCK = threading.Lock()
_WARMUP_STATE: dict[str, bool] = {"done": False}

# Ein blosser ``import umap`` reicht NICHT: Numba kompiliert die
# pynndescent-Kernel lazy, also erst beim ersten fit(). Live-Beleg
# (2026-07-15, Frozen): nach reinem Import blieb NUMBA_CACHE_DIR leer — der
# Warmup fuellte den Cache also gar nicht. Darum ein Mini-fit mit denselben
# JIT-relevanten Parametern wie ``fit()`` unten: metric="cosine" (kompiliert
# pynndescent/distances.py — der Pfad aus den Watchdog-Stacks) und
# float32-2D-Input (bestimmt die Numba-Signatur). Sample-Zahl und n_neighbors
# beeinflussen die Signatur nicht, darum bewusst winzig gehalten.
# Muss als Einzeiler-Snippet fuer ``python -c`` gueltig bleiben.
_WARMUP_SNIPPET: str = (
    "import numpy as np, umap; "
    "umap.UMAP(n_neighbors=5, min_dist=0.0, n_components=2, metric='cosine', "
    "random_state=42).fit(np.random.RandomState(0).rand(40, 32).astype(np.float32))"
)


def warm_umap_cache(timeout: float = _WARMUP_TIMEOUT_S) -> bool:
    """Fuellt den Numba-Disk-Cache fuer umap/pynndescent per Subprocess (B-618).

    Returns:
        True  -- In-Process-Import trifft warmen Zustand (Warmup gelaufen,
                 umap bereits importiert, oder Warmup schon erledigt).
        False -- Warmup konnte nicht laufen (Frozen-Build, Subprocess-Fehler
                 oder Timeout); der Aufrufer faellt auf den bisherigen
                 In-Process-Import zurueck (der den Cache dann selbst fuellt).

    Thread-safe und idempotent: Nur der erste Aufrufer zahlt die Warmup-Zeit;
    parallele Aufrufer warten am Lock, bis der Cache warm ist. Nach einem
    Fehlschlag wird NICHT erneut versucht -- der In-Process-Import
    kompiliert und persistiert den Cache ohnehin selbst.
    """
    with _WARMUP_LOCK:
        if _WARMUP_STATE["done"]:
            return True
        if "umap" in sys.modules:
            # JIT-Kosten in diesem Prozess bereits bezahlt.
            _WARMUP_STATE["done"] = True
            return True
        if getattr(sys, "frozen", False):
            # B-618 Frozen: sys.executable ist die App-EXE. ``app.exe -c "..."``
            # wuerde die GUI hochfahren statt einen Python-Einzeiler laufen zu
            # lassen. Loesung: die EXE mit PB_WARMUP_UMAP=1 re-invoken — main()
            # faengt das VOR GUI/QApplication/Watchdog ab, importiert umap
            # headless im KIND-Prozess und exitet. So JITet der Numba-Kaltstart
            # nie den GIL des Eltern-Main-Threads (kein Watchdog-Kill). Der Cache
            # landet in NUMBA_CACHE_DIR (runtime_hook_torch) und ist auch fuer
            # Folge-Starts warm.
            _frozen_flags = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            )
            try:
                subprocess.run(
                    [sys.executable],
                    env={**os.environ, "PB_WARMUP_UMAP": "1"},
                    check=True,
                    timeout=timeout,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=_frozen_flags,
                )
            except Exception as exc:  # noqa: BLE001 — Warmup darf Aufrufer nie crashen
                _WARMUP_STATE["done"] = True
                logger.warning(
                    "B-618: Frozen-UMAP-Warmup-Subprocess fehlgeschlagen (%s) — "
                    "Fallback auf In-Process-Import.",
                    exc,
                )
                return False
            _WARMUP_STATE["done"] = True
            logger.info(
                "B-618: Frozen-UMAP/Numba-Cache-Warmup-Subprocess erfolgreich."
            )
            return True
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        )
        try:
            subprocess.run(
                [sys.executable, "-c", _WARMUP_SNIPPET],
                check=True,
                timeout=timeout,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except Exception as exc:  # noqa: BLE001 — Warmup darf Aufrufer nie crashen
            _WARMUP_STATE["done"] = True
            logger.warning(
                "B-618: UMAP-Warmup-Subprocess fehlgeschlagen (%s) — "
                "Fallback auf In-Process-Import.",
                exc,
            )
            return False
        _WARMUP_STATE["done"] = True
        logger.info("B-618: UMAP/Numba-Disk-Cache-Warmup-Subprocess erfolgreich.")
        return True


@dataclass(frozen=True)
class ClusterResult:
    """Result wrapper that remains compatible with old tuple unpacking."""

    labels: np.ndarray
    centroids: np.ndarray
    reducer: _UMAPReducer | None
    probabilities: np.ndarray
    degraded: bool = False
    reason: str | None = None

    def __iter__(self):
        yield self.labels
        yield self.centroids
        yield self.reducer


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
    ) -> ClusterResult:
        """Fit UMAP+HDBSCAN on embeddings; return (labels, centroids, reducer).

        labels:     shape (N,) int; -1 = noise (HDBSCAN convention).
        centroids:  shape (K, reduced_dim) float -- mean of REDUCED embeddings per
                    non-noise cluster. Ordered by ascending label id (0, 1, ..., K-1).
                    Excludes noise.
        reducer:    the fitted umap.UMAP instance. Pickleable.
        """
        n_samples = embeddings.shape[0]
        if n_samples < self.min_cluster_size:
            labels = np.zeros(n_samples, dtype=np.int32)
            centroids = np.zeros((1, self.n_components), dtype=np.float32)
            return ClusterResult(
                labels=labels,
                centroids=centroids,
                reducer=None,
                probabilities=np.ones(n_samples, dtype=np.float32),
                degraded=True,
                reason=f"small_library:{n_samples}",
            )

        # B-618: Numba-Disk-Cache per Subprocess fuellen, bevor der Import den
        # GIL dieses Prozesses fuer die JIT-Kompilierung blockieren kann.
        warm_umap_cache()
        import umap  # type: ignore[import-untyped]  # lazy -- keeps module import cheap
        from sklearn.cluster import HDBSCAN  # type: ignore[import-untyped]  # lazy

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
        probabilities = np.asarray(
            getattr(hdbscan, "probabilities_", np.ones(len(labels))),
            dtype=np.float32,
        )

        # Compute centroids in reduced space for each non-noise cluster.
        non_noise_labels = sorted(set(labels.tolist()) - {-1})
        if not non_noise_labels:
            centroids = np.empty((0, self.n_components), dtype=np.float64)
        else:
            centroids = np.stack(
                [reduced[labels == k].mean(axis=0) for k in non_noise_labels],
                axis=0,
            )

        return ClusterResult(
            labels=labels,
            centroids=centroids,
            reducer=reducer,
            probabilities=probabilities,
        )

    def fit_predict(self, embeddings: np.ndarray) -> ClusterResult:
        """Fit and return a structured clustering result."""
        return self.fit(embeddings)

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
        # B-618: Unpickling des UMAP-Reducers importiert das umap-Modul und
        # loeste bei kaltem Numba-Disk-Cache GIL-blockierende JIT-Kompilierung
        # aus (App-Prozess starb ohne Traceback). Cache vorher per Subprocess
        # waermen.
        warm_umap_cache()
        # B-037 / B301: ``p`` zeigt auf den eigenen UMAP-Reducer-Cache
        # unter ``storage/`` — ausschliesslich von uns geschrieben in
        # ``save_reducer()``. Kein attacker-controlled Pickle-Source.
        with open(p, "rb") as f:
            return pickle.load(f)  # nosec B301  # noqa: S301
