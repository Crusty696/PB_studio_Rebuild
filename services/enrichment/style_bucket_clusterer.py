"""StyleBucketClusterer -- UMAP preprocessing + HDBSCAN clustering on SigLIP embeddings.

Pipeline (Research Q2): 1152-d SigLIP -> UMAP(10-d) -> HDBSCAN.
Reducer is persisted via pickle so new clips can be assigned without refitting.
"""

from __future__ import annotations

import logging
import os
import pickle
import shutil
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

# B-618 Frozen: Zeitbudget fuer den Cluster-Fit im Kind-Prozess. Deckt den
# nicht-cachebaren Numba-JIT (gemessen 79 s) plus den eigentlichen Fit auf
# echten Datenmengen ab.
#
# Die Konstante war beim Entfernen des Warmup-Blocks (Commit b8a73f7,
# 2026-08-12) versehentlich mit geloescht worden, obwohl ``_fit_subprocess``
# sie weiter benutzt. Folge: im Frozen-Build warf der Aufruf sofort einen
# NameError, der vom breiten ``except Exception`` geschluckt wurde — der
# Kind-Prozess-Pfad war damit tot und der Fit lief immer in-process, also
# genau in der Konstellation, gegen die er gebaut wurde. Im Dev-Run faellt das
# nicht auf, weil ``_fit_subprocess`` dort gar nicht aufgerufen wird.
_FIT_SUBPROCESS_TIMEOUT_S: float = 900.0

# ---------------------------------------------------------------------------
# B-618: Der Numba-JIT-Warmup wurde am 2026-08-12 ENTFERNT.
#
# Die Annahme des Tickets war, dass die Numba-JIT-Kompilierung von
# pynndescent den GIL haelt und dadurch den Qt-Main-Thread abwuergt. Eine
# vollstaendige Messung widerlegt das: 52 Cache-Dateien wirklich entfernt,
# freier System-RAM per Ballast auf 450-650 MB gedrueckt (der Co-Faktor, der
# allen frueheren Laeufen fehlte), Fit im QThread mit echtem Qt-Event-Loop.
# OHNE Warmup lief der JIT nachweislich in-process (Cache 0 -> 52 Dateien) und
# die laengste Main-Thread-Blockade betrug 0,13 s. LLVM gibt den GIL waehrend
# der Kompilierung offenbar frei.
#
# Damit war der Warmup ein reiner Verlust:
#   In-Process-JIT      4,3 s  (36,35 s kalt gegen 32,0 s warm)
#   Warmup-Subprozess  37-46 s
# Er bezahlte rund 40 Sekunden, um 4 zu sparen — und das auch nur einmal pro
# Installation, weil der Numba-Cache ohnehin auf der Platte liegt.
#
# Was den Prozess am 2026-07-13 wirklich getoetet hat, ist damit OFFEN. Der
# Absturz ist real dokumentiert, der JIT ist nach dieser Messung nicht die
# Ursache. Details: wiki/bugs/B-618-*.md.
#
# NICHT entfernt: der Kind-Prozess-Fit fuer den Frozen-Build
# (``_fit_subprocess`` + PB_CLUSTER_FIT in main.py). Der ist unabhaengig davon
# live bewiesen (F6-Endbeweis 2026-07-18) und loest ein anderes Problem —
# im Frozen kann Numba gar nicht cachen.
# ---------------------------------------------------------------------------

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

        Im Frozen-Build laeuft der Fit in einem KIND-Prozess (B-618): der
        Numba-JIT kostet dort 79 s und ist nicht cachebar (gemessen 2026-07-15,
        Cache bleibt leer — PyInstaller bundlet die Quellen, kein Cache-Locator).
        In-Process wuerde er den GIL halten und den Watchdog ausloesen. Schlaegt
        der Kind-Prozess fehl, faellt diese Methode auf den In-Process-Pfad
        zurueck (langsam, aber korrekt).
        """
        if getattr(sys, "frozen", False):
            child = self._fit_subprocess(embeddings)
            if child is not None:
                return child
            logger.warning(
                "B-618: Cluster-Fit im Kind-Prozess fehlgeschlagen — Fallback auf "
                "In-Process (kann den Main-Thread fuer ~80 s blockieren).",
            )
        return self._fit_inprocess(embeddings)

    def _fit_subprocess(self, embeddings: np.ndarray) -> "ClusterResult | None":
        """Fuehrt den Fit in einem eigenen Prozess aus (B-618, nur Frozen).

        Returns:
            ClusterResult, oder None wenn der Kind-Prozess nicht nutzbar war —
            dann muss der Aufrufer in-process weitermachen.
        """
        import json
        import tempfile

        tmpdir = tempfile.mkdtemp(prefix="pb_clusterfit_")
        in_path = os.path.join(tmpdir, "emb.npz")
        out_path = os.path.join(tmpdir, "res.pkl")
        job_path = os.path.join(tmpdir, "job.json")
        try:
            np.savez_compressed(in_path, embeddings=np.asarray(embeddings))
            with open(job_path, "w", encoding="utf-8") as jf:
                json.dump({
                    "in": in_path,
                    "out": out_path,
                    "params": {
                        "n_components": self.n_components,
                        "n_neighbors": self.n_neighbors,
                        "min_dist": self.min_dist,
                        "metric": self.metric,
                        "min_cluster_size": self.min_cluster_size,
                        "min_samples": self.min_samples,
                        "random_state": self.random_state,
                    },
                }, jf)

            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
            subprocess.run(
                [sys.executable],
                env={**os.environ, "PB_CLUSTER_FIT": job_path},
                check=True,
                timeout=_FIT_SUBPROCESS_TIMEOUT_S,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                creationflags=flags,
            )
            with open(out_path, "rb") as of:
                result = pickle.load(of)  # nosec B301
            logger.info("B-618: Cluster-Fit im Kind-Prozess erfolgreich.")
            return result
        except Exception as exc:  # noqa: BLE001 — jeder Fehler -> In-Process-Fallback
            logger.warning("B-618: Cluster-Fit-Subprozess fehlgeschlagen: %s", exc)
            return None
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _fit_inprocess(
        self,
        embeddings: np.ndarray,
    ) -> ClusterResult:
        """Der eigentliche Fit. Im Frozen wird das im Kind-Prozess aufgerufen
        (siehe ``fit`` und den PB_CLUSTER_FIT-Entrypoint in ``main.py``)."""
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
        # B-037 / B301: ``p`` zeigt auf den eigenen UMAP-Reducer-Cache
        # unter ``storage/`` — ausschliesslich von uns geschrieben in
        # ``save_reducer()``. Kein attacker-controlled Pickle-Source.
        with open(p, "rb") as f:
            return pickle.load(f)  # nosec B301  # noqa: S301
