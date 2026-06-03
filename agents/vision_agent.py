"""
Vision Agent — Spezialisiert auf Video- und Bildanalyse mit KI.

Zuständig für:
- analyze_video: FFprobe-basierte Metadaten (bestehend)
- analyze_video_content: KI-basierte visuelle Szenenanalyse mit Moondream2

Moondream2 (vikhyatk/moondream2):
- Kleines, effizientes Vision-Language-Modell
- Extrahiert Frames aus Video und beschreibt visuelle Inhalte
- Läuft über den ModelManager (VRAM-geschützt)
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agents.base_agent import BaseAgent, extract_id_from_text

logger = logging.getLogger(__name__)

# Schlüsselwörter, die auf Vision-Aufgaben hindeuten
VISION_KEYWORDS = [
    "video", "clip", "szene", "scene", "bild", "image", "frame",
    "visuell", "visual", "kamera", "camera", "auflösung", "resolution",
    "analyse video", "analyze video", "analysiere video",
    "was passiert", "was ist zu sehen", "beschreibe", "describe",
    "inhalt", "content", "zeigt", "shows",
]


class VisionAgent(BaseAgent):
    """Agent für Video- und Bildanalyse mit KI (Moondream2).

    Unterscheidet zwischen:
    - Metadaten-Analyse (FFprobe) → analyze_video
    - KI-Inhaltsanalyse (Moondream2) → analyze_video_content
    """

    name = "vision"
    domain = "vision"
    # B-463 (2026-06-03): Vision laeuft jetzt out-of-process ueber Ollama
    # (VisionAnalysisService -> chat_vision). Kein HF-Modell mehr ueber den
    # ModelManager preloaden — model_id=None verhindert den crashenden
    # ensure_loaded("vikhyatk/moondream2","vision")-Preload im Orchestrator.
    model_id = None

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
        return min(0.3 + 0.15 * len(matches), 0.95)

    def _wants_content_analysis(self, text_lower: str) -> bool:
        """Erkennt ob KI-Inhaltsanalyse gewünscht ist (statt nur Metadaten)."""
        content_keywords = [
            "was ist auf", "was ist in",
            "was passiert", "was ist zu sehen", "beschreibe", "describe",
            "inhalt", "content", "zeigt", "shows", "szene",
            "visuell", "visual", "ki analyse", "ai analy",
            "was sieht man", "was zeigt", "analysiere video", "analyze video",
            "neu analys",
        ]
        return any(kw in text_lower for kw in content_keywords)

    def _wants_new_content_analysis(self, text_lower: str) -> bool:
        """True wenn der User explizit einen neuen Vision-Worker starten will."""
        trigger_keywords = [
            "analysiere", "analyze", "neu analys", "starte analyse",
            "ki analyse", "ai analy", "vision-analyse", "moondream",
        ]
        return any(kw in text_lower for kw in trigger_keywords)

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

        text_lower = user_text.lower()

        # Entscheide: Metadaten oder KI-Inhaltsanalyse
        wants_content = self._wants_content_analysis(text_lower)

        # Suche clip_id oder file_path
        clip_id = None
        file_path = None
        if context:
            clip_id = context.get("clip_id") or context.get("extracted_id")
            file_path = context.get("file_path")

        if clip_id is None:
            # B-131: anchored extraction.
            clip_id = extract_id_from_text(user_text)

        if wants_content:
            # B-245: Natuerliche Lesefragen ("Was ist auf Video 1?")
            # duerfen nicht blind einen asynchronen Worker starten. Erst
            # bestehende DB-Szenen lesen; nur explizite Analyse startet Worker.
            if clip_id is not None or file_path is not None:
                params = {}
                if file_path:
                    params["file_path"] = file_path
                elif clip_id is not None:
                    params["clip_id"] = clip_id
                try:
                    if clip_id is not None and not self._wants_new_content_analysis(text_lower):
                        result["action"] = "describe_video_clip"
                    else:
                        result["action"] = "analyze_video_content"
                    result["params"] = params
                    result["result"] = action_registry.execute(result["action"], params)
                except (KeyError, ValueError, RuntimeError, OSError) as e:
                    result["error"] = str(e)
            else:
                result["message"] = "Video-Inhaltsanalyse benötigt eine clip_id oder file_path."
        else:
            # Standard-Metadaten-Analyse (FFprobe)
            if clip_id is not None:
                try:
                    result["action"] = "analyze_video"
                    result["params"] = {"clip_id": clip_id}
                    result["result"] = action_registry.execute("analyze_video", {"clip_id": clip_id})
                except (KeyError, ValueError, RuntimeError, OSError) as e:
                    result["error"] = str(e)
            else:
                result["message"] = "Video-Analyse benötigt eine clip_id. Bitte einen Clip importieren."

        return result
