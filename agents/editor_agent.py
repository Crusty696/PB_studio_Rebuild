"""
Editor Agent — Spezialisiert auf Timeline-Bearbeitung und Export.

Zuständig für: auto_edit, export_timeline, import_file.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

EDITOR_KEYWORDS = [
    "edit", "schnitt", "cut", "timeline", "export", "render",
    "import", "importieren", "auto edit", "auto_edit",
    "exportieren", "rendern", "schneiden",
]


class EditorAgent(BaseAgent):
    """Agent für Timeline-Bearbeitung, Import und Export."""

    name = "editor"
    domain = "editor"
    model_id = None

    def __init__(self):
        super().__init__()
        self._pattern = re.compile(
            "|".join(re.escape(kw) for kw in EDITOR_KEYWORDS),
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

        logger.info("EditorAgent verarbeitet: %s", user_text[:80])

        result = {
            "agent": self.name,
            "action": "none",
            "params": {},
            "result": None,
            "message": None,
            "error": None,
        }

        text_lower = user_text.lower()

        if any(kw in text_lower for kw in ["export", "exportieren", "render", "rendern"]):
            project_id = None
            if context:
                project_id = context.get("project_id")
            if project_id is None:
                numbers = re.findall(r'\d+', user_text)
                if numbers:
                    project_id = int(numbers[0])
            if project_id is not None:
                try:
                    result["action"] = "export_timeline"
                    result["params"] = {"project_id": project_id}
                    result["result"] = action_registry.execute("export_timeline", {"project_id": project_id})
                except Exception as e:
                    result["error"] = str(e)
            else:
                result["message"] = "Export benötigt eine project_id."

        elif any(kw in text_lower for kw in ["auto edit", "auto_edit", "schnitt", "schneiden", "cut"]):
            track_id = None
            if context:
                track_id = context.get("audio_track_id")
            if track_id is None:
                numbers = re.findall(r'\d+', user_text)
                if numbers:
                    track_id = int(numbers[0])
            if track_id is not None:
                try:
                    result["action"] = "auto_edit"
                    result["params"] = {"audio_track_id": track_id}
                    result["result"] = action_registry.execute("auto_edit", {"audio_track_id": track_id})
                except Exception as e:
                    result["error"] = str(e)
            else:
                result["message"] = "Auto-Edit benötigt eine audio_track_id."

        else:
            result["message"] = "Editor-Agent: Kein spezifischer Befehl erkannt."

        return result
