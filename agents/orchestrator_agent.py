"""
Orchestrator Agent — Zentrale Steuerung des Multi-Agenten-Systems.

Entscheidet anhand der Benutzeranfrage, ob:
1. Ein spezialisierter Agent (Vision, Audio, Editor) zuständig ist
2. Direkt das Action-Registry angesprochen wird (Fuzzy-Matching)
3. Das Text-LLM für freie Antworten gefragt wird

Verwaltet das Modell-Swapping über den ModelManager.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agents.base_agent import BaseAgent
from agents.vision_agent import VisionAgent
from agents.audio_agent import AudioAgent
from agents.editor_agent import EditorAgent

logger = logging.getLogger(__name__)

# Generische Analyse-Keywords (treffen auf mehrere Domänen zu)
ANALYZE_ALL_KEYWORDS = [
    "analysiere alle", "analyze all", "alle analysieren",
    "alle files", "all files", "importiert", "imported",
    "alles analysieren", "alles prüfen",
]


class OrchestratorAgent(BaseAgent):
    """Orchestrator: Verteilt Anfragen an spezialisierte Agenten oder das Action-Registry.

    Architektur:
        User-Input → Orchestrator → [VisionAgent | AudioAgent | EditorAgent | ActionRegistry | LLM]
    """

    name = "orchestrator"
    domain = "orchestrator"

    def __init__(self):
        super().__init__()
        self._agents: list[BaseAgent] = [
            VisionAgent(),
            AudioAgent(),
            EditorAgent(),
        ]
        self._model_manager = None  # Wird vom LocalAgentService gesetzt

    @property
    def agents(self) -> list[BaseAgent]:
        return self._agents

    def set_model_manager(self, manager) -> None:
        """Setzt den ModelManager für Modell-Swapping."""
        self._model_manager = manager

    def can_handle(self, user_text: str) -> float:
        # Der Orchestrator kann alles handeln
        return 1.0

    def _detect_analyze_all(self, user_text: str) -> bool:
        """Erkennt 'analysiere alle importierten Files' (auch mit Tippfehlern)."""
        from thefuzz import fuzz

        text_lower = user_text.lower()

        # Direkte Keyword-Suche
        for kw in ANALYZE_ALL_KEYWORDS:
            if kw in text_lower:
                return True

        # Fuzzy-Check auf die gesamte Eingabe gegen bekannte Muster
        patterns = [
            "analysiere alle files die importiert sind",
            "analysiere alle importierten dateien",
            "analyze all imported files",
        ]
        for pattern in patterns:
            if fuzz.token_sort_ratio(text_lower, pattern) > 60:
                return True

        return False

    def _get_imported_ids(self) -> dict[str, list[int]]:
        """Holt alle importierten Audio-Track- und Video-Clip-IDs aus der Datenbank."""
        try:
            from sqlalchemy.orm import Session
            from database import engine, AudioTrack, VideoClip

            with Session(engine) as session:
                audio_ids = [t.id for t in session.query(AudioTrack).all()]
                video_ids = [c.id for c in session.query(VideoClip).all()]

            return {"audio_track_ids": audio_ids, "video_clip_ids": video_ids}
        except Exception as e:
            logger.error("Fehler beim Laden der importierten IDs: %s", e)
            return {"audio_track_ids": [], "video_clip_ids": []}

    def _handle_analyze_all(self) -> dict[str, Any]:
        """Analysiert alle importierten Audio- und Video-Dateien."""
        from services.action_registry import action_registry

        ids = self._get_imported_ids()
        results = []
        errors = []

        for track_id in ids["audio_track_ids"]:
            try:
                res = action_registry.execute("analyze_audio", {"track_id": track_id})
                results.append({
                    "action": "analyze_audio",
                    "params": {"track_id": track_id},
                    "result": res,
                    "error": None,
                })
            except Exception as e:
                errors.append(f"analyze_audio(track_id={track_id}): {e}")
                results.append({
                    "action": "analyze_audio",
                    "params": {"track_id": track_id},
                    "result": None,
                    "error": str(e),
                })

        for clip_id in ids["video_clip_ids"]:
            try:
                res = action_registry.execute("analyze_video", {"clip_id": clip_id})
                results.append({
                    "action": "analyze_video",
                    "params": {"clip_id": clip_id},
                    "result": res,
                    "error": None,
                })
            except Exception as e:
                errors.append(f"analyze_video(clip_id={clip_id}): {e}")
                results.append({
                    "action": "analyze_video",
                    "params": {"clip_id": clip_id},
                    "result": None,
                    "error": str(e),
                })

        total = len(ids["audio_track_ids"]) + len(ids["video_clip_ids"])
        return {
            "agent": self.name,
            "action": "multi",
            "params": {},
            "result": None,
            "message": f"Analyse gestartet: {len(ids['audio_track_ids'])} Audio-Tracks, "
                       f"{len(ids['video_clip_ids'])} Video-Clips ({total} gesamt).",
            "error": " | ".join(errors) if errors else None,
            "actions": results,
        }

    def _route_to_agent(self, user_text: str) -> BaseAgent | None:
        """Findet den besten spezialisierten Agenten für die Anfrage."""
        best_agent = None
        best_score = 0.0

        for agent in self._agents:
            score = agent.can_handle(user_text)
            if score > best_score:
                best_score = score
                best_agent = agent

        if best_score >= 0.3:
            logger.info(
                "Routing an '%s' (Score: %.2f)",
                best_agent.name, best_score,
            )
            return best_agent

        return None

    def _route_to_registry(self, user_text: str) -> dict[str, Any] | None:
        """Versucht direkt über das Action-Registry (mit Fuzzy) zu routen."""
        from services.action_registry import action_registry

        # Extrahiere mögliche Aktionsnamen aus dem Text
        # Suche nach Wörtern die wie Aktionsnamen aussehen
        words = re.findall(r'[a-z_]+', user_text.lower())

        for word in words:
            if len(word) < 4:
                continue
            matched_name, score = action_registry.fuzzy_match(word)
            if matched_name and score >= 60:
                logger.info("Registry-Routing: '%s' → '%s' (Score: %d%%)", word, matched_name, score)
                # Extrahiere Parameter (IDs) aus dem Text
                params = {}
                numbers = re.findall(r'\d+', user_text)
                action_def = action_registry.get(matched_name)
                if action_def and numbers:
                    # Versuche die erste Zahl dem ersten required-Parameter zuzuordnen
                    schema = action_def.param_schema
                    required = schema.get("required", [])
                    props = schema.get("properties", {})
                    for i, req in enumerate(required):
                        if i < len(numbers) and props.get(req, {}).get("type") == "integer":
                            params[req] = int(numbers[i])

                try:
                    result = action_registry.execute(matched_name, params)
                    return {
                        "agent": self.name,
                        "action": matched_name,
                        "params": params,
                        "result": result,
                        "message": None,
                        "error": None,
                    }
                except Exception as e:
                    return {
                        "agent": self.name,
                        "action": matched_name,
                        "params": params,
                        "result": None,
                        "message": None,
                        "error": str(e),
                    }

        return None

    def process(self, user_text: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Hauptlogik: Routet die Anfrage an den besten Handler.

        Routing-Priorität:
        1. "Analysiere alle" → Spezialbehandlung (alle importierten Dateien)
        2. Spezialisierter Agent (höchster can_handle-Score)
        3. Direktes Action-Registry (Fuzzy-Matching auf Aktionsnamen)
        4. Fallback: Weiterleitung an das Text-LLM
        """
        logger.info("Orchestrator empfängt: '%s'", user_text[:100])

        # 1. "Analysiere alle" Spezialfall
        if self._detect_analyze_all(user_text):
            logger.info("Erkannt: 'Analysiere alle importierten Dateien'")
            return self._handle_analyze_all()

        # 2. Spezialisierter Agent
        agent = self._route_to_agent(user_text)
        if agent is not None:
            # ModelManager: Agent-Modell laden falls nötig
            if self._model_manager and agent.model_id:
                self._model_manager.ensure_loaded(agent.model_id)
            return agent.process(user_text, context)

        # 3. Direktes Action-Registry (Fuzzy)
        registry_result = self._route_to_registry(user_text)
        if registry_result is not None:
            return registry_result

        # 4. Fallback: Kein passender Agent/Action gefunden
        return {
            "agent": self.name,
            "action": "none",
            "params": {},
            "result": None,
            "message": f"Ich konnte keinen passenden Agenten oder Aktion finden für: '{user_text[:80]}'. "
                       "Verfügbare Agenten: Vision, Audio, Editor.",
            "error": None,
        }
