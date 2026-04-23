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
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)


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
        # Names of attributes wrapped in lru_cache — invalidate() iterates this
        # list so new cached endpoints only need to be added in one place.
        self._cached_attrs: tuple[str, ...] = (
            "list_scene_count",
            "list_active_style_buckets",
            "list_distinct_roles",
            "list_distinct_moods",
            "_list_clips_with_tags_cached",
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
