"""MemoryUpdaterWorker — batches PatternAggregator runs.

Triggers:
  - notify_feedback() is called on each user-feedback event; the worker
    increments an internal counter and schedules aggregation once the counter
    hits N=20 — ODER nach FLUSH_DELAY_SEC Sekunden Ruhe (Debounce, B-737).
  - notify_run_end() runs aggregation once unconditionally.
  - shutdown() flusht Restereignisse beim Schliessen; fuer den modulweiten
    Singleton haengt das zusaetzlich an ``atexit``.

Running aggregation N times is cheap (single JOIN query + Python group-by)
but we still batch so the UI thread isn't stalled on every keystroke.

B-737 — warum der Debounce noetig war
-------------------------------------
Vorher gab es genau zwei Ausloeser: der 20er-Zaehler und ``notify_run_end()``.
``notify_run_end()`` hatte im gesamten Produktivcode KEINEN Aufrufer (nur
Tests). Wer also weniger als 20 Mal Feedback gab — der Normalfall — loeste
die Aggregation nie aus; ``mem_learned_pattern`` blieb leer, obwohl die
Ereignisse selbst laengst in ``mem_decision`` / ``mem_user_feedback_event``
standen. Verloren gingen also nicht die Ereignisse, sondern der Ausloeser.
Der Debounce-Timer schliesst genau diese Luecke: auch ein EINZELNES Ereignis
fuehrt nach kurzer Ruhephase zu einem Aggregationslauf.

Qt integration:
  - Inherits from QObject with `started`, `finished`, `error` signals — mirrors
    workers/video.py conventions.
  - Synchronous `run()` entry point is provided for tests and for the
    enrichment worker's post-run hook. Feedback-triggered flushes run on a
    background thread.
"""

from __future__ import annotations

