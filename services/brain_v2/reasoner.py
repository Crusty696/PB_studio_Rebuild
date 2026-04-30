"""Ollama-backed reasoning for Studio Brain v2."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

MAX_CONTEXT_CHARS = 6000
VALID_SUGGESTED_TAGS = {
    "fits",
    "wrong_mood",
    "too_hectic",
    "too_calm",
    "wrong_moment",
    "too_repetitive",
    "visual_mismatch",
    "drop_needs_more_impact",
}


@dataclass(frozen=True)
class BrainExplanation:
    summary: str
    fit_reasons: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    suggested_feedback_tags: list[str] = field(default_factory=list)
    used_ollama: bool = False
    error: str | None = None


class BrainContextBuilder:
    def build_clip_match_context(
        self,
        audio_context: dict[str, Any],
        clip_context: dict[str, Any],
        candidates: list[dict[str, Any]],
    ) -> str:
        payload = {
            "audio_context": audio_context,
            "clip_context": clip_context,
            "candidates": candidates[:8],
        }
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        if len(text) > MAX_CONTEXT_CHARS:
            text = text[:MAX_CONTEXT_CHARS] + "\n[truncated]"
        return text


class BrainReasoner:
    def __init__(
        self,
        ollama_client_factory: Callable[[str | None], Any] | None = None,
        context_builder: BrainContextBuilder | None = None,
    ) -> None:
        self._ollama_client_factory = ollama_client_factory
        self._context_builder = context_builder or BrainContextBuilder()

    def explain_clip_match(
        self,
        audio_context: dict[str, Any],
        clip_context: dict[str, Any],
        candidates: list[dict[str, Any]],
        model: str | None = None,
    ) -> BrainExplanation:
        fallback = self._fallback(audio_context, clip_context)
        try:
            client = self._get_client()
            if client is None or not client.is_available():
                return self._with_error(fallback, "ollama_unavailable")
            chosen_model = model or client.get_best_available_model()
            if not chosen_model:
                return self._with_error(fallback, "ollama_model_missing")
            raw = client.chat(
                model=chosen_model,
                system_prompt=self._system_prompt(),
                user_message=self._context_builder.build_clip_match_context(
                    audio_context, clip_context, candidates
                ),
                temperature=0.1,
                max_tokens=700,
            )
            parsed = self._parse_json(raw)
            return BrainExplanation(
                summary=str(parsed.get("summary") or fallback.summary),
                fit_reasons=[str(x) for x in parsed.get("fit_reasons", []) if isinstance(x, (str, int, float))],
                risks=[str(x) for x in parsed.get("risks", []) if isinstance(x, (str, int, float))],
                suggested_feedback_tags=[
                    str(x) for x in parsed.get("suggested_feedback_tags", [])
                    if str(x) in VALID_SUGGESTED_TAGS
                ],
                used_ollama=True,
            )
        except Exception as exc:
            logger.warning("BrainV2 reasoner fallback: %s", exc)
            return self._with_error(fallback, str(exc))

    def _get_client(self) -> Any:
        if self._ollama_client_factory is not None:
            return self._ollama_client_factory(None)
        try:
            from services.ollama_client import get_ollama_client

            return get_ollama_client()
        except Exception as exc:
            logger.debug("BrainV2 get_ollama_client failed: %s", exc)
            return None

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You explain DJ video edit matches for PB Studio. Return JSON only: "
            "{\"summary\": str, \"fit_reasons\": [str], \"risks\": [str], "
            "\"suggested_feedback_tags\": [str]}. Use these tags only: "
            + ", ".join(sorted(VALID_SUGGESTED_TAGS))
        )

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any]:
        text = str(raw).strip()
        if "```json" in text:
            start = text.index("```json") + len("```json")
            end = text.index("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.index("```") + len("```")
            end = text.index("```", start)
            text = text[start:end].strip()
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("Ollama response JSON must be object")
        return data

    @staticmethod
    def _with_error(base: BrainExplanation, error: str) -> BrainExplanation:
        return BrainExplanation(
            summary=base.summary,
            fit_reasons=list(base.fit_reasons),
            risks=list(base.risks),
            suggested_feedback_tags=list(base.suggested_feedback_tags),
            used_ollama=False,
            error=error,
        )

    @staticmethod
    def _fallback(audio_context: dict[str, Any], clip_context: dict[str, Any]) -> BrainExplanation:
        section = audio_context.get("section") or audio_context.get("section_type") or "unknown section"
        role = clip_context.get("role") or "unknown role"
        motion = clip_context.get("motion") or clip_context.get("motion_score")
        mood = clip_context.get("mood") or clip_context.get("mood_refined")
        reasons = [f"Audio section {section} matched with clip role {role}."]
        if motion is not None:
            reasons.append(f"Clip motion score is {motion}.")
        if mood is not None:
            reasons.append(f"Clip mood is {mood}.")
        return BrainExplanation(
            summary=f"{section}: deterministic match explanation for {role}.",
            fit_reasons=reasons,
            risks=["Ollama explanation unavailable; using stored scores only."],
            suggested_feedback_tags=["fits"],
            used_ollama=False,
        )
