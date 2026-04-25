"""BrainService — aggregated read-views over Structure / Memory / Agent layers.

Design §3 (Structure / Memory / Agent): this service is the single read-only
aggregator the StudioBrainWindow tabs consult. It never writes; write-paths
go through DecisionRecorder, FeedbackService, PatternAggregator, etc.

Implementation notes:
- Raw SQL via sqlalchemy.text() — the context tables (mem_pacing_run,
  mem_decision, struct_*, mem_learned_pattern, mem_user_feedback_event) are
  defined in Alembic migrations and have no ORM classes. This follows the
  same style as services/pacing/decision_recorder.py and pattern_aggregator.py.
- Read methods are wrapped in functools.lru_cache so repeated tab-refreshes
  during a single session are cheap. Cache lifetime is tied to the service
  instance — construct a fresh BrainService when underlying data changes.

T10.1 scope: list_scene_count().
T10.2a extension: list_active_style_buckets, list_clips_with_tags,
list_distinct_roles, list_distinct_moods — backing the Structure tab's
Grid mode + filters.
T10.2b extension: get_clip_detail — backing the Structure tab's Inspector
panel on the right side of the grid.
T10.2c extension: structure_stats — library-level counts + mood coverage
lacuna, backing the Structure tab's Stats panel.
T10.2d extension: graph_nodes_and_edges — snapshot of enriched scenes +
compat-edges for the Structure tab's Graph mode.

T11.1 extension: list_pacing_runs, list_learned_patterns,
list_decisions_for_pattern, list_distinct_pattern_types — backing the
Memory tab's run-timeline + pattern table + drill-down.

T11.2 extension: list_runs_for_audit_selector, list_decisions_for_run,
get_decision_detail, list_structure_segments_for_run — backing the Audit
tab's run dropdown + cut table + details column + segment-strip.

T11.3 extension: list_audio_tracks, list_weights_profiles — backing the
Steer tab's audio-track selector and weights-profile dropdown.

P12 extension: story_map_data, list_runs_with_story_map_data — backing the
Story-Map dialog (waveform + section strip + tension curve + mood strip +
clip-thumb strip + thumbnail-click navigation signal).
"""

from __future__ import annotations

import functools
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from sqlalchemy import text

logger = logging.getLogger(__name__)


# Path to the canonical mood anchor prompt catalog used by
# services/enrichment/mood_anchor_matcher.py. The Stats panel reads the
# label list from here to compute the "mood coverage lacuna" (moods that
# are expected by the enrichment pipeline but have zero scenes yet).
_MOOD_ANCHORS_YAML: Path = (
    Path(__file__).resolve().parent.parent / "config" / "mood_anchors_v1.yaml"
)

# Directory containing the per-genre pacing-weights profile YAMLs. The Steer
# tab's profile dropdown (T11.3) enumerates ``*.yaml`` files from here and the
# "Edit profile" button opens the selected file in the OS default editor.
# Module-level so tests can monkeypatch this path to exercise the missing-dir
# failure mode without materialising a real directory.
_PACING_WEIGHTS_DIR: Path = (
    Path(__file__).resolve().parent.parent / "config" / "pacing_weights"
)


@functools.lru_cache(maxsize=1)
def _load_expected_moods() -> list[str]:
    """Return the sorted list of expected mood labels from the anchor YAML.

    The catalog at ``config/mood_anchors_v1.yaml`` has a top-level
    ``anchors:`` mapping whose keys are the canonical mood labels:

        anchors:
          euphoric:    "..."
          melancholic: "..."
          ...

    We extract those keys, return them alphabetically sorted (mirroring
    MoodAnchorMatcher which sorts names for deterministic ordering), and
    cache the result module-wide so every BrainService instance pays the
    YAML parse exactly once.

    Returns ``[]`` with a warning if the file is missing (fresh checkout
    without the config). Re-raises any parse / structural failure — the
    rebuild treats config errors as loud fails.
    """
    yaml_path = _MOOD_ANCHORS_YAML
    if not yaml_path.exists():
        logger.warning(
            "mood_anchors_v1.yaml not found at %s — returning empty "
            "expected-moods list",
            yaml_path,
        )
        return []

    with yaml_path.open("r", encoding="utf-8") as fh:
        payload = yaml.safe_load(fh)

    anchors = payload.get("anchors")
    if anchors is None:
        raise ValueError(
            f"{yaml_path}: missing top-level 'anchors:' key"
        )
    if not isinstance(anchors, dict):
        raise TypeError(
            f"{yaml_path}: 'anchors' must be a mapping of label -> prompt"
        )
    labels = [str(k) for k in anchors.keys()]
    return sorted(labels)


