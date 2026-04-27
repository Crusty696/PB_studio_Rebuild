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
import sys
import threading
import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal

from services.pacing.pattern_aggregator import PatternAggregator

logger = logging.getLogger(__name__)


def _warn_if_on_gui_thread() -> None:
    """B-105 / BUG-2-b: warn when ``notify_feedback`` triggers a
    synchronous flush on the Qt GUI thread. The aggregation can take
    multiple seconds; on the GUI thread that is a freeze."""
    qtcore = sys.modules.get("PySide6.QtCore")
    if qtcore is None:
        return
    QApplication = getattr(
        sys.modules.get("PySide6.QtWidgets"), "QApplication", None
    )
    if QApplication is None:
        return
    app = QApplication.instance()
    if app is None:
        return
    QThread = getattr(qtcore, "QThread", None)
    if QThread is None:
        return
    if QThread.currentThread() is app.thread():
        logger.warning(
            "MemoryUpdaterWorker.run() is being triggered on the Qt GUI "
            "thread. PatternAggregator.run() can take multiple seconds; "
            "wire MemoryUpdaterWorker into a QThread so the flush does "
            "not freeze the UI."
        )


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
        # B-105 / BUG-2-b: ``_pending`` is mutated from any thread that
        # raises a feedback event. ``self._pending += 1`` is not atomic
        # in CPython, and the threshold check + flush is a TOCTOU race.
        self._pending_lock: threading.Lock = threading.Lock()
        self._gui_thread_warning_logged: bool = False
        self._aggregator = PatternAggregator(session_factory=session_factory)

    # ── Public API ───────────────────────────────────────────────────────────

    def notify_feedback(self) -> bool:
        """Called on each feedback event.

        Increments the internal counter and flushes if the batch size is
        reached.  Returns True if a batch was flushed, False otherwise.

        B-105: increment + threshold check are guarded by
        ``_pending_lock`` so concurrent calls cannot both cross the
        threshold. If the threshold is crossed we warn (once per worker)
        when running on the Qt GUI thread — the flush is a multi-second
        SQL operation and must not block the UI.
        """
        with self._pending_lock:
            self._pending += 1
            should_flush = self._pending >= self._batch_size
        if should_flush:
            if not self._gui_thread_warning_logged:
                _warn_if_on_gui_thread()
                self._gui_thread_warning_logged = True
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
            with self._pending_lock:
                self._pending = 0
            self.finished.emit(n)
        except Exception as exc:  # broad catch — top-level worker safety net
            logger.error(
                "MemoryUpdaterWorker: aggregation failed: %s\n%s",
                exc,
                traceback.format_exc(),
            )
            with self._pending_lock:
                self._pending = 0
            self.error.emit(str(exc))
        return n

    # ── Diagnostics ──────────────────────────────────────────────────────────

    @property
    def pending_events(self) -> int:
        """Internal counter — for diagnostics and tests."""
        return self._pending


# ---------------------------------------------------------------------------
# B-197 F-3: lazy module-level singleton
# ---------------------------------------------------------------------------

_default_memory_updater: MemoryUpdaterWorker | None = None
_singleton_lock = threading.Lock()


def get_memory_updater() -> MemoryUpdaterWorker:
    """B-197 F-3: Modulweiter Singleton-MemoryUpdaterWorker, an die echte
    DB gebunden via ``database.nullpool_session``.

    Erst-Aufruf erzeugt die Instanz. Folge-Aufrufe geben dieselbe.
    Tests duerfen ``MemoryUpdaterWorker(...)`` weiter direkt nutzen
    und diesen Singleton ignorieren.

    Wird vom ``ui/timeline.py``-Pfad gerufen, sobald
    ``FeedbackService.record_*`` erfolgreich war — damit die
    Pattern-Aggregation in ``mem_learned_pattern`` automatisch
    nachgezogen wird.
    """
    global _default_memory_updater
    if _default_memory_updater is None:
        with _singleton_lock:
            if _default_memory_updater is None:
                from database import nullpool_session  # type: ignore[attr-defined]

                _default_memory_updater = MemoryUpdaterWorker(
                    session_factory=nullpool_session,
                )
                logger.info(
                    "MemoryUpdaterWorker: Singleton erstellt "
                    "(batch_size=%d).", _default_memory_updater._batch_size,
                )
    return _default_memory_updater
