"""
Audio Agent — Spezialisiert auf Audio-Analyse, Stem-Separation und Transkription.

Zuständig für: analyze_audio, separate_stems, transcribe_audio (faster-whisper).

Transkription nutzt faster-whisper über den ModelManager:
- Modell-Größe: 'base' (Standard) für RAM-Effizienz
- Gibt Zeitstempel zurück
- Unterstützt Audio- und Video-Dateien
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
    "transkri", "transcri", "speech", "sprache", "gesagt",
    "untertitel", "subtitle", "whisper",
    # DJ-Mix spezifisch
    "dj", "mix", "set", "transition", "drop", "breakdown",
    "buildup", "pacing", "energie", "energy", "makro",
]


class AudioAgent(BaseAgent):
    """Agent für Audio-Analyse, Stem-Separation und Transkription.

    Erkennt automatisch ob Transkription oder Analyse gewünscht ist.
    Nutzt den ModelManager für VRAM-sicheres Laden von faster-whisper.
    """

    name = "audio"
    domain = "audio"
    model_id = None  # Dynamisch: whisper oder keins

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

    def _is_transcription(self, text_lower: str) -> bool:
        """Erkennt ob eine Transkription gewünscht ist."""
        transcription_keywords = [
            "transkri", "transcri", "speech", "sprache", "gesagt",
            "text aus", "untertitel", "subtitle", "whisper",
            "was wird gesagt", "was sagt", "gesprochene",
        ]
        return any(kw in text_lower for kw in transcription_keywords)

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

        # Transkriptions-Erkennung
        if self._is_transcription(text_lower):
            # Suche nach file_path oder track_id
            track_id = None
            file_path = None
            if context:
                track_id = context.get("track_id") or context.get("extracted_id")
                file_path = context.get("file_path")

            if track_id is None:
                numbers = re.findall(r'\d+', user_text)
                if numbers:
                    track_id = int(numbers[0])

            if track_id is not None or file_path is not None:
                try:
                    params = {}
                    if file_path:
                        params["file_path"] = file_path
                    elif track_id is not None:
                        params["track_id"] = track_id
                    result["action"] = "transcribe_audio"
                    result["params"] = params
                    result["result"] = action_registry.execute("transcribe_audio", params)
                except (ValueError, RuntimeError, OSError) as e:
                    result["error"] = str(e)
            else:
                result["message"] = "Transkription benötigt eine track_id oder file_path."
            return result

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
            except (ValueError, RuntimeError, OSError) as e:
                result["error"] = str(e)
        elif track_id is not None:
            try:
                result["action"] = "analyze_audio"
                result["params"] = {"track_id": track_id}
                result["result"] = action_registry.execute("analyze_audio", {"track_id": track_id})
            except (ValueError, RuntimeError, OSError) as e:
                result["error"] = str(e)
        else:
            result["message"] = "Audio-Analyse benötigt eine track_id. Bitte einen Track importieren."

        return result
