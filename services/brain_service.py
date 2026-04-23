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
"""

from __future__ import annotations

import functools
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
        self._list_clips_with_tags_cached = functools.lru_cache(maxsize=32)(
            self._list_clips_with_tags_uncached
        )
        # T10.2b: clip detail (Inspector panel). Keyed by scene_id (int).
        self.get_clip_detail = functools.lru_cache(maxsize=32)(
            self._get_clip_detail_uncached
        )
        # T10.2c: library-level stats (Stats panel). No arguments.
        self.structure_stats = functools.lru_cache(maxsize=1)(
            self._structure_stats_uncached
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
    def _list_active_style_buckets_uncached(self) -> list[dict]:
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
    ) -> list[dict]:
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
    ) -> list[dict]:
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
    def _get_clip_detail_uncached(self, scene_id: int) -> Optional[dict]:
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
            neighbors               (list[dict]) — up to 5, ordered by
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
    def _structure_stats_uncached(self) -> dict:
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
