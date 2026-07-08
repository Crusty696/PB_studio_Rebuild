"""FeedbackService — persists a user-feedback event and updates the decision.

Called by InteractiveTimeline.keyPressEvent when the user presses A/R/S/1-5
on a selected clip. Single-row insert + single-row update, both on a short-
lived connection. Logs and swallows errors (feedback is best-effort; UI
must not crash on a transient DB lock).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import text

logger = logging.getLogger(__name__)


VERDICT_FROM_KEY: dict[str, str] = {
    "A": "accept",
    "R": "reject",
    "S": "skip",
}


@dataclass(frozen=True)
class FeedbackResult:
    success: bool
    event_id: int | None
    decision_id: int | None
    error: str | None = None


class FeedbackService:
    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def record_verdict(
        self, run_id: int, scene_id: int, verdict: str
    ) -> FeedbackResult:
        """Insert mem_user_feedback_event + update mem_decision.user_verdict for the
        most-recent decision on (run_id, scene_id).

        verdict ∈ {"accept", "reject", "skip", "modify", "replace"} — documented set.
        Returns FeedbackResult with success=False on error (errors are logged, not raised).
        """
        allowed = {"accept", "reject", "skip", "modify", "replace"}
        if verdict not in allowed:
            return FeedbackResult(False, None, None, f"invalid verdict {verdict!r}")

        session = self._session_factory()
        ownership = False
        try:
            if hasattr(session, "__enter__") and not hasattr(session, "execute"):
                session = session.__enter__()
                ownership = True

            # Find the most-recent decision for (run_id, scene_id).
            # T1.4 (USE-006): sequence_idx / at_section_type / at_timestamp_sec
            # zusaetzlich lesen, um den RL-v2-Stack zu speisen.
            row = session.execute(
                text(
                    "SELECT id, sequence_idx, at_section_type, at_timestamp_sec "
                    "FROM mem_decision "
                    "WHERE run_id = :rid AND scene_id = :sid "
                    "ORDER BY sequence_idx DESC LIMIT 1"
                ),
                {"rid": run_id, "sid": scene_id},
            ).fetchone()
            if row is None:
                return FeedbackResult(
                    False,
                    None,
                    None,
                    f"no mem_decision for run={run_id} scene={scene_id}",
                )
            decision_id = int(row[0])
            _seq_idx = int(row[1]) if row[1] is not None else 0
            _section_type = str(row[2]) if row[2] is not None else "verse"
            _ts_sec = float(row[3]) if row[3] is not None else 0.0

            # Insert event
            now = datetime.now(timezone.utc)
            event_row = session.execute(
                text(
                    "INSERT INTO mem_user_feedback_event "
                    "(decision_id, run_id, event_type, created_at) "
                    "VALUES (:did, :rid, :type, :ts) RETURNING id"
                ),
                {"did": decision_id, "rid": run_id, "type": verdict, "ts": now},
            ).fetchone()
            event_id = int(event_row[0]) if event_row is not None else None

            # Update decision's verdict (only if currently NULL — don't clobber older explicit feedback)
            # B-377: "replace" gehoert zur dokumentierten verdict-Menge und
            # muss ebenfalls nach mem_decision.user_verdict gespiegelt werden.
            if verdict in ("accept", "reject", "skip", "modify", "replace"):
                session.execute(
                    text(
                        "UPDATE mem_decision SET user_verdict = :v, user_verdict_at = :ts "
                        "WHERE id = :id AND user_verdict IS NULL"
                    ),
                    {"v": verdict, "ts": now, "id": decision_id},
                )

            session.commit()
            logger.info(
                "feedback recorded: run=%d scene=%d verdict=%s event=%s",
                run_id,
                scene_id,
                verdict,
                event_id,
            )
            # T1.4 (USE-006): Verdict in den RL-v2-Stack + WeightStore
            # propagieren (best-effort, nach erfolgreichem Commit).
            self._propagate_rl_v2(
                run_id=run_id,
                scene_id=scene_id,
                verdict=verdict,
                decision_id=decision_id,
                sequence_idx=_seq_idx,
                section_type=_section_type,
                timestamp_sec=_ts_sec,
            )
            return FeedbackResult(True, event_id, decision_id)

        except Exception as e:
            logger.warning(
                "feedback_service error: run=%s scene=%s verdict=%s err=%s",
                run_id,
                scene_id,
                verdict,
                e,
            )
            try:
                session.rollback()
            except Exception:
                pass
            return FeedbackResult(False, None, None, str(e))
        finally:
            try:
                if ownership:
                    session.__exit__(None, None, None)
                else:
                    close = getattr(session, "close", None)
                    if callable(close):
                        close()
            except Exception:
                pass

    # NEUBAU-VOLLINTEGRATION T1.4 (USE-006): Section-Mapping mem_decision
    # (intro|buildup|drop|breakdown|outro|verse|chorus|bridge|transition,
    # ggf. uppercase aus dem Pacing) -> CutContext.VALID_SECTIONS
    # (intro|verse|build|drop|break|outro|transition).
    _SECTION_TO_BRAIN: dict[str, str] = {
        "intro": "intro", "verse": "verse", "buildup": "build",
        "build": "build", "drop": "drop", "breakdown": "break",
        "break": "break", "outro": "outro", "transition": "transition",
        "chorus": "drop", "bridge": "transition",
    }

    def _propagate_rl_v2(
        self,
        *,
        run_id: int,
        scene_id: int,
        verdict: str,
        decision_id: int,
        sequence_idx: int,
        section_type: str,
        timestamp_sec: float,
    ) -> None:
        """T1.4 (USE-006): Timeline-Verdict an den RL-Stack v2 anschliessen.

        1. RLPacingMemoryV2 (prozessweiter Singleton): Verdict-Replay,
           SectionPolicy-Update, VarietyMemory. Bewusst OHNE
           db_session_factory — den mem_decision-Write hat record_verdict
           bereits gemacht; ein zweiter Writer waere der im Plan verbotene
           stille Doppel-Write. Das alte services/pacing_memory.py bleibt
           unberuehrt (Track-Level-Sentiment, anderer Scope).
        2. Brain-V3-WeightStore: accept -> 'fits', reject -> 'no_match'
           via BrainV3Service.feedback (gleicher Pfad wie das
           Brain-V3-Feedback-Popup) — damit veraendern A/R-Verdicts
           nachweisbar die Reranker-Gewichte (T1.2-Pfad).

        Best-effort: Fehler werden geloggt, nie geraised (Feedback darf
        die UI nicht crashen).
        """
        v2_verdict = {"accept": "good", "reject": "bad"}.get(verdict)
        try:
            from services.pacing.rl_memory_v2 import (
                DecisionRecord,
                get_default_rl_memory,
            )
            get_default_rl_memory().record(DecisionRecord(
                run_id=run_id,
                cut_id=sequence_idx,
                timestamp_ms=int(timestamp_sec * 1000),
                section_type=section_type,
                scene_id=scene_id,
                verdict=v2_verdict,
                reward=1.0 if v2_verdict == "good" else 0.0,
            ))
        except Exception as exc:
            logger.warning("T1.4: RL-v2-Record fehlgeschlagen: %s", exc)

        rating = {"accept": "fits", "reject": "no_match"}.get(verdict)
        if rating is None:
            return  # skip/modify/replace: kein Gewichts-Signal
        try:
            from services.brain.brain_v3_service import BrainV3Service
            from services.brain.context_resolver import CutContext
            from services.brain.schemas.brain_v3_schemas import FeedbackRequest
            section = self._SECTION_TO_BRAIN.get(
                section_type.strip().lower(), "verse")
            resp = BrainV3Service().feedback(
                FeedbackRequest(cut_id=decision_id, rating=rating),
                context=CutContext(audio_section_type=section),
            )
            logger.info(
                "T1.4: Verdict %s -> WeightStore (%d Buckets aktualisiert).",
                verdict, resp.n_buckets_updated,
            )
        except Exception as exc:
            logger.warning("T1.4: WeightStore-Update fehlgeschlagen: %s", exc)

    def record_rating(self, run_id: int, scene_id: int, rating: int) -> FeedbackResult:
        """Similar to record_verdict but writes the numeric user_rating (1-5)
        into mem_decision and emits a 'rate' event."""
        if not (1 <= rating <= 5):
            return FeedbackResult(
                False, None, None, f"rating must be 1..5, got {rating}"
            )

        session = self._session_factory()
        ownership = False
        try:
            if hasattr(session, "__enter__") and not hasattr(session, "execute"):
                session = session.__enter__()
                ownership = True

            row = session.execute(
                text(
                    "SELECT id FROM mem_decision WHERE run_id = :rid AND scene_id = :sid "
                    "ORDER BY sequence_idx DESC LIMIT 1"
                ),
                {"rid": run_id, "sid": scene_id},
            ).fetchone()
            if row is None:
                return FeedbackResult(
                    False,
                    None,
                    None,
                    f"no mem_decision for run={run_id} scene={scene_id}",
                )
            decision_id = int(row[0])

            now = datetime.now(timezone.utc)
            import json

            event_row = session.execute(
                text(
                    "INSERT INTO mem_user_feedback_event "
                    "(decision_id, run_id, event_type, payload, created_at) "
                    "VALUES (:did, :rid, 'rate', :pl, :ts) RETURNING id"
                ),
                {
                    "did": decision_id,
                    "rid": run_id,
                    "pl": json.dumps({"rating": rating}),
                    "ts": now,
                },
            ).fetchone()
            event_id = int(event_row[0]) if event_row is not None else None

            session.execute(
                text("UPDATE mem_decision SET user_rating = :r WHERE id = :id"),
                {"r": rating, "id": decision_id},
            )

            session.commit()
            return FeedbackResult(True, event_id, decision_id)

        except Exception as e:
            logger.warning("feedback_service.record_rating error: %s", e)
            try:
                session.rollback()
            except Exception:
                pass
            return FeedbackResult(False, None, None, str(e))
        finally:
            try:
                if ownership:
                    session.__exit__(None, None, None)
                else:
                    close = getattr(session, "close", None)
                    if callable(close):
                        close()
            except Exception:
                pass
