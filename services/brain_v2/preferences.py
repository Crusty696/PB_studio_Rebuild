"""Feedback-to-memory aggregation for Studio Brain v2."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import text

from services.brain_v2.store import _json, _now

VALID_FEEDBACK_TYPES = {
    "fits",
    "wrong_mood",
    "too_hectic",
    "too_calm",
    "wrong_moment",
    "too_repetitive",
    "visual_mismatch",
    "drop_needs_more_impact",
}

_POSITIVE = {"fits"}


@dataclass(frozen=True)
class BrainPreferenceUpdate:
    decision_id: int
    feedback_type: str
    updated_count: int


class BrainPreferenceService:
    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def record_feedback(
        self,
        decision_id: int,
        feedback_type: str,
        comment: str | None = None,
    ) -> BrainPreferenceUpdate:
        if feedback_type not in VALID_FEEDBACK_TYPES:
            raise ValueError(f"invalid feedback_type: {feedback_type}")
        session = self._session_factory()
        close = getattr(session, "close", None)
        try:
            row = session.execute(
                text("SELECT why_json FROM brain_decision WHERE id = :id OR decision_id = :id"),
                {"id": int(decision_id)},
            ).fetchone()
            why = json.loads(row[0]) if row and row[0] else {}
            scopes = self._scopes_from_why(why)
            positive = 1 if feedback_type in _POSITIVE else 0
            negative = 0 if positive else 1
            for scope in scopes:
                self._upsert_memory(session, scope, feedback_type, comment, positive, negative)
            session.commit()
            return BrainPreferenceUpdate(
                decision_id=int(decision_id),
                feedback_type=feedback_type,
                updated_count=len(scopes),
            )
        finally:
            if callable(close):
                close()

    @staticmethod
    def _scopes_from_why(why: dict[str, Any]) -> list[str]:
        audio = why.get("audio") if isinstance(why.get("audio"), dict) else {}
        clip = why.get("clip") if isinstance(why.get("clip"), dict) else {}
        scopes = ["global"]
        section = audio.get("section") or audio.get("section_type")
        if section:
            scopes.append(f"section:{section}")
        role = clip.get("role")
        if role:
            scopes.append(f"clip_role:{role}")
        mood = clip.get("mood") or clip.get("mood_refined")
        if mood:
            scopes.append(f"mood:{mood}")
        return scopes

    @staticmethod
    def _upsert_memory(
        session: Any,
        scope: str,
        feedback_type: str,
        comment: str | None,
        positive: int,
        negative: int,
    ) -> None:
        row = session.execute(
            text(
                "SELECT id, positive_count, negative_count, payload_json "
                "FROM brain_memory WHERE memory_type = 'feedback_preference' AND scope = :scope"
            ),
            {"scope": scope},
        ).fetchone()
        payload = {"last_feedback_type": feedback_type, "last_comment": comment}
        now = _now()
        if row is None:
            confidence = 1.0
            session.execute(
                text(
                    """
                    INSERT INTO brain_memory
                    (memory_type, scope, payload_json, confidence, positive_count, negative_count, updated_at)
                    VALUES
                    ('feedback_preference', :scope, :payload_json, :confidence, :positive, :negative, :now)
                    """
                ),
                {
                    "scope": scope,
                    "payload_json": _json(payload),
                    "confidence": confidence,
                    "positive": positive,
                    "negative": negative,
                    "now": now,
                },
            )
            return
        pos = int(row[1] or 0) + positive
        neg = int(row[2] or 0) + negative
        confidence = min(1.0, (pos + neg) / 5.0)
        old_payload = json.loads(row[3] or "{}")
        old_payload.update(payload)
        session.execute(
            text(
                """
                UPDATE brain_memory
                SET payload_json = :payload_json,
                    confidence = :confidence,
                    positive_count = :positive,
                    negative_count = :negative,
                    updated_at = :now
                WHERE id = :id
                """
            ),
            {
                "id": int(row[0]),
                "payload_json": _json(old_payload),
                "confidence": confidence,
                "positive": pos,
                "negative": neg,
                "now": now,
            },
        )
