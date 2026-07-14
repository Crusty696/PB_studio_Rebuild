"""workers/structure_enrichment.py — StructureEnrichmentWorker (T4.1).

Orchestrates the four P3 enrichment deep modules:
  1. RoleClassifier       — per-scene rule-based role
  2. MoodAnchorMatcher    — per-scene SigLIP → 10-class mood refinement
  3. StyleBucketClusterer — library-wide UMAP+HDBSCAN clustering (fit) or
                            nearest-centroid assignment (assign)
  4. CompatGraphBuilder   — cosine Top-K graph over all library scenes

Writes results to struct_clip_tags, struct_style_bucket, struct_compat_edge.
On success (and when clip_id is given) marks analysis_status.structure_enrichment=done.
"""

from __future__ import annotations

import logging
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PySide6.QtCore import QObject, Signal
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ENRICHER_VERSION: str = "v1"
REFIT_THRESHOLD: int = 50  # if fewer active struct_clip_tags rows → fit mode

# Process-wide mutex around the destructive fit-mode block (B-100 / BUG-6-b).
# Without it: a user-triggered library re-enrich (clip_id=None) and a
# pipeline-triggered per-clip enrich (clip_id=X) can BOTH enter fit-mode
# concurrently — both UPDATE struct_style_bucket SET active=0, both INSERT
# their own buckets, and the second writer's deactivation flips the first
# writer's freshly-inserted buckets to active=0. Result: struct_clip_tags
# rows from the first run reference inactive buckets; Stats panel hides them.
# The lock keeps fit-mode strictly serial across threads. Assign-mode is
# read-mostly and unaffected.
_FIT_MODE_LOCK: threading.Lock = threading.Lock()

_REDUCER_PATH = (
    Path(__file__).resolve().parent.parent / "storage" / "enricher" / "umap_v1.pkl"
)
_MOOD_ANCHORS_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "mood_anchors.npz"
)