import atexit
import logging
import sys
import threading
import time
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
    # B-737: Debounce. Nach so vielen Sekunden ohne weiteres Ereignis wird
    # auch unterhalb von BATCH_SIZE aggregiert. 0 (oder negativ) schaltet den
    # Timer ab und stellt das alte Reine-Schwellen-Verhalten wieder her.
    FLUSH_DELAY_SEC: float = 5.0

    started = Signal()
    finished = Signal(int)  # emits number of patterns upserted
    error = Signal(str)

    def __init__(
        self,
        session_factory: Callable[[], Any],
        batch_size: int | None = None,
        flush_delay_sec: float | None = None,
    ) -> None:
        super().__init__()
        self._session_factory = session_factory
        self._batch_size: int = (
            batch_size if batch_size is not None else self.BATCH_SIZE
        )
        self._flush_delay_sec: float = float(
            flush_delay_sec if flush_delay_sec is not None else self.FLUSH_DELAY_SEC
        )
        self._flush_timer: threading.Timer | None = None
        self._pending: int = 0
        # B-105 / BUG-2-b: ``_pending`` is mutated from any thread that
        # raises a feedback event. ``self._pending += 1`` is not atomic
        # in CPython, and the threshold check + flush is a TOCTOU race.
        self._pending_lock: threading.Lock = threading.Lock()
        self._flush_condition = threading.Condition(self._pending_lock)
        self._flush_in_progress: bool = False
        self._gui_thread_warning_logged: bool = False
        self._aggregator = PatternAggregator(session_factory=session_factory)

    # ── Public API ───────────────────────────────────────────────────────────

    def notify_feedback(self) -> bool:
        """Called on each feedback event.

        Increments the internal counter and schedules a background flush if
        the batch size is reached. Returns True if a batch was scheduled,
        False otherwise.

        B-105: increment + threshold check are guarded by
        ``_pending_lock`` so concurrent calls cannot both cross the
        threshold. If another flush is already in progress, the new event
        remains counted for the next batch and no second concurrent flush is
        started.

        B-737: wird die Schwelle nicht erreicht, laeuft trotzdem ein
        Debounce-Timer an. Der Rueckgabewert bleibt bei seiner alten
        Bedeutung ("Batch SOFORT geschedult?"), damit bestehende Aufrufer
        und Tests unveraendert weiterlaufen.
        """
        with self._flush_condition:
            self._pending += 1
            if self._flush_in_progress:
                return False
            if self._pending < self._batch_size:
                self._arm_flush_timer_locked()
                return False
            claimed_pending = self._claim_flush_locked()
            self._cancel_flush_timer_locked()
        self._start_background_flush(claimed_pending)
        return True

    # ── B-737: Debounce-Timer ────────────────────────────────────────────────

    def _arm_flush_timer_locked(self) -> None:
        """Startet den Debounce-Timer. Aufrufer haelt ``_pending_lock``."""
        if self._flush_delay_sec <= 0 or self._flush_timer is not None:
            return
        timer = threading.Timer(self._flush_delay_sec, self._on_flush_timer)
        timer.name = "MemoryUpdaterWorkerDebounce"
        timer.daemon = True
        self._flush_timer = timer
        timer.start()

    def _cancel_flush_timer_locked(self) -> None:
        """Stoppt einen laufenden Timer. Aufrufer haelt ``_pending_lock``."""
        timer = self._flush_timer
        self._flush_timer = None
        if timer is not None:
            timer.cancel()

    def _on_flush_timer(self) -> None:
        with self._flush_condition:
            self._flush_timer = None
            if self._pending <= 0 or self._flush_in_progress:
                return
            claimed_pending = self._claim_flush_locked()
        logger.info(
            "MemoryUpdaterWorker: Debounce-Flush nach %.1fs "
            "(unterhalb BATCH_SIZE=%d).",
            self._flush_delay_sec, self._batch_size,
        )
        self._run_aggregation(claimed_pending)

    def shutdown(
        self,
        timeout_sec: float = 30.0,
        *,
        raise_on_error: bool = False,
    ) -> int:
        """B-737: letzter Flush beim Schliessen / am Lauf-Ende.

        Stoppt den Debounce-Timer und aggregiert synchron, falls noch
        Ereignisse offen sind. Ohne offene Ereignisse passiert nichts.
        Returns: Anzahl upserteter Pattern-Zeilen.
        """
        return self._drain_flush_generations(
            timeout_sec=timeout_sec,
            context="shutdown",
            force_first=False,
            raise_on_error=raise_on_error,
        )

    def _start_background_flush(self, claimed_pending: int) -> None:
        thread = threading.Thread(
            target=self._run_scheduled_flush,
            args=(claimed_pending,),
            name="MemoryUpdaterWorkerFlush",
            daemon=True,
        )
        thread.start()

    def _run_scheduled_flush(self, claimed_pending: int) -> None:
        self._run_aggregation(claimed_pending)

    def notify_run_end(
        self,
        timeout_sec: float = 30.0,
        *,
        raise_on_error: bool = False,
    ) -> int:
        """Called when a pacing run ends.

        Always flushes regardless of the pending counter.
        Returns the number of patterns upserted (0 if nothing was pending).
        """
        return self._drain_flush_generations(
            timeout_sec=timeout_sec,
            context="run end",
            force_first=True,
            raise_on_error=raise_on_error,
        )

    def run(self, *, raise_on_error: bool = False) -> int:
        """Synchronous aggregation.

        Runs PatternAggregator, resets the pending counter, and emits Qt
        signals so the caller can wire this into a QThread if desired.
        Returns the number of patterns upserted.
        """
        with self._flush_condition:
            # B-737: ein expliziter Lauf macht den Debounce-Timer gegenstandslos.
            self._cancel_flush_timer_locked()
            if self._flush_in_progress:
                logger.info("MemoryUpdaterWorker: flush already in progress; skip sync run.")
                return 0
            claimed_pending = self._claim_flush_locked()
        return self._run_aggregation(
            claimed_pending,
            raise_on_error=raise_on_error,
        )

    def _claim_flush_locked(self) -> int:
        """Claim current generation while ``_flush_condition`` is held."""
        claimed_pending = self._pending
        self._pending = 0
        self._flush_in_progress = True
        return claimed_pending

    def _wait_for_idle_locked(self, timeout_sec: float, context: str) -> None:
        """Generation-safe wait while ``_flush_condition`` is held."""
        if self._flush_condition.wait_for(
            lambda: not self._flush_in_progress,
            timeout=max(0.0, timeout_sec),
        ):
            return
        raise TimeoutError(
            "MemoryUpdaterWorker: active aggregation did not finish "
            f"within {timeout_sec:.1f}s at {context}"
        )

    def _drain_flush_generations(
        self,
        *,
        timeout_sec: float,
        context: str,
        force_first: bool,
        raise_on_error: bool,
    ) -> int:
        """Drain generations until no feedback arrived during the last flush."""
        deadline = time.monotonic() + max(0.0, timeout_sec)
        total = 0
        must_flush = force_first
        attempted_generation = False
        while True:
            with self._flush_condition:
                self._cancel_flush_timer_locked()
                remaining = max(0.0, deadline - time.monotonic())
                self._wait_for_idle_locked(remaining, context)
                if self._pending <= 0 and not must_flush:
                    return total
                if attempted_generation and remaining <= 0.0:
                    message = (
                        "MemoryUpdaterWorker: pending feedback remained after "
                        f"{timeout_sec:.1f}s at {context}"
                    )
                    if raise_on_error:
                        raise TimeoutError(message)
                    logger.warning(message)
                    return total
                claimed_pending = self._claim_flush_locked()
                must_flush = False
                attempted_generation = True
            try:
                total += self._run_aggregation(
                    claimed_pending,
                    raise_on_error=True,
                )
            except Exception:
                if raise_on_error:
                    raise
                return total

    def _run_aggregation(
        self,
        claimed_pending: int,
        *,
        raise_on_error: bool = False,
    ) -> int:
        self.started.emit()
        try:
            n = self._aggregator.run()
            self._finish_flush(claimed_pending, failed=False)
            self.finished.emit(n)
            return n
        except Exception as exc:  # broad catch — top-level worker safety net
            logger.error(
                "MemoryUpdaterWorker: aggregation failed: %s\n%s",
                exc,
                traceback.format_exc(),
            )
            self._finish_flush(claimed_pending, failed=True)
            self.error.emit(str(exc))
            if raise_on_error:
                raise
            return 0

    def _finish_flush(self, claimed_pending: int, *, failed: bool) -> None:
        """Close one generation and wake waiters under the same condition."""
        with self._flush_condition:
            if failed:
                self._pending += claimed_pending
            self._flush_in_progress = False
            if self._pending > 0:
                self._arm_flush_timer_locked()
            self._flush_condition.notify_all()

    # ── Diagnostics ──────────────────────────────────────────────────────────

    @property
    def pending_events(self) -> int:
        """Internal counter — for diagnostics and tests."""
        with self._pending_lock:
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
                # B-737: Restereignisse duerfen beim Schliessen nicht
                # verfallen. ``notify_run_end()`` hatte im Produktivcode
                # keinen Aufrufer — atexit ist der einzige Haken, der ohne
                # Aenderung an ui/timeline.py greift.
                atexit.register(flush_default_memory_updater)
                logger.info(
                    "MemoryUpdaterWorker: Singleton erstellt "
                    "(batch_size=%d, flush_delay=%.1fs).",
                    _default_memory_updater._batch_size,
                    _default_memory_updater._flush_delay_sec,
                )
    return _default_memory_updater


def flush_default_memory_updater(
    *,
    timeout_sec: float = 30.0,
    raise_on_error: bool = False,
) -> int:
    """B-737: Restereignisse des Singletons aggregieren (Lauf-Ende/Shutdown).

    Legt KEINEN Singleton an — gab es keinen, gab es auch keine Ereignisse.
    ``raise_on_error=False`` ist fuer ``atexit`` best-effort. Explizite
    Projektwechsel-/Shutdown-Pfade koennen Fehler strikt propagieren.
    """
    updater = _default_memory_updater
    if updater is None:
        return 0
    try:
        return updater.shutdown(
            timeout_sec=timeout_sec,
            raise_on_error=raise_on_error,
        )
    except Exception as exc:  # broad: Shutdown darf nie eskalieren
        logger.warning("MemoryUpdaterWorker: Shutdown-Flush fehlgeschlagen: %s", exc)
        if raise_on_error:
            raise
        return 0
