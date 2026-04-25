"""DecisionRecorder — persists every pacing decision as a mem_decision row.

Design §4.3: mem_decision snapshots are IMMUTABLE TRUTH. Every at_* field
is copied from the live AudioContext at the moment of the decision; the
recorder never back-references a live Beatgrid/Structure row, because
re-analysis would silently rewrite history.

The recorder is the ONLY write-path into mem_decision from the pacing pipeline.
Bug F in the failed-attempt audit: the previous implementation had a
DecisionRecorder class that was never called — so no row ever landed in
mem_decision, and the whole learning loop was dead.

Usage:
    recorder = DecisionRecorder(session_factory=my_factory)
    result = pipeline.select_best(candidates, ctx, predecessor=prev)
    if result.chosen is not None:
        decision_id = recorder.record(
            run_id=active_run_id,
            sequence_idx=seq,
            ctx=ctx,
            chosen=result.chosen,
            rationale=result.rationale,
            agent_score=result.rationale["chosen_score"],
        )

The pipeline itself wires this call (see pipeline.py).  If no recorder is
injected, the pipeline silently skips persistence — useful for tests and
for the future standalone "simulate-run" mode.

SQLite WAL + retry contract:
- Up to 3 retries on OperationalError with exponential backoff (100ms, 400ms, 1600ms).
- Beyond that, the record is appended to an in-memory queue. The caller can
  drain the queue via recorder.flush_queue() once contention subsides.

THREADING CONTRACT (B-104 / BUG-3-b):
- ``record()`` may block for up to ~2.1 seconds if SQLite is contended
  (3 retries × cumulative backoff). It MUST be called from a worker
  thread, never from the Qt GUI thread.
- A single decision is fast; a 60-cut run × worst-case backoff = ~2 min
  GUI freeze if wired wrong. The Studio Brain Steer-tab "Run"-Button
  must dispatch to a QThread/worker.
- We log a warning when ``record()`` runs on the Qt GUI thread (only if
  a ``QApplication`` is alive and we're on its main thread); tests and
  CLI scripts run on the main thread without a QApplication and are
  silently allowed.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from services.enrichment import ENRICHER_VERSION
from services.pacing.scorer import AudioContext, ClipFeatures

logger = logging.getLogger(__name__)


# Lists of the at_* fields that MUST be copied into every mem_decision row.
# Used by test_record_persists_all_audio_context_fields to catch omissions.
# Note: at_structure_segment_id and at_key_modulation are mem_decision DB columns
# that are NOT present on AudioContext (they come from structural analysis and are
# nullable by design — callers may pass them separately if available).
AUDIO_CTX_SNAPSHOT_FIELDS: tuple[str, ...] = (
    "at_timestamp_sec",
    "at_beat_idx",
    "at_bpm",
    "at_energy",
    "at_section_type",
    "at_key",
    "at_key_confidence",
    "at_harmonic_tension",
    "at_mood_audio",
    "at_genre",
    "at_sub_genre",
    "at_spectral_hash",
    "at_groove_template",
    "at_lufs",
)


@dataclass
class _QueuedDecision:
    """Retained in-memory when every DB retry fails."""

    run_id: int
    sequence_idx: int
    payload: dict[str, Any]
    reason: str


def _warn_if_on_gui_thread() -> None:
    """B-104 / BUG-3-b: warn if ``record()`` runs on the Qt GUI thread.

    The recorder's ``time.sleep`` retry can block the caller for up to
    ~2.1 seconds. On the GUI thread that translates to a UI freeze.
    We can't import PySide6 unconditionally (the recorder is also used
    from CLI scripts and tests without Qt) — only check when Qt is loaded.
    """
    import sys

    qtcore = sys.modules.get("PySide6.QtCore")
    if qtcore is None:
        return  # No Qt loaded — nothing to compare against.
    QApplication = getattr(sys.modules.get("PySide6.QtWidgets"), "QApplication", None)
    if QApplication is None:
        return
    app = QApplication.instance()
    if app is None:
        return  # Qt loaded but no app — likely a unit test.
    QThread = getattr(qtcore, "QThread", None)
    if QThread is None:
        return
    if QThread.currentThread() is app.thread():
        logger.warning(
            "DecisionRecorder.record() is running on the Qt GUI thread. "
            "Each call may block up to ~2.1s on SQLite contention; over "
            "60 cuts that is a multi-minute UI freeze. Dispatch the "
            "pacing pipeline to a QThread worker instead."
        )


class DecisionRecorder:
    MAX_RETRIES: int = 3
    INITIAL_BACKOFF_SEC: float = 0.1

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        """Args:
        session_factory: callable returning a SQLAlchemy session (or session-context-
            manager). The recorder calls `session_factory()`, commits, then closes.
        """
        self._session_factory = session_factory
        self._queue: list[_QueuedDecision] = []
        # B-161: Lock fuer _queue. record() laeuft im Worker-Thread,
        # flush_queue() im Main-Thread — list.append/iterate gleichzeitig
        # ist nicht thread-safe (CPython GIL schuetzt nur einzelne Bytecodes).
        self._queue_lock = threading.Lock()
        self._gui_thread_warning_logged: bool = False

    def record(
        self,
        run_id: int,
        sequence_idx: int,
        ctx: AudioContext,
        chosen: ClipFeatures,
        rationale: dict[str, Any],
        agent_score: float,
    ) -> int | None:
        """Persist a decision row. Returns the new mem_decision.id, or None
        if all retries failed (the decision is then in self._queue).

        The rationale dict is stored as JSON in mem_decision.agent_rationale.
        at_enricher_version is stamped from services.enrichment.ENRICHER_VERSION
        at the moment of the call, not the import time, so re-runs after an
        enricher upgrade snapshot the correct version.
        """
        payload = self._build_payload(
            run_id, sequence_idx, ctx, chosen, rationale, agent_score
        )
        if not self._gui_thread_warning_logged:
            _warn_if_on_gui_thread()
            self._gui_thread_warning_logged = True
        try:
            decision_id = self._insert_with_retry(payload)
            return decision_id
        except OperationalError as exc:
            logger.warning(
                "DecisionRecorder: %d retries exhausted for run_id=%s seq=%d; queueing. err=%s",
                self.MAX_RETRIES,
                run_id,
                sequence_idx,
                exc,
            )
            # B-161: queue-mutation unter Lock
            with self._queue_lock:
                self._queue.append(
                    _QueuedDecision(
                        run_id=run_id,
                        sequence_idx=sequence_idx,
                        payload=payload,
                        reason=str(exc),
                    )
                )
            return None

    @staticmethod
    def _build_payload(
        run_id: int,
        sequence_idx: int,
        ctx: AudioContext,
        chosen: ClipFeatures,
        rationale: dict[str, Any],
        agent_score: float,
    ) -> dict[str, Any]:
        import json

        return {
            "run_id": run_id,
            "sequence_idx": sequence_idx,
            # Audio snapshot (all at_* fields)
            **{f: getattr(ctx, f, None) for f in AUDIO_CTX_SNAPSHOT_FIELDS},
            # Video snapshot
            "scene_id": chosen.scene_id,
            "clip_role": chosen.role,
            "clip_mood_refined": chosen.mood_refined,
            "clip_style_bucket_id": chosen.style_bucket_id,
            "clip_motion_score": chosen.motion_score,
            # Decision payload
            "agent_score": float(agent_score),
            "agent_rationale": json.dumps(rationale, default=str),
            # Enricher-version snapshot (Feasibility R4)
            "at_enricher_version": ENRICHER_VERSION,
            # User-verdict fields start null; user_feedback later fills them in
            "user_verdict": None,
            "user_verdict_at": None,
            "user_rating": None,
        }

    def _insert_with_retry(self, payload: dict[str, Any]) -> int:
        backoff = self.INITIAL_BACKOFF_SEC
        last_err: OperationalError | None = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                return self._insert_once(payload)
            except OperationalError as exc:
                last_err = exc
                if attempt < self.MAX_RETRIES:
                    logger.info(
                        "DecisionRecorder: OperationalError attempt %d/%d, backoff %.2fs: %s",
                        attempt + 1,
                        self.MAX_RETRIES,
                        backoff,
                        exc,
                    )
                    time.sleep(backoff)
                    backoff *= 4  # 100 → 400 → 1600 ms
        assert last_err is not None
        raise last_err

    def _insert_once(self, payload: dict[str, Any]) -> int:
        session = self._session_factory()
        ownership = False
        try:
            # Detect whether we got a context-manager-style or a plain session
            if hasattr(session, "__enter__") and not hasattr(session, "execute"):
                session = session.__enter__()
                ownership = True

            columns = ", ".join(payload.keys())
            placeholders = ", ".join(f":{k}" for k in payload.keys())
            sql = text(
                f"INSERT INTO mem_decision ({columns}) VALUES ({placeholders}) RETURNING id"
            )
            result = session.execute(sql, payload)
            row = result.fetchone()
            if row is None:
                # SQLite older versions lack RETURNING; fall back to last_insert_rowid
                row_id_result = session.execute(text("SELECT last_insert_rowid()"))
                decision_id = int(row_id_result.scalar() or 0)
            else:
                decision_id = int(row[0])
            session.commit()
            return decision_id
        finally:
            try:
                if ownership:
                    session.__exit__(None, None, None)
                else:
                    close = getattr(session, "close", None)
                    if callable(close):
                        close()
            except Exception:
                pass  # best-effort cleanup

    def flush_queue(self) -> int:
        """Retry every queued decision once. Returns count successfully drained.

        B-161: Snapshot unter _queue_lock, retry ausserhalb des Locks
        (DB-Calls duerfen nicht den Lock halten), dann remaining wieder
        unter Lock zurueckschreiben — wobei zwischenzeitliche record()-
        Appends nicht verloren gehen.
        """
        drained = 0
        with self._queue_lock:
            snapshot = list(self._queue)
            self._queue.clear()
        remaining: list[_QueuedDecision] = []
        for q in snapshot:
            try:
                self._insert_with_retry(q.payload)
                drained += 1
            except OperationalError:
                remaining.append(q)
        if remaining:
            with self._queue_lock:
                # Andere record()-Appends seit dem clear wandern nach hinten
                self._queue[:0] = remaining
        return drained

    @property
    def queue_size(self) -> int:
        return len(self._queue)