# ---------------------------------------------------------------------------
# Default session factory (lazy import to avoid circular imports at module load)
# ---------------------------------------------------------------------------
def _default_session_factory() -> Session:
    """Return a NullPool session against the active project DB."""
    # nullpool_session() returns a context-manager, not a plain Session.
    # The worker needs a plain Session it manages manually so we can keep
    # a single transaction across all writes.  We therefore extract the
    # underlying engine URL and build a plain Session here.
    from sqlalchemy import create_engine as _ce
    from sqlalchemy.pool import NullPool

    from database.session import engine as _proxy_engine

    _eng = _ce(
        str(_proxy_engine.url),
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    # low-fix (Sweep 2026-07-14): markiere die selbst-erstellte Engine als
    # worker-owned, damit run() sie im finally disposen kann. Extern uebergebene
    # (evtl. geteilte) Engines tragen dieses Flag NICHT und bleiben unangetastet.
    _eng._pb_worker_owned = True
    return Session(_eng)


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------
class StructureEnrichmentWorker(QObject):
    """Orchestrates Role/Mood/Style/Compat enrichment for video scenes.

    Intended trigger: after ``scene_db_storage=done`` for a clip (T4.2 wires
    the hookup).  Also usable standalone for one-off library re-enrichment
    from a manual trigger.

    Qt signals (mirror conventions from workers/video.py):
        progress(int, str)  → (0-100, human-readable step name)
        finished(dict)      → {clip_id, scenes_enriched, buckets_fitted|None,
                               edges_written, mode}
        error(str)          → exception message on failure

    Public API:
        __init__(clip_id=None, session_factory=None, force_refit=False)
        run() -> dict
    """

    # Qt signal declarations
    progress = Signal(int, str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(
        self,
        clip_id: int | None = None,
        session_factory: Callable[[], Session] | None = None,
        force_refit: bool = False,
    ) -> None:
        super().__init__()
        self.clip_id = clip_id
        self._session_factory = session_factory or _default_session_factory
        self.force_refit = force_refit

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(self) -> dict[str, Any]:
        """Synchronous entry point; returns the same dict emitted via ``finished``."""
        try:
            result = self._run_impl()
            self.finished.emit(result)
            return result
        except Exception as exc:
            msg = str(exc)
            logger.error(
                "StructureEnrichmentWorker crashed: %s\n%s",
                msg,
                traceback.format_exc(),
            )
            self.error.emit(msg)
            return {"error": msg}

    # ------------------------------------------------------------------
    # Implementation
    # ------------------------------------------------------------------
    def _run_impl(self) -> dict[str, Any]:
        from services.enrichment.compat_graph_builder import CompatGraphBuilder
        from services.enrichment.mood_anchor_matcher import MoodAnchorMatcher
        from services.enrichment.role_classifier import classify_role
        from services.enrichment.style_bucket_clusterer import StyleBucketClusterer
        from services.vector_db_service import VectorDBService

        # ── Step 1: Load scenes to enrich ────────────────────────────────────
        self.progress.emit(5, "Lade Szenen …")
        session = self._session_factory()
        # B-100 / BUG-6-b: serialize the entire enrichment write phase across
        # threads. A user-triggered library re-enrich (clip_id=None) and a
        # pipeline-triggered per-clip enrich (clip_id=X) used to be able to
        # run concurrently, both UPDATE struct_style_bucket SET active=0 and
        # both INSERT new buckets — the second writer's deactivation would
        # flip the first writer's freshly-inserted buckets to active=0,
        # leaving struct_clip_tags rows pointing at inactive buckets.
        # Holding the lock for the full _do_enrich body (which ends with
        # session.commit()) is heavier-handed than necessary but keeps the
        # invariant trivially obvious: only one enrichment writes at a time.
        try:
            with _FIT_MODE_LOCK:
                return self._do_enrich(
                    session=session,
                    classify_role=classify_role,
                    MoodAnchorMatcher=MoodAnchorMatcher,
                    StyleBucketClusterer=StyleBucketClusterer,
                    CompatGraphBuilder=CompatGraphBuilder,
                    VectorDBService=VectorDBService,
                )
        finally:
            try:
                _eng = session.get_bind()
            except Exception:
                _eng = None
            try:
                session.close()
            except Exception:  # broad catch — close() errors are non-fatal
                pass
            # low-fix (Sweep 2026-07-14): nur die worker-eigene NullPool-Engine
            # disposen (Flag aus _default_session_factory) — verhindert Engine-Leak
            # pro run(), ohne extern geteilte Engines zu zerstoeren.
            if _eng is not None and getattr(_eng, "_pb_worker_owned", False):
                try:
                    _eng.dispose()
                except Exception:
                    pass

    def _do_enrich(  # noqa: C901 — complex but linear, steps match spec §T4.1
        self,
        *,
        session: Session,
        classify_role: Any,
        MoodAnchorMatcher: Any,
        StyleBucketClusterer: Any,
        CompatGraphBuilder: Any,
        VectorDBService: Any,
    ) -> dict[str, Any]:
        # ── 1. Load scenes ────────────────────────────────────────────────────
        self.progress.emit(10, "Lade Szenen aus DB …")
        if self.clip_id is not None:
            rows = session.execute(
                text(
                    "SELECT id, video_clip_id, start_time, end_time, "
                    "ai_caption, ai_mood FROM scenes WHERE video_clip_id = :cid"
                ),
                {"cid": self.clip_id},
            ).fetchall()
        else:
            rows = session.execute(
                text(
                    "SELECT id, video_clip_id, start_time, end_time, "
                    "ai_caption, ai_mood FROM scenes"
                )
            ).fetchall()

        if not rows:
            logger.warning("StructureEnrichmentWorker: no scenes found.")
            return {
                "clip_id": self.clip_id,
                "scenes_enriched": 0,
                "buckets_fitted": None,
                "edges_written": 0,
                "mode": "fit",
            }

        # Parse rows into lightweight dicts
        import json as _json

        scenes: list[dict[str, Any]] = []
        for r in rows:
            scene_id, clip_id, start_time, end_time, ai_caption_raw, ai_mood = r
            ai_caption: dict[str, Any] = {}
            if ai_caption_raw is not None:
                if isinstance(ai_caption_raw, str):
                    try:
                        ai_caption = _json.loads(ai_caption_raw)
                    except Exception:
                        ai_caption = {}
                elif isinstance(ai_caption_raw, dict):
                    ai_caption = ai_caption_raw
            scenes.append(
                {
                    "id": scene_id,
                    "clip_id": clip_id,
                    "start_time": start_time,
                    "end_time": end_time,
                    "ai_caption": ai_caption,
                    "ai_mood": ai_mood,
                }
            )

        # ── 2. Load embeddings ────────────────────────────────────────────────
        self.progress.emit(15, "Lade Embeddings …")
        vdb = VectorDBService()

        # get_all_embeddings() returns ALL library embeddings (not just this clip's).
        all_embeddings_matrix, all_metadata = vdb.get_all_embeddings()

        # Build scene_id → embedding index map.
        # VectorDB composite id = clip_id * 1_000_000 + scene_index.
        # We need to cross-reference DB scenes with VectorDB entries.
        # The VectorDB stores scene_index (0-based position within a clip),
        # NOT the DB scene id.  We match on clip_id + scene_index ordering.
        # Strategy: for each clip, sort its DB scenes by start_time to get
        # scene_index ordering (0,1,2,...) and match to VDB entries.
        id_to_emb_idx: dict[int, int] = {}
        if all_metadata:
            # Group VDB entries by clip_id (extracted from composite id)
            from collections import defaultdict

            vdb_by_clip: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for idx, meta in enumerate(all_metadata):
                composite_id = meta["id"]
                cid = int(composite_id) // 1_000_000
                vdb_by_clip[cid].append({"vdb_idx": idx, "meta": meta})

            # Group DB scenes by clip_id, sort by start_time → scene_index
            db_by_clip: dict[int, list[dict[str, Any]]] = defaultdict(list)
            for s in scenes:
                db_by_clip[s["clip_id"]].append(s)
            for cid in db_by_clip:
                db_by_clip[cid].sort(key=lambda x: x["start_time"])

            for cid, db_scenes_for_clip in db_by_clip.items():
                vdb_entries = sorted(
                    vdb_by_clip.get(cid, []),
                    key=lambda x: x["meta"]["scene_index"],
                )
                # Match by position (0-based scene_index)
                for pos, db_scene in enumerate(db_scenes_for_clip):
                    if pos < len(vdb_entries):
                        id_to_emb_idx[db_scene["id"]] = vdb_entries[pos]["vdb_idx"]

        # Filter out scenes that have no embedding
        enrichable_scenes = [s for s in scenes if s["id"] in id_to_emb_idx]
        if not enrichable_scenes:
            logger.warning(
                "StructureEnrichmentWorker: no scenes with embeddings found; "
                "check that VectorDB is populated."
            )
            return {
                "clip_id": self.clip_id,
                "scenes_enriched": 0,
                "buckets_fitted": None,
                "edges_written": 0,
                "mode": "fit",
            }

        # Build the embedding sub-matrix for the enrichable scenes
        enrichable_emb_indices = [id_to_emb_idx[s["id"]] for s in enrichable_scenes]
        enrichable_matrix = all_embeddings_matrix[
            enrichable_emb_indices
        ]  # (N_target, D)

        # ── 3. Role classification ────────────────────────────────────────────
        self.progress.emit(25, "Rollenklassifizierung …")
        role_results: list[tuple[str, float]] = []
        for s in enrichable_scenes:
            duration = float(s["end_time"]) - float(s["start_time"])
            tags: set[str] = set(
                s["ai_caption"].get("tags", []) if s["ai_caption"] else []
            )
            # motion_score is not stored on the Scene model; fall back to 0.5
            role, role_conf = classify_role(
                motion=0.5,
                duration=duration,
                tags=tags,
            )
            role_results.append((role, role_conf))

        # ── 4. Mood refinement ────────────────────────────────────────────────
        self.progress.emit(35, "Mood-Refinement …")
        anchors_path = str(_MOOD_ANCHORS_PATH)
        matcher = MoodAnchorMatcher(anchors_path=anchors_path)
        mood_results: list[tuple[str, float]] = []
        for i, s in enumerate(enrichable_scenes):
            emb = enrichable_matrix[i]
            mood, mood_conf = matcher.refine(
                embedding=emb,
                prior_mood=s["ai_mood"],
                prior_weight=0.6,
            )
            mood_results.append((mood, mood_conf))

        # ── 5. Style bucket ───────────────────────────────────────────────────
        self.progress.emit(50, "Style-Bucket-Clustering …")

        # Determine fit vs assign mode
        active_tags_count: int = (
            session.execute(text("SELECT COUNT(*) FROM struct_clip_tags")).scalar() or 0
        )
        active_buckets_count: int = (
            session.execute(
                text("SELECT COUNT(*) FROM struct_style_bucket WHERE active = 1")
            ).scalar()
            or 0
        )

        do_fit = (
            self.clip_id is None
            or self.force_refit
            or active_buckets_count == 0
            or active_tags_count < REFIT_THRESHOLD
        )

        clusterer = StyleBucketClusterer()
        mode = "fit" if do_fit else "assign"

        # scene_id → (bucket_db_id, style_distance)
        bucket_assignment: dict[int, tuple[int, float]] = {}
        buckets_fitted: int | None = None
        cluster_degraded = False

        if do_fit:
            # Use all library embeddings for fitting (not just target scenes)
            fit_matrix = all_embeddings_matrix  # shape (N_all, D)
            if fit_matrix.shape[0] < clusterer.min_cluster_size:
                # Fall back to enrichable_matrix if all_embeddings is too small
                fit_matrix = enrichable_matrix

            cluster_result = clusterer.fit(fit_matrix)
            labels = cluster_result.labels
            centroids = cluster_result.centroids
            reducer = cluster_result.reducer
            cluster_degraded = bool(getattr(cluster_result, "degraded", False))
            if cluster_degraded:
                logger.info(
                    "StructureEnrichment: kleine Library (%s Embeddings), nutze Single-Bucket-Degraded-Modus",
                    len(fit_matrix),
                )

            # ── Mark existing buckets inactive ────────────────────────────────
            session.execute(text("UPDATE struct_style_bucket SET active = 0"))

            # ── Insert new buckets ────────────────────────────────────────────
            now_dt = datetime.now(timezone.utc).replace(tzinfo=None)
            now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
            unique_labels = sorted(set(labels.tolist()) - {-1})
            label_to_db_id: dict[int, int] = {}

            for label_id in unique_labels:
                member_count = int((labels == label_id).sum())
                centroid_blob = (
                    centroids[unique_labels.index(label_id)]
                    .astype(np.float32)
                    .tobytes()
                )
                bucket_name = (
                    f"bucket_{label_id}_{now_dt.strftime('%Y%m%d%H%M%S%f')}"
                    f"_{id(self)}"
                )
                session.execute(
                    text(
                        "INSERT INTO struct_style_bucket "
                        "(name, description, centroid_embedding, member_count, "
                        " created_at, enricher_version, active) "
                        "VALUES (:name, NULL, :centroid, :member_count, :created_at, "
                        "        :version, 1)"
                    ),
                    {
                        "name": bucket_name,
                        "centroid": centroid_blob,
                        "member_count": member_count,
                        "created_at": now_str,
                        "version": ENRICHER_VERSION,
                    },
                )
                new_id: int = session.execute(
                    text("SELECT last_insert_rowid()")
                ).scalar_one()
                label_to_db_id[label_id] = new_id

            session.flush()
            buckets_fitted = len(unique_labels)

            # ── Persist reducer ───────────────────────────────────────────────
            if reducer is not None:
                _REDUCER_PATH.parent.mkdir(parents=True, exist_ok=True)
                StyleBucketClusterer.save_reducer(reducer, _REDUCER_PATH)

            # ── Assign scenes using fit_matrix labels ─────────────────────────
            # Map each enrichable scene → its label from fit_matrix.
            # Since fit_matrix may be all_embeddings_matrix, labels[i] aligns
            # with all_metadata[i].  We look up by vdb index.
            for i, s in enumerate(enrichable_scenes):
                vdb_idx = enrichable_emb_indices[i]
                if vdb_idx < len(labels):
                    label = int(labels[vdb_idx])
                else:
                    label = -1

                if label == -1:
                    # Noise point: assign to nearest centroid manually
                    if centroids.shape[0] == 0:
                        # No clusters at all; create a fallback bucket
                        label = 0
                        if 0 not in label_to_db_id:
                            # Edge: all points are noise; insert a single bucket
                            now_dt2 = datetime.now(timezone.utc).replace(tzinfo=None)
                            now_str2 = now_dt2.strftime("%Y-%m-%d %H:%M:%S")
                            centroid_blob2 = np.zeros(
                                clusterer.n_components, dtype=np.float32
                            ).tobytes()
                            session.execute(
                                text(
                                    "INSERT INTO struct_style_bucket "
                                    "(name, description, centroid_embedding, member_count, "
                                    " created_at, enricher_version, active) "
                                    "VALUES (:name, NULL, :centroid, 1, :created_at, :version, 1)"
                                ),
                                {
                                    "name": f"bucket_noise_{now_str2}",
                                    "centroid": centroid_blob2,
                                    "created_at": now_str2,
                                    "version": ENRICHER_VERSION,
                                },
                            )
                            noise_id: int = session.execute(
                                text("SELECT last_insert_rowid()")
                            ).scalar_one()
                            label_to_db_id[0] = noise_id
                            session.flush()
                    elif reducer is not None:
                        # Assign to nearest centroid
                        emb_i = enrichable_matrix[i].astype(np.float64)
                        reduced_pt = reducer.transform([emb_i])
                        dists = np.linalg.norm(centroids - reduced_pt, axis=1)
                        label = int(unique_labels[int(np.argmin(dists))])
                    else:
                        # B-491: Degraded-Modus (Single-Bucket / kein gefitteter
                        # Reducer) — keine Dim-Reduktion moeglich. Frueher crashte
                        # ``reducer.transform`` mit AttributeError ('NoneType').
                        # Noise-Point dem ersten vorhandenen Bucket zuordnen.
                        label = int(unique_labels[0]) if len(unique_labels) else 0

                bucket_db_id = label_to_db_id.get(
                    label, next(iter(label_to_db_id.values())) if label_to_db_id else 1
                )
                # Style distance: Euclidean from reduced embedding to centroid
                if cluster_degraded:
                    style_dist = 0.0
                elif centroids.shape[0] > 0 and label in unique_labels and reducer is not None:
                    centroid = centroids[unique_labels.index(label)]
                    reduced_pt = reducer.transform(
                        [enrichable_matrix[i].astype(np.float64)]
                    )
                    style_dist = float(np.linalg.norm(centroid - reduced_pt[0]))
                else:
                    style_dist = 0.0

                bucket_assignment[s["id"]] = (bucket_db_id, style_dist)

        else:
            # ── Assign mode ───────────────────────────────────────────────────
            # B-491 Followup (CRF-005): Ein degradierter Fit (kleine Library)
            # persistiert Buckets, aber KEINE Reducer-Datei (fit() liefert
            # reducer=None -> save_reducer wird uebersprungen, Z.421-423).
            # Ein spaeterer Assign-Lauf crashte dann hart: load_reducer wirft
            # FileNotFoundError. Erkennung "degraded" = fehlende Reducer-Datei
            # — dieselbe Quelle, die der Fit-Pfad schreibt.
            reducer = None
            if _REDUCER_PATH.exists():
                try:
                    reducer = StyleBucketClusterer.load_reducer(_REDUCER_PATH)
                except FileNotFoundError as load_exc:
                    # Belt+Suspenders: Datei zwischen exists() und open()
                    # verschwunden (Race/Cleanup) — kein Crash, Fallback.
                    logger.warning(
                        "StructureEnrichment assign: Reducer-Datei %s nicht "
                        "ladbar (%s) — Single-Bucket-Fallback.",
                        _REDUCER_PATH, load_exc,
                    )
                    reducer = None
            else:
                logger.warning(
                    "StructureEnrichment assign: keine Reducer-Datei %s "
                    "(degradierter Fit?) — Single-Bucket-Fallback statt Crash.",
                    _REDUCER_PATH,
                )

            # Load active bucket centroids
            bucket_rows = session.execute(
                text(
                    "SELECT id, centroid_embedding FROM struct_style_bucket "
                    "WHERE active = 1 ORDER BY id"
                )
            ).fetchall()

            bucket_ids = [r[0] for r in bucket_rows]
            centroids_list = [
                np.frombuffer(r[1], dtype=np.float32) for r in bucket_rows
            ]
            if not centroids_list:
                raise RuntimeError(
                    "assign mode requested but no active struct_style_bucket rows found"
                )
            centroids = np.stack(centroids_list, axis=0)

            if reducer is None:
                # B-491 Followup: Single-Bucket-Fallback wie im degradierten
                # Fit-Pfad — alle Szenen dem ersten aktiven Bucket zuordnen,
                # style_distance 0.0 (analog cluster_degraded im Fit-Pfad).
                cluster_degraded = True
                fallback_bucket_id = bucket_ids[0]
                for s in enrichable_scenes:
                    bucket_assignment[s["id"]] = (fallback_bucket_id, 0.0)
            else:
                for i, s in enumerate(enrichable_scenes):
                    emb_i = enrichable_matrix[i]
                    label_idx = clusterer.assign(emb_i, centroids, reducer)
                    bucket_db_id = bucket_ids[label_idx]
                    centroid = centroids[label_idx]
                    reduced_pt = reducer.transform([emb_i.astype(np.float64)])
                    style_dist = float(np.linalg.norm(centroid - reduced_pt[0]))
                    bucket_assignment[s["id"]] = (bucket_db_id, style_dist)

        # ── 6. Compat graph ───────────────────────────────────────────────────
        self.progress.emit(80, "Compat-Graph aufbauen …")
        builder = CompatGraphBuilder(top_k=20)

        # Build ordered scene id list matching all_embeddings_matrix rows
        # VDB ids: composite_id = clip_id * 1_000_000 + scene_index
        # We need actual DB scene ids.  Use id_to_emb_idx inverse.
        # For all library embeddings, we only know scene ids for enrichable_scenes.
        # For compat graph, use only the scenes we can resolve.
        # If clip_id=None (full library), all scenes are enrichable_scenes.
        resolved_scene_ids: list[int] = []
        resolved_emb_indices: list[int] = []
        for scene_id, vdb_idx in id_to_emb_idx.items():
            resolved_scene_ids.append(scene_id)
            resolved_emb_indices.append(vdb_idx)

        # Also include ALL library scenes if we are doing full-library mode
        # (not just the target scenes)
        if self.clip_id is None:
            # All enrichable scenes cover the full library
            compat_matrix = all_embeddings_matrix[resolved_emb_indices]
            compat_scene_ids = resolved_scene_ids
        else:
            # Load ALL scenes from DB to build a complete library graph
            all_rows = session.execute(
                text(
                    "SELECT id, video_clip_id, start_time FROM scenes ORDER BY video_clip_id, start_time"
                )
            ).fetchall()
            from collections import defaultdict as _dd

            all_db_by_clip: dict[int, list[Any]] = _dd(list)
            for r in all_rows:
                all_db_by_clip[r[1]].append(r)

            all_id_to_emb: dict[int, int] = {}
            vdb_by_clip2: dict[int, list[Any]] = _dd(list)
            for idx2, meta2 in enumerate(all_metadata):
                cid2 = int(meta2["id"]) // 1_000_000
                vdb_by_clip2[cid2].append({"vdb_idx": idx2, "meta": meta2})

            for cid2, db_s_list in all_db_by_clip.items():
                db_s_sorted = sorted(db_s_list, key=lambda x: x[2])
                vdb_list = sorted(
                    vdb_by_clip2.get(cid2, []), key=lambda x: x["meta"]["scene_index"]
                )
                for pos2, db_s in enumerate(db_s_sorted):
                    if pos2 < len(vdb_list):
                        all_id_to_emb[db_s[0]] = vdb_list[pos2]["vdb_idx"]

            compat_scene_ids = list(all_id_to_emb.keys())
            compat_emb_indices = [all_id_to_emb[sid] for sid in compat_scene_ids]
            compat_matrix = all_embeddings_matrix[compat_emb_indices]

        edges = builder.build(compat_matrix, compat_scene_ids)
        this_clip_scene_ids: set[int] = {s["id"] for s in enrichable_scenes}

        # Write edges to DB within our transaction
        if self.clip_id is None:
            # Full library: truncate and bulk-insert
            session.execute(text("DELETE FROM struct_compat_edge"))
            for edge in edges:
                session.execute(
                    text(
                        "INSERT OR REPLACE INTO struct_compat_edge "
                        "(scene_id_a, scene_id_b, cosine_similarity, rank_in_a) "
                        "VALUES (:a, :b, :sim, :rank)"
                    ),
                    {
                        "a": edge.scene_id_a,
                        "b": edge.scene_id_b,
                        "sim": edge.cosine_similarity,
                        "rank": edge.rank_in_a,
                    },
                )
        else:
            # Incremental: delete old edges for this clip's scenes, re-insert
            if this_clip_scene_ids:
                for sid in this_clip_scene_ids:
                    session.execute(
                        text(
                            "DELETE FROM struct_compat_edge "
                            "WHERE scene_id_a = :sid OR scene_id_b = :sid"
                        ),
                        {"sid": sid},
                    )
            # Insert only edges involving at least one target scene
            for edge in edges:
                if (
                    edge.scene_id_a in this_clip_scene_ids
                    or edge.scene_id_b in this_clip_scene_ids
                ):
                    session.execute(
                        text(
                            "INSERT OR REPLACE INTO struct_compat_edge "
                            "(scene_id_a, scene_id_b, cosine_similarity, rank_in_a) "
                            "VALUES (:a, :b, :sim, :rank)"
                        ),
                        {
                            "a": edge.scene_id_a,
                            "b": edge.scene_id_b,
                            "sim": edge.cosine_similarity,
                            "rank": edge.rank_in_a,
                        },
                    )

        # ── 7. Write struct_clip_tags ─────────────────────────────────────────
        self.progress.emit(95, "Schreibe struct_clip_tags …")
        now_str_write = (
            datetime.now(timezone.utc)
            .replace(tzinfo=None)
            .strftime("%Y-%m-%d %H:%M:%S")
        )
        for i, s in enumerate(enrichable_scenes):
            scene_id = s["id"]
            role, role_conf = role_results[i]
            mood, mood_conf = mood_results[i]
            bucket_db_id, style_dist = bucket_assignment.get(scene_id, (1, 0.0))

            session.execute(
                text(
                    "INSERT OR REPLACE INTO struct_clip_tags "
                    "(scene_id, role, role_confidence, mood_refined, mood_confidence, "
                    " style_bucket_id, style_distance, enriched_at, enricher_version) "
                    "VALUES (:sid, :role, :rc, :mood, :mc, :bid, :sdist, :eat, :ver)"
                ),
                {
                    "sid": scene_id,
                    "role": role,
                    "rc": role_conf,
                    "mood": mood,
                    "mc": mood_conf,
                    "bid": bucket_db_id,
                    "sdist": style_dist,
                    "eat": now_str_write,
                    "ver": ENRICHER_VERSION,
                },
            )

        # Commit everything atomically
        session.commit()

        # ── 8. AnalysisStatus ─────────────────────────────────────────────────
        if self.clip_id is not None:
            from services import analysis_status_service

            analysis_status_service.mark_done(
                media_type="video",
                media_id=self.clip_id,
                step_key="structure_enrichment",
                value_summary={
                    "scenes": len(enrichable_scenes),
                    "mode": mode,
                    "degraded": cluster_degraded,
                },
            )

        # Count edges written
        edges_written: int = (
            session.execute(text("SELECT COUNT(*) FROM struct_compat_edge")).scalar()
            or 0
        )

        self.progress.emit(100, "Enrichment abgeschlossen.")

        return {
            "clip_id": self.clip_id,
            "scenes_enriched": len(enrichable_scenes),
            "buckets_fitted": buckets_fitted,
            "edges_written": edges_written,
            "mode": mode,
            "degraded": cluster_degraded,
        }
