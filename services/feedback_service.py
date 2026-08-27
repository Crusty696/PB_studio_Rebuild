"""FeedbackService — persists a user-feedback event and updates the decision.

Called by InteractiveTimeline.keyPressEvent when the user presses A/R/S/1-5
on a selected clip. Single-row insert + single-row update, both on a short-
lived connection. Logs and swallows errors (feedback is best-effort; UI
must not crash on a transient DB lock).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from sqlalchemy import text

logger = logging.getLogger(__name__)


VERDICT_FROM_KEY: dict[str, str] = {
    "A": "accept",
    "R": "reject",
    "S": "skip",
}


# Zusatz-Spalten fuer Kontext + Credit-Assignment. Bewusst als SEPARATE,
# best-effort-Query: aeltere/abgespeckte mem_decision-Schemata (Unit-Test-
# Fixtures) haben diese Spalten nicht, und ein Feedback-Write darf daran
# nicht scheitern.
_LEARNING_SIGNAL_SQL = text(
    "SELECT at_energy, at_mood_audio, at_bpm, clip_motion_score, "
    "       at_section_type, agent_rationale "
    "FROM mem_decision WHERE id = :id"
)


def load_decision_learning_signal(
    session: Any, decision_id: int
) -> tuple[Any, dict[str, float]]:
    """Liest CutContext + Achsen-Beitraege einer Entscheidung.

    Beides kommt aus derselben ``mem_decision``-Zeile:
      - Kontext (Section/Mood/Energie/Motion/Pace) fuer den 6-stufigen
        Backoff der Brain-V3-Gewichte,
      - ``agent_rationale`` -> ``brain_v3_scores`` bzw. ``contribs`` fuer
        das Credit-Assignment.

    Returns:
        ``(CutContext | None, axis_contributions)``. Bei fehlenden Spalten
        oder DB-Fehlern ``(None, {})`` — der Aufrufer faellt dann auf den
        alten, groberen Pfad zurueck statt zu crashen.
    """
    from services.brain.feedback_logger import axis_contributions_from_rationale

    try:
        row = session.execute(
            _LEARNING_SIGNAL_SQL, {"id": int(decision_id)}
        ).mappings().fetchone()
    except Exception as exc:
        logger.info(
            "feedback_service: Lern-Signal fuer decision=%s nicht lesbar "
            "(%s) — Kontext/Credit fallen auf Default zurueck.",
            decision_id, exc,
        )
        try:
            session.rollback()
        except Exception:  # nosec B110 - Rollback-Fehler darf Feedback nicht killen
            pass
        return None, {}
    if row is None:
        return None, {}

    rationale: Any = row.get("agent_rationale")
    if isinstance(rationale, str):
        try:
            rationale = json.loads(rationale)
        except (TypeError, ValueError):
            rationale = None
    contributions = axis_contributions_from_rationale(
        rationale if isinstance(rationale, Mapping) else None
    )
    return build_cut_context_from_decision(row), contributions


def build_cut_context_from_decision(row: Mapping[str, Any]) -> Any:
    """Baut einen echten ``CutContext`` aus einer mem_decision-Zeile.

    Nutzt ausschliesslich den vorhandenen Kontextbegriff
    (``services.brain.context_mapping`` + ``context_resolver``), kein
    zweites Vokabular. Fehlende Felder fallen auf die neutralen
    CutContext-Defaults zurueck.
    """
    from services.brain.context_mapping import (
        ContextMappingConfig,
        build_cut_context,
    )
    from services.brain.context_resolver import (
        quantize_quartile,
        quantize_tertile,
    )

    energy = _as_float(row.get("at_energy"))
    motion = _as_float(row.get("clip_motion_score"))
    bpm = _as_float(row.get("at_bpm"))

    return build_cut_context(
        raw_section=str(row.get("at_section_type") or "verse"),
        raw_mood=str(row.get("at_mood_audio") or "neutral"),
        raw_subtrack_position="middle",  # nicht in mem_decision gespeichert
        raw_energy_level=(
            quantize_tertile(energy, 0.33, 0.66) if energy is not None else "medium"
        ),
        raw_motion_class=(
            quantize_quartile(motion, 0.25, 0.5, 0.75)
            if motion is not None else "medium"
        ),
        # pace aus dem gespeicherten BPM statt aus 'recent_cuts' — beim
        # Feedback gibt es keine Live-Cut-Historie mehr.
        cfg=ContextMappingConfig(pace_source="audio_bpm"),
        audio_bpm=bpm,
    )


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class FeedbackResult:
    success: bool
    event_id: int | None
    decision_id: int | None
    error: str | None = None


class FeedbackService:
    def __init__(
        self,
        session_factory: Callable[[], Any],
        pattern_notifier: Callable[[], object] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._pattern_notifier = pattern_notifier

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
            # Credit-Assignment (2026-07-27): echter CutContext + Achsen-
            # Beitraege aus derselben mem_decision-Zeile nachladen. Nach dem
            # Commit, best-effort — schlaegt das fehl, bleibt es beim alten,
            # groben Section-Only-Kontext.
            cut_context, axis_contributions = load_decision_learning_signal(
                session, decision_id
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
                cut_context=cut_context,
                axis_contributions=axis_contributions,
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
        cut_context: Any = None,
        axis_contributions: Mapping[str, float] | None = None,
    ) -> None:
        """T1.4 (USE-006): Timeline-Verdict an den RL-Stack v2 anschliessen.

        1. RLPacingMemoryV2 (prozessweiter Singleton): Verdict-Replay,
           SectionPolicy-Update, VarietyMemory. Bewusst OHNE
           db_session_factory — den mem_decision-Write hat record_verdict
           bereits gemacht; ein zweiter Writer waere der im Plan verbotene
           stille Doppel-Write. Das alte services/pacing_memory.py bleibt
           unberuehrt (Track-Level-Sentiment, anderer Scope).
        2. Brain-V3-WeightStore: accept -> 'fits', reject -> 'no_match'
           via ``feedback_logger.submit_feedback`` — mit den Achsen-
           Beitraegen dieser Entscheidung, damit alpha/beta GEWICHTET statt
           uniform verteilt werden. Der Umweg um ``BrainV3Service.feedback``
           ist noetig, weil dessen Signatur die Beitraege nicht durchreicht;
           der Schreibpfad (FeedbackLogger + prozessweiter Lock) ist
           derselbe.

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
            from services.brain import feedback_logger
            from services.brain.context_resolver import CutContext

            ctx = cut_context
            if ctx is None:
                section = self._SECTION_TO_BRAIN.get(
                    section_type.strip().lower(), "verse")
                ctx = CutContext(audio_section_type=section)
            diag = feedback_logger.submit_feedback(
                rating=rating,
                context=ctx,
                # B-894: {} bedeutet autoritativ "keine Signalachse" und
                # darf nicht zu None/Legacy-Uniform kollabieren.
                axis_contributions=axis_contributions,
            )
            logger.info(
                "T1.4: Verdict %s -> WeightStore (%d Buckets, mode=%s, "
                "%d Achsen mit Credit).",
                verdict,
                diag.get("n_buckets_updated", 0),
                diag.get("credit_mode"),
                diag.get("n_axes_credited", 0),
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

    def record_brain_rating(
        self,
        run_id: int,
        scene_id: int,
        brain_rating: str,
    ) -> FeedbackResult:
        """Persist one Brain-V3 4-click rating as decision-level feedback.

        Brain labels map onto the existing 1..5 decision scale so
        ``PatternAggregator`` receives the same semantic signal as Ctrl+1..5:
        perfect/fits are positive; not_quite/no_match are negative.
        """
        mapped_rating = {
            "perfect": 5,
            "fits": 4,
            "not_quite": 2,
            "no_match": 1,
        }.get(brain_rating)
        if mapped_rating is None:
            return FeedbackResult(
                False,
                None,
                None,
                f"invalid brain rating {brain_rating!r}",
            )
        result = self.record_rating(run_id, scene_id, mapped_rating)
        if result.success:
            self._notify_pattern_learning()
        return result

    def _notify_pattern_learning(self) -> None:
        """Schedule aggregation only after semantic decision feedback exists."""
        notifier = self._pattern_notifier
        try:
            if notifier is None:
                from workers.memory_updater import get_memory_updater

                notifier = get_memory_updater().notify_feedback
            notifier()
        except Exception as exc:  # feedback write already committed; retry at lifecycle flush
            logger.debug("Brain pattern notification failed: %s", exc)