class BrainService:
    def __init__(self, session_factory: Callable[[], Any]) -> None:
        """Args:
        session_factory: callable returning a SQLAlchemy session (plain or
            context-manager style). Mirrors DecisionRecorder's contract.
        """
        self._session_factory = session_factory
        # Per-instance lru_cache wrapper so different BrainService instances
        # have independent caches (tests rely on this for freshness).
        self.list_scene_count = functools.lru_cache(maxsize=1)(
            self._list_scene_count_uncached
        )
        self.list_active_style_buckets = functools.lru_cache(maxsize=1)(
            self._list_active_style_buckets_uncached
        )
        self.list_distinct_roles = functools.lru_cache(maxsize=1)(
            self._list_distinct_roles_uncached
        )
        self.list_distinct_moods = functools.lru_cache(maxsize=1)(
            self._list_distinct_moods_uncached
        )
        # list_clips_with_tags takes kwargs — wrap the underlying positional
        # helper, and expose a kwargs-friendly facade below.
        # B-114 / BUG-9-b: maxsize bumped 32 → 128 so power-user
        # filter-combo exploration (>32 distinct combinations per session)
        # doesn't evict and re-hit DB on every refresh.
        self._list_clips_with_tags_cached = functools.lru_cache(maxsize=128)(
            self._list_clips_with_tags_uncached
        )
        # T10.2b: clip detail (Inspector panel). Keyed by scene_id (int).
        self.get_clip_detail = functools.lru_cache(maxsize=128)(
            self._get_clip_detail_uncached
        )
        # T10.2c: library-level stats (Stats panel). No arguments.
        self.structure_stats = functools.lru_cache(maxsize=1)(
            self._structure_stats_uncached
        )
        # T10.2d: graph snapshot (Graph mode). No arguments.
        self.graph_nodes_and_edges = functools.lru_cache(maxsize=1)(
            self._graph_nodes_and_edges_uncached
        )
        # T11.1: Memory tab read-views.
        self.list_pacing_runs = functools.lru_cache(maxsize=1)(
            self._list_pacing_runs_uncached
        )
        self.list_distinct_pattern_types = functools.lru_cache(maxsize=1)(
            self._list_distinct_pattern_types_uncached
        )
        # list_learned_patterns takes kwargs (type + min_confidence).
        # B-114 / BUG-9-b: maxsize 32 → 128 (siehe oben).
        self._list_learned_patterns_cached = functools.lru_cache(maxsize=128)(
            self._list_learned_patterns_uncached
        )
        # list_decisions_for_pattern is keyed on (pattern_id, limit).
        self.list_decisions_for_pattern = functools.lru_cache(maxsize=128)(
            self._list_decisions_for_pattern_uncached
        )
        # T11.2: Audit tab read-views.
        self.list_runs_for_audit_selector = functools.lru_cache(maxsize=1)(
            self._list_runs_for_audit_selector_uncached
        )
        self.get_decision_detail = functools.lru_cache(maxsize=64)(
            self._get_decision_detail_uncached
        )
        self.list_structure_segments_for_run = functools.lru_cache(maxsize=32)(
            self._list_structure_segments_for_run_uncached
        )
        # list_decisions_for_run takes kwargs → wrap positional helper.
        self._list_decisions_for_run_cached = functools.lru_cache(maxsize=32)(
            self._list_decisions_for_run_uncached
        )
        # T11.3: Steer tab read-views. ``list_audio_tracks`` hits the DB;
        # ``list_weights_profiles`` scans the filesystem. Both cache at
        # maxsize=1 — the scans are cheap, but registering caches in
        # ``_cached_attrs`` means ``invalidate()`` can clear them when the
        # user hits "Refresh" (new track uploaded, profile edited on disk).
        self.list_audio_tracks = functools.lru_cache(maxsize=1)(
            self._list_audio_tracks_uncached
        )
        self.list_weights_profiles = functools.lru_cache(maxsize=1)(
            self._list_weights_profiles_uncached
        )
        # P12: Story-Map dialog reads. story_map_data is keyed on run_id;
        # list_runs_with_story_map_data is parameter-free.
        self.story_map_data = functools.lru_cache(maxsize=16)(
            self._story_map_data_uncached
        )
        self.list_runs_with_story_map_data = functools.lru_cache(maxsize=1)(
            self._list_runs_with_story_map_data_uncached
        )
        # Names of attributes wrapped in lru_cache — invalidate() iterates this
        # list so new cached endpoints only need to be added in one place.
        self._cached_attrs: tuple[str, ...] = (
            "list_scene_count",
            "list_active_style_buckets",
            "list_distinct_roles",
            "list_distinct_moods",
            "_list_clips_with_tags_cached",
            "get_clip_detail",
            "structure_stats",
            "graph_nodes_and_edges",
            "list_pacing_runs",
            "list_distinct_pattern_types",
            "_list_learned_patterns_cached",
            "list_decisions_for_pattern",
            "list_runs_for_audit_selector",
            "get_decision_detail",
            "list_structure_segments_for_run",
            "_list_decisions_for_run_cached",
            "list_audio_tracks",
            "list_weights_profiles",
            "story_map_data",
            "list_runs_with_story_map_data",
        )

    def invalidate(self) -> None:
        """Clear every per-instance lru_cache on this service.

        Call this before a read when the caller knows the underlying DB has
        been mutated externally (e.g. StructureTab.refresh after the enricher
        reruns). Without this, repeated reads with identical kwargs would
        return stale data for the lifetime of the BrainService instance.
        """
        for attr_name in self._cached_attrs:
            wrapped = getattr(self, attr_name, None)
            cache_clear = getattr(wrapped, "cache_clear", None)
            if callable(cache_clear):
                cache_clear()

    # ── Session helpers ────────────────────────────────────────────────────
    def _open_session(self) -> tuple[Any, bool]:
        """Return (session, ownership). Ownership=True means we entered a
        context-manager and must __exit__ it on close."""
        session = self._session_factory()
        ownership = False
        if hasattr(session, "__enter__") and not hasattr(session, "execute"):
            session = session.__enter__()
            ownership = True
        return session, ownership

    @staticmethod
    def _close_session(session: Any, ownership: bool) -> None:
        try:
            if ownership:
                session.__exit__(None, None, None)
            else:
                close = getattr(session, "close", None)
                if callable(close):
                    close()
        except Exception:  # best-effort cleanup
            pass

    # ── T10.1: scene count ─────────────────────────────────────────────────
    def _list_scene_count_uncached(self) -> int:
        """Return the total number of rows in the `scenes` table."""
        session, ownership = self._open_session()
        try:
            result = session.execute(text("SELECT COUNT(*) FROM scenes"))
            return int(result.scalar() or 0)
        finally:
            self._close_session(session, ownership)

    # ── T10.2a: style buckets ──────────────────────────────────────────────
    def _list_active_style_buckets_uncached(self) -> list[dict[str, Any]]:
        """Return active style buckets (Feasibility-R4: active=1 only).

        Each dict has keys: id, name, description, member_count.
        Ordered by name ASC for stable dropdown presentation.
        """
        session, ownership = self._open_session()
        try:
            rows = (
                session.execute(
                    text(
                        "SELECT id, name, description, member_count "
                        "FROM struct_style_bucket "
                        "WHERE active = 1 "
                        "ORDER BY name ASC"
                    )
                )
                .mappings()
                .all()
            )
            return [
                {
                    "id": int(r["id"]),
                    "name": r["name"],
                    "description": r["description"],
                    "member_count": int(r["member_count"] or 0),
                }
                for r in rows
            ]
        finally:
            self._close_session(session, ownership)

    # ── T10.2a: distinct filter values ─────────────────────────────────────
    def _list_distinct_roles_uncached(self) -> list[str]:
        session, ownership = self._open_session()
        try:
            rows = session.execute(
                text(
                    "SELECT DISTINCT role FROM struct_clip_tags "
                    "WHERE role IS NOT NULL ORDER BY role ASC"
                )
            ).all()
            return [r[0] for r in rows if r[0] is not None]
        finally:
            self._close_session(session, ownership)

    def _list_distinct_moods_uncached(self) -> list[str]:
        session, ownership = self._open_session()
        try:
            rows = session.execute(
                text(
                    "SELECT DISTINCT mood_refined FROM struct_clip_tags "
                    "WHERE mood_refined IS NOT NULL ORDER BY mood_refined ASC"
                )
            ).all()
            return [r[0] for r in rows if r[0] is not None]
        finally:
            self._close_session(session, ownership)

    # ── T10.2a: clip-tag rows with optional filters ────────────────────────
    def list_clips_with_tags(
        self,
        role: Optional[str] = None,
        mood: Optional[str] = None,
        style_bucket_id: Optional[int] = None,
        min_role_confidence: float = 0.0,
        min_usage_count: int = 0,
    ) -> list[dict[str, Any]]:
        """Return rows joined across struct_clip_tags + struct_style_bucket
        + (LEFT JOIN on mem_decision for usage count).

        Only scenes that have a struct_clip_tags row are returned (inner join).
        Grouping into style-bucket sections happens in the UI widget — this
        method returns a flat list sorted by (style_bucket_id, scene_id) ASC.

        Filter semantics:
          - role / mood: exact match (None = no filter).
          - style_bucket_id: exact match (None = no filter).
          - min_role_confidence: role_confidence >= threshold.
          - min_usage_count: usage_count >= threshold (post-aggregation).
        """
        return self._list_clips_with_tags_cached(
            role, mood, style_bucket_id, float(min_role_confidence), int(min_usage_count)
        )

    def _list_clips_with_tags_uncached(
        self,
        role: Optional[str],
        mood: Optional[str],
        style_bucket_id: Optional[int],
        min_role_confidence: float,
        min_usage_count: int,
    ) -> list[dict[str, Any]]:
        session, ownership = self._open_session()
        try:
            sql = """
                SELECT
                    t.scene_id            AS scene_id,
                    t.role                AS role,
                    t.role_confidence     AS role_confidence,
                    t.mood_refined        AS mood_refined,
                    t.mood_confidence     AS mood_confidence,
                    t.style_bucket_id     AS style_bucket_id,
                    b.name                AS style_bucket_name,
                    t.style_distance      AS style_distance,
                    s.video_clip_id       AS video_clip_id,
                    s.start_time          AS start_time,
                    s.end_time            AS end_time,
                    COALESCE(u.usage_count, 0) AS usage_count
                FROM struct_clip_tags t
                INNER JOIN scenes s ON s.id = t.scene_id
                LEFT JOIN struct_style_bucket b ON b.id = t.style_bucket_id
                LEFT JOIN (
                    SELECT scene_id, COUNT(*) AS usage_count
                    FROM mem_decision
                    WHERE scene_id IS NOT NULL
                    GROUP BY scene_id
                ) u ON u.scene_id = t.scene_id
                WHERE 1 = 1
            """
            params: dict[str, Any] = {}
            if role is not None:
                sql += " AND t.role = :role"
                params["role"] = role
            if mood is not None:
                sql += " AND t.mood_refined = :mood"
                params["mood"] = mood
            if style_bucket_id is not None:
                sql += " AND t.style_bucket_id = :bucket"
                params["bucket"] = int(style_bucket_id)
            if min_role_confidence > 0.0:
                sql += " AND t.role_confidence >= :min_conf"
                params["min_conf"] = float(min_role_confidence)
            if min_usage_count > 0:
                sql += " AND COALESCE(u.usage_count, 0) >= :min_usage"
                params["min_usage"] = int(min_usage_count)
            sql += " ORDER BY t.style_bucket_id ASC, t.scene_id ASC"

            rows = session.execute(text(sql), params).mappings().all()
            return [
                {
                    "scene_id": int(r["scene_id"]),
                    "role": r["role"],
                    "role_confidence": float(r["role_confidence"] or 0.0),
                    "mood_refined": r["mood_refined"],
                    "mood_confidence": float(r["mood_confidence"] or 0.0),
                    "style_bucket_id": (
                        int(r["style_bucket_id"])
                        if r["style_bucket_id"] is not None
                        else None
                    ),
                    "style_bucket_name": r["style_bucket_name"],
                    "style_distance": float(r["style_distance"] or 0.0),
                    "video_clip_id": (
                        int(r["video_clip_id"])
                        if r["video_clip_id"] is not None
                        else None
                    ),
                    "start_time": float(r["start_time"] or 0.0),
                    "end_time": float(r["end_time"] or 0.0),
                    "usage_count": int(r["usage_count"] or 0),
                }
                for r in rows
            ]
        finally:
            self._close_session(session, ownership)

    # ── T10.2b: single-clip detail for the Inspector panel ─────────────────
    def _get_clip_detail_uncached(self, scene_id: int) -> Optional[dict[str, Any]]:
        """Return a rich detail dict for the Inspector panel, or None if the
        scene has no struct_clip_tags row yet (i.e. not enriched).

        Result dict shape:
            scene_id                (int)
            video_file_basename     (str | None)
            start_time              (float)
            end_time                (float)
            role                    (str | None)
            role_confidence         (float)
            mood_refined            (str | None)
            mood_confidence         (float)
            style_bucket_id         (int | None)
            style_bucket_name       (str | None)
            style_distance          (float)
            neighbors               (list[dict[str, Any]]) — up to 5, ordered by
                                      rank_in_a ASC; each dict has
                                      scene_id / cosine_similarity / role /
                                      mood_refined (role/mood may be None if
                                      the neighbor has no struct_clip_tags).
            usage_count             (int)
            last_run_completed_at   (str | None) — ISO timestamp of the most
                                      recent mem_pacing_run.completed_at that
                                      referenced this scene_id via mem_decision.

        Single session, single transaction — no N+1 queries for neighbors or
        usage.
        """
        sid = int(scene_id)
        session, ownership = self._open_session()
        try:
            header_sql = """
                SELECT
                    t.scene_id            AS scene_id,
                    t.role                AS role,
                    t.role_confidence     AS role_confidence,
                    t.mood_refined        AS mood_refined,
                    t.mood_confidence     AS mood_confidence,
                    t.style_bucket_id     AS style_bucket_id,
                    b.name                AS style_bucket_name,
                    t.style_distance      AS style_distance,
                    s.start_time          AS start_time,
                    s.end_time            AS end_time,
                    v.file_path           AS video_file_path,
                    COALESCE(u.usage_count, 0) AS usage_count,
                    u.last_completed_at   AS last_completed_at
                FROM struct_clip_tags t
                INNER JOIN scenes s            ON s.id = t.scene_id
                LEFT  JOIN struct_style_bucket b ON b.id = t.style_bucket_id
                LEFT  JOIN video_clips v       ON v.id = s.video_clip_id
                LEFT  JOIN (
                    SELECT
                        d.scene_id            AS scene_id,
                        COUNT(*)              AS usage_count,
                        MAX(r.completed_at)   AS last_completed_at
                    FROM mem_decision d
                    LEFT JOIN mem_pacing_run r ON r.id = d.run_id
                    WHERE d.scene_id = :sid
                    GROUP BY d.scene_id
                ) u ON u.scene_id = t.scene_id
                WHERE t.scene_id = :sid
            """
            header = (
                session.execute(text(header_sql), {"sid": sid})
                .mappings()
                .first()
            )
            if header is None:
                return None

            neighbors_sql = """
                SELECT
                    e.scene_id_b        AS scene_id,
                    e.cosine_similarity AS cosine_similarity,
                    t.role              AS role,
                    t.mood_refined      AS mood_refined
                FROM struct_compat_edge e
                LEFT JOIN struct_clip_tags t ON t.scene_id = e.scene_id_b
                WHERE e.scene_id_a = :sid
                ORDER BY e.rank_in_a ASC
                LIMIT 5
            """
            neighbor_rows = (
                session.execute(text(neighbors_sql), {"sid": sid})
                .mappings()
                .all()
            )
            neighbors = [
                {
                    "scene_id": int(n["scene_id"]),
                    "cosine_similarity": float(n["cosine_similarity"] or 0.0),
                    "role": n["role"],
                    "mood_refined": n["mood_refined"],
                }
                for n in neighbor_rows
            ]

            video_path = header["video_file_path"]
            video_basename = (
                os.path.basename(str(video_path)) if video_path else None
            )
            last_completed = header["last_completed_at"]
            if last_completed is None:
                last_completed_str: Optional[str] = None
            else:
                # SQLite typically returns str; SQLAlchemy may hand back a
                # datetime. Normalise to ISO string either way.
                try:
                    last_completed_str = last_completed.isoformat()
                except AttributeError:
                    last_completed_str = str(last_completed)

            return {
                "scene_id": int(header["scene_id"]),
                "video_file_basename": video_basename,
                "start_time": float(header["start_time"] or 0.0),
                "end_time": float(header["end_time"] or 0.0),
                "role": header["role"],
                "role_confidence": float(header["role_confidence"] or 0.0),
                "mood_refined": header["mood_refined"],
                "mood_confidence": float(header["mood_confidence"] or 0.0),
                "style_bucket_id": (
                    int(header["style_bucket_id"])
                    if header["style_bucket_id"] is not None
                    else None
                ),
                "style_bucket_name": header["style_bucket_name"],
                "style_distance": float(header["style_distance"] or 0.0),
                "neighbors": neighbors,
                "usage_count": int(header["usage_count"] or 0),
                "last_run_completed_at": last_completed_str,
            }
        finally:
            self._close_session(session, ownership)

    # ── T10.2c: library-level structure stats ──────────────────────────────
    def _structure_stats_uncached(self) -> dict[str, Any]:
        """Return a library-wide health snapshot for the Stats panel.

        Keys:
          total_scenes            int   — rows in `scenes`.
          enriched_scenes         int   — rows in `struct_clip_tags`.
          coverage_fraction       float — enriched / total, 0.0 if total==0.
          role_counts             list[tuple[str, int]] — sorted count DESC,
                                    then label ASC for determinism.
          mood_counts             list[tuple[str, int]] — same ordering rule.
          active_style_buckets    int   — buckets with active=1.
          missing_moods           list[str] — expected mood labels (from
                                    ``config/mood_anchors_v1.yaml``) that
                                    have zero scenes in `struct_clip_tags`.
                                    Sorted alphabetically.

        All reads share a single session. No N+1.
        """
        session, ownership = self._open_session()
        try:
            total_scenes = int(
                session.execute(text("SELECT COUNT(*) FROM scenes")).scalar()
                or 0
            )
            enriched_scenes = int(
                session.execute(
                    text("SELECT COUNT(*) FROM struct_clip_tags")
                ).scalar()
                or 0
            )
            coverage_fraction = (
                enriched_scenes / total_scenes if total_scenes > 0 else 0.0
            )

            role_rows = session.execute(
                text(
                    "SELECT role, COUNT(*) AS n FROM struct_clip_tags "
                    "WHERE role IS NOT NULL "
                    "GROUP BY role "
                    "ORDER BY n DESC, role ASC"
                )
            ).all()
            role_counts: list[tuple[str, int]] = [
                (str(r[0]), int(r[1])) for r in role_rows
            ]

            mood_rows = session.execute(
                text(
                    "SELECT mood_refined, COUNT(*) AS n FROM struct_clip_tags "
                    "WHERE mood_refined IS NOT NULL "
                    "GROUP BY mood_refined "
                    "ORDER BY n DESC, mood_refined ASC"
                )
            ).all()
            mood_counts: list[tuple[str, int]] = [
                (str(r[0]), int(r[1])) for r in mood_rows
            ]

            active_style_buckets = int(
                session.execute(
                    text(
                        "SELECT COUNT(*) FROM struct_style_bucket "
                        "WHERE active = 1"
                    )
                ).scalar()
                or 0
            )

            used_moods = {label for label, _ in mood_counts}
            expected = _load_expected_moods()
            missing_moods: list[str] = sorted(
                label for label in expected if label not in used_moods
            )

            return {
                "total_scenes": total_scenes,
                "enriched_scenes": enriched_scenes,
                "coverage_fraction": float(coverage_fraction),
                "role_counts": role_counts,
                "mood_counts": mood_counts,
                "active_style_buckets": active_style_buckets,
                "missing_moods": missing_moods,
            }
        finally:
            self._close_session(session, ownership)

    # ── T10.2d: graph snapshot (nodes + edges) ─────────────────────────────
    def _graph_nodes_and_edges_uncached(self) -> dict[str, Any]:
        """Return a snapshot for the Graph view.

        Keys:
          nodes: list[dict[str, Any]]  — each has {scene_id, role, mood_refined,
                                         style_bucket_id, style_bucket_name}.
          edges: list[dict[str, Any]]  — each has {a, b, similarity}. `a` / `b` are
                               scene_ids canonicalised to (a < b) so that
                               reciprocal edges (a=5,b=7) and (a=7,b=5)
                               collapse into a single record.
          scene_count: int   — number of enriched scenes (rows in
                               struct_clip_tags).

        Only enriched scenes are returned. Edges are included only when BOTH
        endpoints are enriched (inner join onto struct_clip_tags at the
        aggregation layer). Sorted: nodes by scene_id ASC; edges by (a,b) ASC.

        Single session, single transaction — no N+1.
        """
        session, ownership = self._open_session()
        try:
            node_rows = (
                session.execute(
                    text(
                        "SELECT "
                        "  t.scene_id        AS scene_id, "
                        "  t.role            AS role, "
                        "  t.mood_refined    AS mood_refined, "
                        "  t.style_bucket_id AS style_bucket_id, "
                        "  b.name            AS style_bucket_name "
                        "FROM struct_clip_tags t "
                        "LEFT JOIN struct_style_bucket b "
                        "  ON b.id = t.style_bucket_id "
                        "ORDER BY t.scene_id ASC"
                    )
                )
                .mappings()
                .all()
            )
            nodes = [
                {
                    "scene_id": int(r["scene_id"]),
                    "role": r["role"],
                    "mood_refined": r["mood_refined"],
                    "style_bucket_id": (
                        int(r["style_bucket_id"])
                        if r["style_bucket_id"] is not None
                        else None
                    ),
                    "style_bucket_name": r["style_bucket_name"],
                }
                for r in node_rows
            ]
            scene_count = len(nodes)

            # Deduplicated edges: canonical orientation (a,b)=(min,max). We
            # aggregate MAX(cosine_similarity) across reciprocal rows so the
            # caller gets the best known weight; semantically both directions
            # carry the same similarity but we don't rely on that equality.
            # The inner join onto struct_clip_tags (aliased as ta/tb) drops
            # edges with any non-enriched endpoint.
            edge_sql = text(
                "SELECT "
                "  MIN(e.scene_id_a, e.scene_id_b) AS a, "
                "  MAX(e.scene_id_a, e.scene_id_b) AS b, "
                "  MAX(e.cosine_similarity)        AS similarity "
                "FROM struct_compat_edge e "
                "INNER JOIN struct_clip_tags ta ON ta.scene_id = e.scene_id_a "
                "INNER JOIN struct_clip_tags tb ON tb.scene_id = e.scene_id_b "
                "GROUP BY MIN(e.scene_id_a, e.scene_id_b), "
                "         MAX(e.scene_id_a, e.scene_id_b) "
                "ORDER BY a ASC, b ASC"
            )
            edge_rows = session.execute(edge_sql).mappings().all()
            edges = [
                {
                    "a": int(r["a"]),
                    "b": int(r["b"]),
                    "similarity": float(r["similarity"] or 0.0),
                }
                for r in edge_rows
            ]

            return {
                "nodes": nodes,
                "edges": edges,
                "scene_count": scene_count,
            }
        finally:
            self._close_session(session, ownership)

    # ── T11.1: Memory tab reads ───────────────────────────────────────────
    def _list_pacing_runs_uncached(self) -> list[dict[str, Any]]:
        """Return pacing runs newest-first with a LEFT-JOIN on audio_tracks.

        Each dict has keys: id, started_at, completed_at, is_dj_mix,
        total_duration_sec, total_cuts, agent_version, weights_profile,
        user_rating, user_notes, audio_track_id, audio_track_filename.
        ``audio_track_filename`` is the raw ``audio_tracks.file_path`` (may be
        ``None`` if the run references a deleted / missing track).
        """
        session, ownership = self._open_session()
        try:
            rows = (
                session.execute(
                    text(
                        "SELECT "
                        "  r.id                  AS id, "
                        "  r.audio_track_id      AS audio_track_id, "
                        "  r.started_at          AS started_at, "
                        "  r.completed_at        AS completed_at, "
                        "  r.is_dj_mix           AS is_dj_mix, "
                        "  r.total_duration_sec  AS total_duration_sec, "
                        "  r.total_cuts          AS total_cuts, "
                        "  r.agent_version       AS agent_version, "
                        "  r.weights_profile     AS weights_profile, "
                        "  r.user_rating         AS user_rating, "
                        "  r.user_notes          AS user_notes, "
                        "  a.file_path           AS audio_track_filename "
                        "FROM mem_pacing_run r "
                        "LEFT JOIN audio_tracks a ON a.id = r.audio_track_id "
                        "ORDER BY r.started_at DESC, r.id DESC"
                    )
                )
                .mappings()
                .all()
            )
            return [
                {
                    "id": int(r["id"]),
                    "audio_track_id": (
                        int(r["audio_track_id"])
                        if r["audio_track_id"] is not None
                        else None
                    ),
                    "started_at": r["started_at"],
                    "completed_at": r["completed_at"],
                    "is_dj_mix": bool(r["is_dj_mix"]),
                    "total_duration_sec": float(r["total_duration_sec"] or 0.0),
                    "total_cuts": int(r["total_cuts"] or 0),
                    "agent_version": r["agent_version"],
                    "weights_profile": r["weights_profile"],
                    "user_rating": (
                        int(r["user_rating"])
                        if r["user_rating"] is not None
                        else None
                    ),
                    "user_notes": r["user_notes"],
                    "audio_track_filename": r["audio_track_filename"],
                }
                for r in rows
            ]
        finally:
            self._close_session(session, ownership)

    def list_learned_patterns(
        self,
        pattern_type: Optional[str] = None,
        min_confidence: float = 0.0,
    ) -> list[dict[str, Any]]:
        """Return learned patterns sorted by confidence DESC then last_updated DESC.

        Filters:
          - ``pattern_type``: exact match (None → all types).
          - ``min_confidence``: ``confidence >= threshold`` (0.0 → no filter).

        Each dict has keys: id, pattern_type, context_fingerprint (parsed JSON
        dict), target_ref (parsed JSON dict), stat_accept_count,
        stat_reject_count, stat_sample_size, confidence, last_updated.
        """
        return self._list_learned_patterns_cached(
            pattern_type, float(min_confidence)
        )

    def _list_learned_patterns_uncached(
        self,
        pattern_type: Optional[str],
        min_confidence: float,
    ) -> list[dict[str, Any]]:
        session, ownership = self._open_session()
        try:
            sql = (
                "SELECT "
                "  id, pattern_type, context_fingerprint, target_ref, "
                "  stat_accept_count, stat_reject_count, stat_sample_size, "
                "  confidence, last_updated "
                "FROM mem_learned_pattern "
                "WHERE 1 = 1"
            )
            params: dict[str, Any] = {}
            if pattern_type is not None:
                sql += " AND pattern_type = :ptype"
                params["ptype"] = pattern_type
            if min_confidence > 0.0:
                sql += " AND confidence >= :min_conf"
                params["min_conf"] = float(min_confidence)
            sql += " ORDER BY confidence DESC, last_updated DESC, id DESC"

            rows = session.execute(text(sql), params).mappings().all()
            return [
                {
                    "id": int(r["id"]),
                    "pattern_type": r["pattern_type"],
                    "context_fingerprint": _parse_json_field(
                        r["context_fingerprint"]
                    ),
                    "target_ref": _parse_json_field(r["target_ref"]),
                    "stat_accept_count": int(r["stat_accept_count"] or 0),
                    "stat_reject_count": int(r["stat_reject_count"] or 0),
                    "stat_sample_size": int(r["stat_sample_size"] or 0),
                    "confidence": float(r["confidence"] or 0.0),
                    "last_updated": r["last_updated"],
                }
                for r in rows
            ]
        finally:
            self._close_session(session, ownership)

    def _list_decisions_for_pattern_uncached(
        self, pattern_id: int, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Drill-down: decisions matching a learned pattern's fingerprint.

        Matching rules (see services/pacing/pattern_aggregator.make_context_fingerprint):
          - ``fingerprint.genre``  ↔ LOWER(mem_decision.at_genre)        (null-safe).
          - ``fingerprint.section_type`` ↔ LOWER(mem_decision.at_section_type).
          - ``fingerprint.bpm_bucket`` ↔ ROUND(mem_decision.at_bpm) cast to str.

        No enricher-version filter is applied: ``mem_learned_pattern`` has no
        ``at_enricher_version`` column, so we cannot correlate. All matching rows
        are returned regardless of their ``at_enricher_version``.

        Joins ``mem_pacing_run`` so we can sort primarily by run recency, then
        within a run by timestamp, limit 100.
        """
        pid = int(pattern_id)
        lim = max(1, int(limit))
        session, ownership = self._open_session()
        try:
            fp_row = session.execute(
                text(
                    "SELECT context_fingerprint FROM mem_learned_pattern "
                    "WHERE id = :pid"
                ),
                {"pid": pid},
            ).first()
            if fp_row is None:
                return []
            fingerprint = _parse_json_field(fp_row[0]) or {}
            genre = fingerprint.get("genre")
            section_type = fingerprint.get("section_type")
            bpm_bucket = fingerprint.get("bpm_bucket")

            sql_parts: list[str] = [
                "SELECT "
                "  d.id                    AS decision_id, "
                "  d.run_id                AS run_id, "
                "  d.sequence_idx          AS sequence_idx, "
                "  d.at_timestamp_sec      AS at_timestamp_sec, "
                "  d.at_genre              AS at_genre, "
                "  d.at_section_type       AS at_section_type, "
                "  d.at_bpm                AS at_bpm, "
                "  d.at_enricher_version   AS at_enricher_version, "
                "  d.scene_id              AS scene_id, "
                "  d.clip_role             AS clip_role, "
                "  d.clip_mood_refined     AS clip_mood_refined, "
                "  d.agent_score           AS agent_score, "
                "  d.user_verdict          AS user_verdict, "
                "  d.user_rating           AS user_rating, "
                "  r.started_at            AS run_started_at "
                "FROM mem_decision d "
                "JOIN mem_pacing_run r ON r.id = d.run_id "
                "WHERE 1 = 1"
            ]
            params: dict[str, Any] = {}
            if genre is None:
                sql_parts.append(" AND d.at_genre IS NULL")
            else:
                sql_parts.append(" AND LOWER(d.at_genre) = :genre")
                params["genre"] = str(genre).lower()
            if section_type is None:
                sql_parts.append(" AND d.at_section_type IS NULL")
            else:
                sql_parts.append(" AND LOWER(d.at_section_type) = :section_type")
                params["section_type"] = str(section_type).lower()
            if bpm_bucket is None:
                sql_parts.append(" AND d.at_bpm IS NULL")
            else:
                # ROUND() in SQLite returns a float; compare as int via CAST.
                sql_parts.append(
                    " AND CAST(ROUND(d.at_bpm) AS INTEGER) = :bpm_bucket"
                )
                try:
                    params["bpm_bucket"] = int(bpm_bucket)
                except (TypeError, ValueError):
                    # Fingerprint bucket wasn't a valid integer string — no
                    # decisions can match.
                    return []
            sql_parts.append(
                " ORDER BY r.started_at DESC, d.at_timestamp_sec ASC, d.id ASC"
            )
            sql_parts.append(" LIMIT :lim")
            params["lim"] = lim

            rows = (
                session.execute(text("".join(sql_parts)), params)
                .mappings()
                .all()
            )
            return [
                {
                    "decision_id": int(r["decision_id"]),
                    "run_id": int(r["run_id"]),
                    "sequence_idx": int(r["sequence_idx"] or 0),
                    "at_timestamp_sec": float(r["at_timestamp_sec"] or 0.0),
                    "at_genre": r["at_genre"],
                    "at_section_type": r["at_section_type"],
                    "at_bpm": (
                        float(r["at_bpm"])
                        if r["at_bpm"] is not None
                        else None
                    ),
                    "at_enricher_version": r["at_enricher_version"],
                    "scene_id": (
                        int(r["scene_id"])
                        if r["scene_id"] is not None
                        else None
                    ),
                    "clip_role": r["clip_role"],
                    "clip_mood_refined": r["clip_mood_refined"],
                    "agent_score": float(r["agent_score"] or 0.0),
                    "user_verdict": r["user_verdict"],
                    "user_rating": (
                        int(r["user_rating"])
                        if r["user_rating"] is not None
                        else None
                    ),
                    "run_started_at": r["run_started_at"],
                }
                for r in rows
            ]
        finally:
            self._close_session(session, ownership)

    def _list_distinct_pattern_types_uncached(self) -> list[str]:
        """Return DISTINCT pattern_type values from mem_learned_pattern, ASC."""
        session, ownership = self._open_session()
        try:
            rows = session.execute(
                text(
                    "SELECT DISTINCT pattern_type FROM mem_learned_pattern "
                    "WHERE pattern_type IS NOT NULL "
                    "ORDER BY pattern_type ASC"
                )
            ).all()
            return [r[0] for r in rows if r[0] is not None]
        finally:
            self._close_session(session, ownership)

    # ── T11.2: Audit tab reads ────────────────────────────────────────────
    def _list_runs_for_audit_selector_uncached(self) -> list[dict[str, Any]]:
        """Return COMPLETED pacing runs newest-first for the Audit tab dropdown.

        Same shape as ``list_pacing_runs`` but filtered to
        ``completed_at IS NOT NULL`` — partial/in-flight runs are not
        meaningfully auditable (no decisions to step through).

        A dedicated query (rather than Python-side filtering of the broader
        ``list_pacing_runs`` result) keeps the Audit dropdown cheap when the
        DB holds a long tail of completed mixes plus the occasional crash
        recovery row, and lets the two caches evolve independently.
        """
        session, ownership = self._open_session()
        try:
            rows = (
                session.execute(
                    text(
                        "SELECT "
                        "  r.id                  AS id, "
                        "  r.audio_track_id      AS audio_track_id, "
                        "  r.started_at          AS started_at, "
                        "  r.completed_at        AS completed_at, "
                        "  r.is_dj_mix           AS is_dj_mix, "
                        "  r.total_duration_sec  AS total_duration_sec, "
                        "  r.total_cuts          AS total_cuts, "
                        "  r.agent_version       AS agent_version, "
                        "  r.weights_profile     AS weights_profile, "
                        "  r.user_rating         AS user_rating, "
                        "  r.user_notes          AS user_notes, "
                        "  a.file_path           AS audio_track_filename "
                        "FROM mem_pacing_run r "
                        "LEFT JOIN audio_tracks a ON a.id = r.audio_track_id "
                        "WHERE r.completed_at IS NOT NULL "
                        "ORDER BY r.started_at DESC, r.id DESC"
                    )
                )
                .mappings()
                .all()
            )
            return [
                {
                    "id": int(r["id"]),
                    "audio_track_id": (
                        int(r["audio_track_id"])
                        if r["audio_track_id"] is not None
                        else None
                    ),
                    "started_at": r["started_at"],
                    "completed_at": r["completed_at"],
                    "is_dj_mix": bool(r["is_dj_mix"]),
                    "total_duration_sec": float(r["total_duration_sec"] or 0.0),
                    "total_cuts": int(r["total_cuts"] or 0),
                    "agent_version": r["agent_version"],
                    "weights_profile": r["weights_profile"],
                    "user_rating": (
                        int(r["user_rating"])
                        if r["user_rating"] is not None
                        else None
                    ),
                    "user_notes": r["user_notes"],
                    "audio_track_filename": r["audio_track_filename"],
                }
                for r in rows
            ]
        finally:
            self._close_session(session, ownership)

    def list_decisions_for_run(
        self,
        run_id: int,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """Return the cuts for a run, optionally filtered by verdict / fallback.

        ``filters`` may contain:
          - ``rejected_only`` (bool): keep rows where ``user_verdict = 'reject'``.
          - ``fallback_only`` (bool): keep rows whose ``agent_rationale`` JSON
            indicates a fallback branch. We consider any of
            ``stage1_softened``, ``stage2_forced``, ``forced_negative`` or
            an explicit ``fallback`` key being truthy as "fallback" — the
            real pipeline sets the first three (see services/pacing/pipeline.py),
            and we keep the literal ``fallback`` key for forward-compat with
            future rationale shapes.

        Multiple filters are AND-combined. Sorted by ``sequence_idx ASC``.

        Each returned dict has keys:
          ``id, sequence_idx, at_timestamp_sec, at_section_type,
           at_structure_segment_id, scene_id, scene_filename,
           clip_role, clip_mood_refined, clip_style_bucket_id,
           agent_score, user_verdict``.

        ``scene_filename`` is the basename of the underlying video-clip file,
        resolved via scenes → video_clips JOIN (``None`` if either row
        is missing — defensive against deleted clips that still have
        historical decisions pointing at their scene_id).
        """
        rid = int(run_id)
        flt = dict(filters or {})
        rejected_only = bool(flt.get("rejected_only", False))
        fallback_only = bool(flt.get("fallback_only", False))
        return self._list_decisions_for_run_cached(rid, rejected_only, fallback_only)

    def _list_decisions_for_run_uncached(
        self,
        run_id: int,
        rejected_only: bool,
        fallback_only: bool,
    ) -> list[dict[str, Any]]:
        session, ownership = self._open_session()
        try:
            sql = (
                "SELECT "
                "  d.id                     AS id, "
                "  d.sequence_idx           AS sequence_idx, "
                "  d.at_timestamp_sec       AS at_timestamp_sec, "
                "  d.at_section_type        AS at_section_type, "
                "  d.at_structure_segment_id AS at_structure_segment_id, "
                "  d.scene_id               AS scene_id, "
                "  d.clip_role              AS clip_role, "
                "  d.clip_mood_refined      AS clip_mood_refined, "
                "  d.clip_style_bucket_id   AS clip_style_bucket_id, "
                "  d.agent_score            AS agent_score, "
                "  d.user_verdict           AS user_verdict, "
                "  v.file_path              AS video_file_path "
                "FROM mem_decision d "
                "LEFT JOIN scenes s       ON s.id = d.scene_id "
                "LEFT JOIN video_clips v  ON v.id = s.video_clip_id "
                "WHERE d.run_id = :rid"
            )
            params: dict[str, Any] = {"rid": int(run_id)}
            if rejected_only:
                sql += " AND d.user_verdict = 'reject'"
            if fallback_only:
                # Any fallback-indicator flag truthy in the rationale counts.
                # json_extract is part of SQLite's JSON1 extension — available
                # in all current SQLite builds shipped with Python 3.10+.
                sql += (
                    " AND ( "
                    "   json_extract(d.agent_rationale, '$.fallback') = 1 "
                    " OR json_extract(d.agent_rationale, '$.stage1_softened') = 1 "
                    " OR json_extract(d.agent_rationale, '$.stage2_forced') = 1 "
                    " OR json_extract(d.agent_rationale, '$.forced_negative') = 1 "
                    " )"
                )
            sql += " ORDER BY d.sequence_idx ASC, d.id ASC"

            rows = session.execute(text(sql), params).mappings().all()
            out: list[dict[str, Any]] = []
            for r in rows:
                video_path = r["video_file_path"]
                scene_filename = (
                    os.path.basename(str(video_path)) if video_path else None
                )
                out.append(
                    {
                        "id": int(r["id"]),
                        "sequence_idx": int(r["sequence_idx"] or 0),
                        "at_timestamp_sec": float(r["at_timestamp_sec"] or 0.0),
                        "at_section_type": r["at_section_type"],
                        "at_structure_segment_id": (
                            int(r["at_structure_segment_id"])
                            if r["at_structure_segment_id"] is not None
                            else None
                        ),
                        "scene_id": (
                            int(r["scene_id"])
                            if r["scene_id"] is not None
                            else None
                        ),
                        "scene_filename": scene_filename,
                        "clip_role": r["clip_role"],
                        "clip_mood_refined": r["clip_mood_refined"],
                        "clip_style_bucket_id": (
                            int(r["clip_style_bucket_id"])
                            if r["clip_style_bucket_id"] is not None
                            else None
                        ),
                        "agent_score": float(r["agent_score"] or 0.0),
                        "user_verdict": r["user_verdict"],
                    }
                )
            return out
        finally:
            self._close_session(session, ownership)

    def _get_decision_detail_uncached(self, decision_id: int) -> Optional[dict[str, Any]]:
        """Return the parsed rationale + context for one decision, or None.

        Backs the Audit tab's right-hand details column: term-contributions,
        top-3 alternatives, budget-state.

        The rationale JSON shape matches services/pacing/pipeline.py's
        ``PacingPipeline.select_best`` return value:
            {
              chosen_clip_id, chosen_scene_id, chosen_score,
              contribs: {term: signed_contribution},
              stage1_softened, stage2_forced, forced_negative,
              stage_results: [StageResult, ...],
              at_section_type,
              persisted_decision_id (if recorded),
              ...
            }

        Fields mapped for the UI:
          - ``rationale_terms``  — the ``contribs`` dict (signed per-term values).
                                    Empty dict if missing.
          - ``alternatives``     — at most 3, derived from the ``stage_results``
                                    rows that have a ``soft_score`` set,
                                    excluding the chosen clip itself, sorted by
                                    ``soft_score`` DESC. The plan-brief's
                                    ``rationale.alternatives`` field does NOT
                                    exist in the real rationale — this is an
                                    adapter. Each entry: ``{scene_id (None for
                                    now — stage_results only carries clip_id),
                                    clip_id, score, role}``.
          - ``budget_state``     — forwarded from ``rationale.budget_state`` if
                                    the pipeline ever populates it; otherwise
                                    an empty dict. (Today pipeline.py does not
                                    emit budget_state — the UI shows "—" when
                                    absent.)
          - ``fallback``         — True if any of stage1_softened /
                                    stage2_forced / forced_negative / a literal
                                    ``fallback`` flag are truthy.
          - ``rejected``         — ``user_verdict == 'reject'``.
        """
        did = int(decision_id)
        session, ownership = self._open_session()
        try:
            row = (
                session.execute(
                    text(
                        "SELECT id, run_id, sequence_idx, at_timestamp_sec, "
                        "  scene_id, clip_role, agent_score, agent_rationale, "
                        "  user_verdict "
                        "FROM mem_decision WHERE id = :did"
                    ),
                    {"did": did},
                )
                .mappings()
                .first()
            )
            if row is None:
                return None

            rationale = _parse_json_field(row["agent_rationale"]) or {}
            if not isinstance(rationale, dict):
                rationale = {}

            terms_raw = rationale.get("contribs") or rationale.get("terms") or {}
            if isinstance(terms_raw, dict):
                rationale_terms = {str(k): float(v) for k, v in terms_raw.items()}
            else:
                rationale_terms = {}

            # Derive alternatives from stage_results when an explicit
            # ``alternatives`` key isn't already present (future-proof: future
            # rationale shapes may add one).
            alternatives: list[dict[str, Any]] = []
            raw_alts = rationale.get("alternatives")
            chosen_clip_id = rationale.get("chosen_clip_id")
            if isinstance(raw_alts, list) and raw_alts:
                for alt in raw_alts[:3]:
                    if not isinstance(alt, dict):
                        continue
                    alternatives.append(
                        {
                            "scene_id": alt.get("scene_id"),
                            "clip_id": alt.get("clip_id"),
                            "score": float(alt.get("score") or 0.0),
                            "role": alt.get("role"),
                        }
                    )
            else:
                stage_results = rationale.get("stage_results") or []
                if isinstance(stage_results, list):
                    scored = [
                        sr
                        for sr in stage_results
                        if isinstance(sr, dict)
                        and sr.get("soft_score") is not None
                        and sr.get("clip_id") != chosen_clip_id
                    ]
                    scored.sort(
                        key=lambda sr: float(sr.get("soft_score") or 0.0),
                        reverse=True,
                    )
                    for sr in scored[:3]:
                        alternatives.append(
                            {
                                "scene_id": None,  # not carried in stage_results
                                "clip_id": sr.get("clip_id"),
                                "score": float(sr.get("soft_score") or 0.0),
                                "role": None,
                            }
                        )

            budget_raw = rationale.get("budget_state")
            if isinstance(budget_raw, dict):
                budget_state = {str(k): v for k, v in budget_raw.items()}
            else:
                budget_state = {}

            fallback = bool(
                rationale.get("fallback")
                or rationale.get("stage1_softened")
                or rationale.get("stage2_forced")
                or rationale.get("forced_negative")
            )

            return {
                "id": int(row["id"]),
                "run_id": int(row["run_id"]),
                "sequence_idx": int(row["sequence_idx"] or 0),
                "at_timestamp_sec": float(row["at_timestamp_sec"] or 0.0),
                "scene_id": (
                    int(row["scene_id"])
                    if row["scene_id"] is not None
                    else None
                ),
                "clip_role": row["clip_role"],
                "agent_score": float(row["agent_score"] or 0.0),
                "rationale_terms": rationale_terms,
                "alternatives": alternatives,
                "budget_state": budget_state,
                "fallback": fallback,
                "rejected": row["user_verdict"] == "reject",
            }
        finally:
            self._close_session(session, ownership)

    def _list_structure_segments_for_run_uncached(
        self, run_id: int
    ) -> list[dict[str, Any]]:
        """Return song-structure segments for a DJ-mix run.

        Non-DJ-mix runs return ``[]`` (the segment-strip is hidden for them).
        The segments live on ``structure_segments`` keyed by
        ``audio_track_id``; we resolve the FK via ``mem_pacing_run``.

        Result dicts have keys ``id, start_sec, end_sec, label`` (the DB
        columns are called ``start_time`` / ``end_time`` — we alias here to
        match the UI-side naming the brief uses). Sorted by ``start_sec ASC``.
        """
        rid = int(run_id)
        session, ownership = self._open_session()
        try:
            run_row = (
                session.execute(
                    text(
                        "SELECT is_dj_mix, audio_track_id "
                        "FROM mem_pacing_run WHERE id = :rid"
                    ),
                    {"rid": rid},
                )
                .mappings()
                .first()
            )
            if run_row is None or not bool(run_row["is_dj_mix"]):
                return []
            audio_track_id = run_row["audio_track_id"]
            if audio_track_id is None:
                return []

            rows = (
                session.execute(
                    text(
                        "SELECT id, start_time, end_time, label "
                        "FROM structure_segments "
                        "WHERE audio_track_id = :aid "
                        "ORDER BY start_time ASC, id ASC"
                    ),
                    {"aid": int(audio_track_id)},
                )
                .mappings()
                .all()
            )
            return [
                {
                    "id": int(r["id"]),
                    "start_sec": float(r["start_time"] or 0.0),
                    "end_sec": float(r["end_time"] or 0.0),
                    "label": r["label"],
                }
                for r in rows
            ]
        finally:
            self._close_session(session, ownership)


    # ── T11.3: Steer tab reads ─────────────────────────────────────────────
    def _list_audio_tracks_uncached(self) -> list[dict[str, Any]]:
        """Return every row in ``audio_tracks`` newest-first.

        Result dict shape (keys stable across schema drift):
          ``id``             (int)
          ``file_path``      (str)
          ``file_basename``  (str) — computed Python-side via ``os.path.basename``
          ``duration_sec``   (float | None) — from the ``duration`` column
                              (real schema uses ``duration``; the dict aliases
                              it to ``duration_sec`` for UI-layer clarity).
                              ``None`` if the column is missing (bootstrap
                              schemas in tests), preserving the contract.
          ``bpm``            (float | None) — ``None`` if the column is missing.
          ``created_at``     (raw DB value — datetime or ISO string; the
                              Steer tab renders it via ``str()``).

        Implementation note: the production ``audio_tracks`` schema (see
        ``database/models.py``) has ``duration`` and ``bpm``; the
        tests-bootstrap schema in ``tests/ui/test_structure_tab.py`` does not.
        We introspect ``PRAGMA table_info`` once per call to decide which
        optional columns to include in the SELECT, so the method works in both
        environments without forcing every test to materialise the full
        schema.
        """
        session, ownership = self._open_session()
        try:
            # Column set is schema-dependent; PRAGMA is cheap and bypasses the
            # ORM so we don't need to mirror the AudioTrack model here.
            cols_rows = session.execute(
                text("PRAGMA table_info(audio_tracks)")
            ).all()
            present = {row[1] for row in cols_rows}
            select_duration = "a.duration AS duration_sec" if "duration" in present else "NULL AS duration_sec"
            select_bpm = "a.bpm AS bpm" if "bpm" in present else "NULL AS bpm"
            # created_at is only on the test-harness schema (added by
            # `_add_audio_track_bpm_and_duration` helper); production
            # `audio_tracks` has no such column. Introspect and fall back to
            # id-ordering (autoincrement → newest-first) so the query works
            # on both schemas.
            has_created_at = "created_at" in present
            select_created = "a.created_at AS created_at" if has_created_at else "NULL AS created_at"
            order_by = (
                "a.created_at DESC, a.id DESC" if has_created_at else "a.id DESC"
            )
            sql = (
                "SELECT "
                "  a.id                 AS id, "
                "  a.file_path          AS file_path, "
                f" {select_duration}, "
                f" {select_bpm}, "
                f" {select_created} "
                "FROM audio_tracks a "
                f"ORDER BY {order_by}"
            )
            rows = session.execute(text(sql)).mappings().all()
            out: list[dict[str, Any]] = []
            for r in rows:
                file_path = r["file_path"]
                basename = (
                    os.path.basename(str(file_path)) if file_path else ""
                )
                duration = r["duration_sec"]
                bpm_raw = r["bpm"]
                out.append(
                    {
                        "id": int(r["id"]),
                        "file_path": file_path,
                        "file_basename": basename,
                        "duration_sec": (
                            float(duration) if duration is not None else None
                        ),
                        "bpm": float(bpm_raw) if bpm_raw is not None else None,
                        "created_at": r["created_at"],
                    }
                )
            return out
        finally:
            self._close_session(session, ownership)

    def _list_weights_profiles_uncached(self) -> list[dict[str, Any]]:
        """Return ``[{"name", "path"}, ...]`` for every ``*.yaml`` under
        ``config/pacing_weights/``, sorted by name ASC.

        The list is read from the module-level ``_PACING_WEIGHTS_DIR`` so
        tests can monkeypatch the path to a nonexistent location and exercise
        the missing-dir fallback. A missing directory or filesystem error is
        logged at WARNING and the method returns ``[]`` — the Steer tab treats
        an empty list as "no profiles to pick" and keeps the dropdown
        disabled.
        """
        profiles_dir = _PACING_WEIGHTS_DIR
        try:
            if not profiles_dir.exists() or not profiles_dir.is_dir():
                logger.warning(
                    "pacing_weights dir missing at %s — returning empty "
                    "profile list",
                    profiles_dir,
                )
                return []
            entries: list[dict[str, Any]] = []
            for yaml_path in profiles_dir.glob("*.yaml"):
                if not yaml_path.is_file():
                    continue
                entries.append(
                    {
                        "name": yaml_path.stem,
                        "path": str(yaml_path.resolve()),
                    }
                )
            entries.sort(key=lambda e: e["name"])
            return entries
        except OSError as exc:  # pragma: no cover — defensive
            logger.warning(
                "Failed to enumerate pacing_weights dir %s: %s",
                profiles_dir,
                exc,
            )
            return []


    # ── P12: Story-Map dialog reads ────────────────────────────────────────
    def _story_map_data_uncached(self, run_id: int) -> Optional[dict[str, Any]]:
        """Return the full bundle of data the Story-Map dialog renders.

        Returns ``None`` if the run does not exist.

        Result dict shape (see plan P12 for the contract):
            {
              run: {id, audio_track_id, total_duration_sec, is_dj_mix,
                    started_at, completed_at},
              audio_track: {id, file_path, file_basename} | None,
              decisions: [
                {decision_id, sequence_idx, at_timestamp_sec, at_section_type,
                 at_mood_audio, at_harmonic_tension, scene_id, clip_role,
                 clip_mood_refined, video_file_path}
                ...  # ordered by sequence_idx ASC
              ],
              structure_segments: [
                {id, start_sec, end_sec, label}
                ...  # empty if not is_dj_mix
              ],
              tension_curve: [
                {time_sec, value}
                ...  # one per decision, derived from at_harmonic_tension
              ],
              mood_curve: [
                {time_sec, mood}
                ...  # one per decision, derived from at_mood_audio
              ],
              waveform_energy: [
                {time_sec, energy}
                ...  # sampled from audio_tracks.energy_curve, empty if absent
              ],
            }

        Sampling semantics:
          * tension_curve and mood_curve are point-snapshots from
            mem_decision (one per cut). The dialog renders them as a step or
            linear interpolation. We do not reconstruct a per-frame curve from
            raw audio — only per-decision snapshots are persisted.
          * waveform_energy is lifted from audio_tracks.energy_curve (a JSON
            list of energies, evenly-spaced across total_duration_sec). If the
            column is missing, NULL, or unparseable, returns ``[]`` and the
            dialog hides the waveform panel.

        Single session, single transaction; no N+1.
        """
        rid = int(run_id)
        session, ownership = self._open_session()
        try:
            run_row = (
                session.execute(
                    text(
                        "SELECT id, audio_track_id, total_duration_sec, "
                        "  is_dj_mix, started_at, completed_at "
                        "FROM mem_pacing_run WHERE id = :rid"
                    ),
                    {"rid": rid},
                )
                .mappings()
                .first()
            )
            if run_row is None:
                return None

            run_dict = {
                "id": int(run_row["id"]),
                "audio_track_id": (
                    int(run_row["audio_track_id"])
                    if run_row["audio_track_id"] is not None
                    else None
                ),
                "total_duration_sec": float(run_row["total_duration_sec"] or 0.0),
                "is_dj_mix": bool(run_row["is_dj_mix"]),
                "started_at": run_row["started_at"],
                "completed_at": run_row["completed_at"],
            }

            audio_track: Optional[dict[str, Any]] = None
            audio_track_id = run_row["audio_track_id"]
            energy_curve_raw: Any = None
            if audio_track_id is not None:
                # PRAGMA-introspect for energy_curve so the older test-bootstrap
                # schemas (which don't carry it) don't blow up the SELECT.
                cols_rows = session.execute(
                    text("PRAGMA table_info(audio_tracks)")
                ).all()
                present = {row[1] for row in cols_rows}
                select_energy = (
                    "a.energy_curve AS energy_curve"
                    if "energy_curve" in present
                    else "NULL AS energy_curve"
                )
                track_row = (
                    session.execute(
                        text(
                            "SELECT a.id AS id, a.file_path AS file_path, "
                            f" {select_energy} "
                            "FROM audio_tracks a WHERE a.id = :aid"
                        ),
                        {"aid": int(audio_track_id)},
                    )
                    .mappings()
                    .first()
                )
                if track_row is not None:
                    file_path = track_row["file_path"]
                    audio_track = {
                        "id": int(track_row["id"]),
                        "file_path": file_path,
                        "file_basename": (
                            os.path.basename(str(file_path))
                            if file_path
                            else ""
                        ),
                    }
                    energy_curve_raw = track_row["energy_curve"]

            decisions_rows = (
                session.execute(
                    text(
                        "SELECT "
                        "  d.id                  AS decision_id, "
                        "  d.sequence_idx        AS sequence_idx, "
                        "  d.at_timestamp_sec    AS at_timestamp_sec, "
                        "  d.at_section_type     AS at_section_type, "
                        "  d.at_mood_audio       AS at_mood_audio, "
                        "  d.at_harmonic_tension AS at_harmonic_tension, "
                        "  d.scene_id            AS scene_id, "
                        "  d.clip_role           AS clip_role, "
                        "  d.clip_mood_refined   AS clip_mood_refined, "
                        "  v.file_path           AS video_file_path "
                        "FROM mem_decision d "
                        "LEFT JOIN scenes s      ON s.id = d.scene_id "
                        "LEFT JOIN video_clips v ON v.id = s.video_clip_id "
                        "WHERE d.run_id = :rid "
                        "ORDER BY d.sequence_idx ASC, d.id ASC"
                    ),
                    {"rid": rid},
                )
                .mappings()
                .all()
            )
            decisions: list[dict[str, Any]] = []
            tension_curve: list[dict[str, Any]] = []
            mood_curve: list[dict[str, Any]] = []
            for r in decisions_rows:
                ts = float(r["at_timestamp_sec"] or 0.0)
                tension_raw = r["at_harmonic_tension"]
                mood_raw = r["at_mood_audio"]
                decisions.append(
                    {
                        "decision_id": int(r["decision_id"]),
                        "sequence_idx": int(r["sequence_idx"] or 0),
                        "at_timestamp_sec": ts,
                        "at_section_type": r["at_section_type"],
                        "at_mood_audio": mood_raw,
                        "at_harmonic_tension": (
                            float(tension_raw)
                            if tension_raw is not None
                            else None
                        ),
                        "scene_id": (
                            int(r["scene_id"])
                            if r["scene_id"] is not None
                            else None
                        ),
                        "clip_role": r["clip_role"],
                        "clip_mood_refined": r["clip_mood_refined"],
                        "video_file_path": r["video_file_path"],
                    }
                )
                if tension_raw is not None:
                    try:
                        tension_curve.append(
                            {"time_sec": ts, "value": float(tension_raw)}
                        )
                    except (TypeError, ValueError):
                        pass
                if mood_raw is not None:
                    mood_curve.append({"time_sec": ts, "mood": mood_raw})

            structure_segments: list[dict[str, Any]] = []
            if run_dict["is_dj_mix"] and audio_track_id is not None:
                # Probe the table; some test-bootstrap envs don't create it.
                try:
                    seg_rows = (
                        session.execute(
                            text(
                                "SELECT id, start_time, end_time, label "
                                "FROM structure_segments "
                                "WHERE audio_track_id = :aid "
                                "ORDER BY start_time ASC, id ASC"
                            ),
                            {"aid": int(audio_track_id)},
                        )
                        .mappings()
                        .all()
                    )
                    structure_segments = [
                        {
                            "id": int(s["id"]),
                            "start_sec": float(s["start_time"] or 0.0),
                            "end_sec": float(s["end_time"] or 0.0),
                            "label": s["label"],
                        }
                        for s in seg_rows
                    ]
                except Exception as exc:  # pragma: no cover — defensive
                    logger.warning(
                        "story_map_data: structure_segments read failed for "
                        "audio_track_id=%s: %s",
                        audio_track_id,
                        exc,
                    )

            waveform_energy: list[dict[str, Any]] = []
            energy_values = _parse_json_field(energy_curve_raw)
            if isinstance(energy_values, list) and energy_values:
                duration = run_dict["total_duration_sec"]
                if duration <= 0:
                    duration = float(len(energy_values))
                n = len(energy_values)
                if n == 1:
                    # Single-point curve: anchor at t=0.
                    try:
                        waveform_energy = [
                            {"time_sec": 0.0, "energy": float(energy_values[0])}
                        ]
                    except (TypeError, ValueError):
                        waveform_energy = []
                else:
                    step = duration / (n - 1)
                    for i, ev in enumerate(energy_values):
                        try:
                            waveform_energy.append(
                                {
                                    "time_sec": float(i * step),
                                    "energy": float(ev),
                                }
                            )
                        except (TypeError, ValueError):
                            # Skip non-numeric entries defensively.
                            continue

            return {
                "run": run_dict,
                "audio_track": audio_track,
                "decisions": decisions,
                "structure_segments": structure_segments,
                "tension_curve": tension_curve,
                "mood_curve": mood_curve,
                "waveform_energy": waveform_energy,
            }
        finally:
            self._close_session(session, ownership)

    def _list_runs_with_story_map_data_uncached(self) -> list[dict[str, Any]]:
        """Return runs that have at least one decision (newest-first).

        Each dict has keys: ``id, started_at, completed_at, is_dj_mix,
        total_cuts, audio_track_filename`` — exactly the columns the Story-Map
        trigger menus need to render their items. ``audio_track_filename`` is
        the basename of the joined ``audio_tracks.file_path`` (None if the
        run has no track or the file path is empty).
        """
        session, ownership = self._open_session()
        try:
            rows = (
                session.execute(
                    text(
                        "SELECT "
                        "  r.id                  AS id, "
                        "  r.started_at          AS started_at, "
                        "  r.completed_at        AS completed_at, "
                        "  r.is_dj_mix           AS is_dj_mix, "
                        "  r.total_cuts          AS total_cuts, "
                        "  a.file_path           AS audio_track_filepath "
                        "FROM mem_pacing_run r "
                        "LEFT JOIN audio_tracks a ON a.id = r.audio_track_id "
                        "WHERE EXISTS ("
                        "  SELECT 1 FROM mem_decision d WHERE d.run_id = r.id"
                        ") "
                        "ORDER BY r.started_at DESC, r.id DESC"
                    )
                )
                .mappings()
                .all()
            )
            out: list[dict[str, Any]] = []
            for r in rows:
                fp = r["audio_track_filepath"]
                basename = os.path.basename(str(fp)) if fp else None
                out.append(
                    {
                        "id": int(r["id"]),
                        "started_at": r["started_at"],
                        "completed_at": r["completed_at"],
                        "is_dj_mix": bool(r["is_dj_mix"]),
                        "total_cuts": int(r["total_cuts"] or 0),
                        "audio_track_filename": basename,
                    }
                )
            return out
        finally:
            self._close_session(session, ownership)


def _parse_json_field(raw: Any) -> Any:
    """Coerce a JSON column into a Python value.

    SQLAlchemy's ``JSON`` type returns dicts/lists directly on most drivers,
    but SQLite-backed setups sometimes hand back the raw text (especially
    when the ``text()`` query bypasses the type system). Normalise to a
    parsed dict / list; fall back to ``None`` on garbage input.
    """
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("Could not parse JSON field: %r", raw)
        return None
