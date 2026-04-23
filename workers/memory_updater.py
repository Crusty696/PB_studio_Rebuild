"""MemoryUpdaterWorker — batches PatternAggregator runs.

Triggers:
  - notify_feedback() is called on each user-feedback event; the worker
    increments an internal counter and runs aggregation once the counter
    hits N=20.
  - notify_run_end() runs aggregation once unconditionally.

Running aggregation N times is cheap (single JOIN query + Python group-by)
but we still batch so the UI thread isn't stalled on every keystroke.

Qt integration:
  - Inherits from QObject with `started`, `finished`, `error` signals — mirrors
    workers/video.py conventions.
  - Synchronous `run()` entry point is provided for tests and for the
    enrichment worker's post-run hook.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

from services.pacing.pattern_aggregator import PatternAggregator

logger = logging.getLogger(__name__)


class MemoryUpdaterWorker(QObject):
    """Batches PatternAggregator runs: flush after BATCH_SIZE feedback events
    or explicitly on run-end."""

    BATCH_SIZE: int = 20  # flush after this many feedback events

    started = Signal()
    finished = Signal(int)  # emits number of patterns upserted
    error = Signal(str)

    def __init__(
        self,
        session_factory: Callable[[], Any],
        batch_size: int | None = None,
    ) -> None:
        super().__init__()
        self._session_factory = session_factory
        self._batch_size: int = (
            batch_size if batch_size is not None else self.BATCH_SIZE
        )
        self._pending: int = 0
        self._aggregator = PatternAggregator(session_factory=session_factory)

    # ── Public API ───────────────────────────────────────────────────────────

    def notify_feedback(self) -> bool:
        """Called on each feedback event.

        Increments the internal counter and flushes if the batch size is
        reached.  Returns True if a batch was flushed, False otherwise.
        """
        self._pending += 1
        if self._pending >= self._batch_size:
            self.run()
            return True
        return False

    def notify_run_end(self) -> int:
        """Called when a pacing run ends.

        Always flushes regardless of the pending counter.
        Returns the number of patterns upserted (0 if nothing was pending).
        """
        return self.run()

    def run(self) -> int:
        """Synchronous aggregation.

        Runs PatternAggregator, resets the pending counter, and emits Qt
        signals so the caller can wire this into a QThread if desired.
        Returns the number of patterns upserted.
        """
        self.started.emit()
        n = 0
        try:
            n = self._aggregator.run()
            self._pending = 0
            self.finished.emit(n)
        except Exception as exc:  # broad catch — top-level worker safety net
            logger.error(
                "MemoryUpdaterWorker: aggregation failed: %s\n%s",
                exc,
                traceback.format_exc(),
            )
            self._pending = 0
            self.error.emit(str(exc))
        return n

    # ── Diagnostics ──────────────────────────────────────────────────────────

    @property
    def pending_events(self) -> int:
        """Internal counter — for diagnostics and tests."""
        return self._pending
