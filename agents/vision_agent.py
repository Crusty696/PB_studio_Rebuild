"""
Vision Agent — Spezialisiert auf Video- und Bildanalyse.

Zuständig für: analyze_video, Szenen-Erkennung, Frame-Analyse.
Kann ein eigenes Vision-Modell laden (z.B. CLIP, BLIP).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Schlüsselwörter, die auf Vision-Aufgaben hindeuten
VISION_KEYWORDS = [
    "video", "clip", "szene", "scene", "bild", "image", "frame",
    "visuell", "visual", "kamera", "camera", "auflösung", "resolution",
    "analyse video", "analyze video", "analysiere video",
]


class VisionAgent(BaseAgent):
    """Agent für Video- und Bildanalyse-Aufgaben.

    Routet intern an die passende Action-Registry-Aktion
    (z.B. analyze_video) und kann in Zukunft ein eigenes
    Vision-Modell (CLIP/BLIP) verwalten.
    """

    name = "vision"
    domain = "vision"
    model_id = None  # Wird gesetzt wenn ein Vision-Modell benötigt wird

    def __init__(self):
        super().__init__()
        self._pattern = re.compile(
            "|".join(re.escape(kw) for kw in VISION_KEYWORDS),
            re.IGNORECASE,
        )

    def can_handle(self, user_text: str) -> float:
        text_lower = user_text.lower()
        matches = self._pattern.findall(text_lower)
        if not matches:
            return 0.0
        # Mehr Matches = höhere Konfidenz, max 0.95
        return min(0.3 + 0.15 * len(matches), 0.95)

    def process(self, user_text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        from services.action_registry import action_registry

        logger.info("VisionAgent verarbeitet: %s", user_text[:80])

        result = {
            "agent": self.name,
            "action": "none",
            "params": {},
            "result": None,
            "message": None,
            "error": None,
        }

        # Versuche clip_id aus Kontext oder Text zu extrahieren
        clip_id = None
        if context:
            clip_id = context.get("clip_id")

        if clip_id is None:
            # Suche nach Zahlen im Text
            numbers = re.findall(r'\d+', user_text)
            if numbers:
                clip_id = int(numbers[0])

        if clip_id is not None:
            try:
                result["action"] = "analyze_video"
                result["params"] = {"clip_id": clip_id}
                result["result"] = action_registry.execute("analyze_video", {"clip_id": clip_id})
            except Exception as e:
                result["error"] = str(e)
        else:
            result["message"] = "Video-Analyse benötigt eine clip_id. Bitte einen Clip importieren."

        return result
