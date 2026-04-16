"""
Audio Agent — Spezialisiert auf Audio-Analyse und Stem-Separation.

Zuständig für: analyze_audio, separate_stems, detect_key, analyze_lufs,
classify_audio, analyze_spectral, detect_structure.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Schlüsselwörter, die auf Audio-Aufgaben hindeuten
AUDIO_KEYWORDS = [
    "audio", "musik", "music", "beat", "bpm", "stem", "vocals",
    "drums", "bass", "ton", "sound", "track", "song", "lied",
    "analyse audio", "analyze audio", "analysiere audio",
    "trennen", "separate", "separation",
    # DJ-Mix spezifisch
    "dj", "mix", "set", "transition", "drop", "breakdown",
    "buildup", "pacing", "energie", "energy", "makro",
]


class AudioAgent(BaseAgent):
    """Agent für Audio-Analyse und Stem-Separation.

    Erkennt automatisch ob Stem-Separation oder Analyse gewünscht ist.
    """

    name = "audio"
    domain = "audio"
    model_id = None

    def __init__(self):
        super().__init__()
        self._pattern = re.compile(
            "|".join(re.escape(kw) for kw in AUDIO_KEYWORDS),
            re.IGNORECASE,
        )

    def can_handle(self, user_text: str) -> float:
        text_lower = user_text.lower()
        matches = self._pattern.findall(text_lower)
        if not matches:
            return 0.0
        return min(0.3 + 0.15 * len(matches), 0.95)

    def process(self, user_text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        from services.action_registry import action_registry

        logger.info("AudioAgent verarbeitet: %s", user_text[:80])

        result = {
            "agent": self.name,
            "action": "none",
            "params": {},
            "result": None,
            "message": None,
            "error": None,
        }

        text_lower = user_text.lower()

        # Stem-Separation oder Audio-Analyse
        is_stem = any(kw in text_lower for kw in [
            "stem", "trennen", "separate", "separation", "vocals", "drums"
        ])

        track_id = None
        if context:
            track_id = context.get("track_id") or context.get("extracted_id")
        if track_id is None:
            numbers = re.findall(r'\d+', user_text)
            if numbers:
                track_id = int(numbers[0])

        if is_stem:
            # Stem-Separation: track_id=None → Batch-Modus (alle Audios)
            try:
                params = {"track_id": track_id} if track_id is not None else {}
                result["action"] = "separate_stems"
                result["params"] = params
                result["result"] = action_registry.execute("separate_stems", params)
            except (KeyError, ValueError, RuntimeError, OSError) as e:
                result["error"] = str(e)
        elif track_id is not None:
            try:
                result["action"] = "analyze_audio"
                result["params"] = {"track_id": track_id}
                result["result"] = action_registry.execute("analyze_audio", {"track_id": track_id})
            except (KeyError, ValueError, RuntimeError, OSError) as e:
                result["error"] = str(e)
        else:
            result["message"] = "Audio-Analyse benötigt eine track_id. Bitte einen Track importieren."

        return result
