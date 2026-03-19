"""
Audio Agent — Spezialisiert auf Audio-Analyse und -Verarbeitung.

Zuständig für: analyze_audio, separate_stems, BPM-Erkennung.
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
]


class AudioAgent(BaseAgent):
    """Agent für Audio-Analyse und -Verarbeitung.

    Routet an analyze_audio, separate_stems etc.
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

        # Entscheide zwischen Stem-Separation und Audio-Analyse
        is_stem = any(kw in text_lower for kw in ["stem", "trennen", "separate", "separation", "vocals", "drums"])

        track_id = None
        if context:
            track_id = context.get("track_id")
        if track_id is None:
            numbers = re.findall(r'\d+', user_text)
            if numbers:
                track_id = int(numbers[0])

        if track_id is not None:
            action_name = "separate_stems" if is_stem else "analyze_audio"
            try:
                result["action"] = action_name
                result["params"] = {"track_id": track_id}
                result["result"] = action_registry.execute(action_name, {"track_id": track_id})
            except Exception as e:
                result["error"] = str(e)
        else:
            result["message"] = "Audio-Analyse benötigt eine track_id. Bitte einen Track importieren."

        return result
