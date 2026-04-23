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

T10.1 scope: only list_scene_count() is implemented. Later tasks (T10.2 +)
will extend this file with structure/memory/audit read-views.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable

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

    def _list_scene_count_uncached(self) -> int:
        """Return the total number of rows in the `scenes` table."""
        session = self._session_factory()
        ownership = False
        try:
            if hasattr(session, "__enter__") and not hasattr(session, "execute"):
                session = session.__enter__()
                ownership = True
            result = session.execute(text("SELECT COUNT(*) FROM scenes"))
            return int(result.scalar() or 0)
        finally:
            try:
                if ownership:
                    session.__exit__(None, None, None)
                else:
                    close = getattr(session, "close", None)
                    if callable(close):
                        close()
            except Exception:  # best-effort cleanup
                pass
