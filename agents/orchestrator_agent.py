"""
Orchestrator Agent — Zentrale Steuerung des Multi-Agenten-Systems.

Entscheidet anhand der Benutzeranfrage, ob:
1. Ein spezialisierter Agent (Vision, Audio, Editor) zuständig ist
2. Direkt das Action-Registry angesprochen wird (Fuzzy-Matching)
3. Das Text-LLM für freie Antworten gefragt wird

NEU: Multi-Step-Analyse — Kann Prompts wie "Was passiert in Video 1
und was wird gesagt?" in parallele Agent-Aufrufe zerlegen:
  1. Vision-Agent → Szenen beschreiben
  2. Audio-Agent → Text transkribieren
  3. Ergebnisse zusammenfassen

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

# Multi-Step Keywords: Sowohl Bild ALS AUCH Ton
MULTI_STEP_KEYWORDS = [
    ("bild", "ton"), ("video", "audio"), ("visual", "audio"),
    ("sehen", "gesagt"), ("sieht", "hört"), ("visuell", "akustisch"),
    ("szene", "sprache"), ("zeigt", "sagt"), ("passiert", "gesagt"),
    ("inhalt", "transkri"), ("bild und ton", None),
    ("video und audio", None), ("analysiere bild und ton", None),
]


class OrchestratorAgent(BaseAgent):
    """Orchestrator: Verteilt Anfragen an spezialisierte Agenten oder das Action-Registry.

    Architektur:
        User-Input → Orchestrator → [VisionAgent | AudioAgent | EditorAgent | Multi-Step | ActionRegistry | LLM]
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

    def _detect_multi_step(self, user_text: str) -> bool:
        """Erkennt ob eine Multi-Step-Analyse (Vision + Audio) gewünscht ist."""
        text_lower = user_text.lower()

        for pair in MULTI_STEP_KEYWORDS:
            if pair[1] is None:
                # Direktes Keyword
                if pair[0] in text_lower:
                    return True
            else:
                # Beide Keywords müssen vorkommen
                if pair[0] in text_lower and pair[1] in text_lower:
                    return True

        return False

    def _extract_id_from_text(self, user_text: str) -> int | None:
        """Extrahiert eine ID (Zahl) aus dem Text."""
        numbers = re.findall(r'\d+', user_text)
        if numbers:
            return int(numbers[0])
        return None

    def _handle_multi_step(self, user_text: str) -> dict[str, Any]:
        """Führt eine Multi-Step-Analyse durch: Vision + Audio auf dasselbe Medien-Objekt.

        Schritt 1: Vision-Agent → Visuelle Szenenanalyse
        Schritt 2: Audio-Agent → Transkription
        Schritt 3: Ergebnisse zusammenfassen
        """
        from services.action_registry import action_registry

        media_id = self._extract_id_from_text(user_text)
        results = []
        errors = []

        logger.info("Multi-Step-Analyse gestartet für ID: %s", media_id)

        # Schritt 1: Vision-Agent (Moondream2)
        try:
            vision_params = {}
            if media_id is not None:
                vision_params["clip_id"] = media_id

            vision_result = action_registry.execute("analyze_video_content", vision_params)
            results.append({
                "agent": "vision",
                "action": "analyze_video_content",
                "params": vision_params,
                "result": vision_result,
                "error": None,
            })
        except Exception as e:
            error_msg = f"Vision-Analyse fehlgeschlagen: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            results.append({
                "agent": "vision",
                "action": "analyze_video_content",
                "params": {"clip_id": media_id},
                "result": None,
                "error": error_msg,
            })

        # Schritt 2: Audio-Agent (faster-whisper)
        # Versuche zuerst mit track_id, dann mit file_path des VideoClips
        try:
            audio_params = {}
            if media_id is not None:
                # Versuche file_path des VideoClips für Whisper
                try:
                    from sqlalchemy.orm import Session as SASession
                    from database import engine, VideoClip
                    with SASession(engine) as session:
                        clip = session.get(VideoClip, media_id)
                        if clip and clip.file_path:
                            audio_params["file_path"] = clip.file_path
                except Exception:
                    audio_params["track_id"] = media_id

            if not audio_params:
                audio_params["track_id"] = media_id

            audio_result = action_registry.execute("transcribe_audio", audio_params)
            results.append({
                "agent": "audio",
                "action": "transcribe_audio",
                "params": audio_params,
                "result": audio_result,
                "error": None,
            })
        except Exception as e:
            error_msg = f"Audio-Transkription fehlgeschlagen: {e}"
            logger.error(error_msg)
            errors.append(error_msg)
            results.append({
                "agent": "audio",
                "action": "transcribe_audio",
                "params": audio_params,
                "result": None,
                "error": error_msg,
            })

        # Schritt 3: Zusammenfassung erstellen
        summary_parts = []

        # Vision-Zusammenfassung
        vision_data = results[0].get("result") if results else None
        if vision_data and not vision_data.get("error"):
            scenes = vision_data.get("scenes", [])
            if scenes:
                summary_parts.append(f"🎬 VISUELLE ANALYSE ({len(scenes)} Szenen):")
                for scene in scenes[:5]:  # Max 5 für Zusammenfassung
                    summary_parts.append(
                        f"  [{scene['timestamp_sec']}s] {scene['description'][:100]}"
                    )

        # Audio-Zusammenfassung
        audio_data = results[1].get("result") if len(results) > 1 else None
        if audio_data and not audio_data.get("error"):
            full_text = audio_data.get("full_text", "")
            lang = audio_data.get("language", "?")
            summary_parts.append(f"\n🎤 TRANSKRIPTION (Sprache: {lang}):")
            if full_text:
                summary_parts.append(f"  {full_text[:300]}")
            else:
                summary_parts.append("  (Kein gesprochener Text erkannt)")

        summary = "\n".join(summary_parts) if summary_parts else "Keine Ergebnisse."

        return {
            "agent": self.name,
            "action": "multi",
            "params": {"media_id": media_id},
            "result": None,
            "message": summary,
            "error": " | ".join(errors) if errors else None,
            "actions": results,
        }

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
        words = re.findall(r'[a-z_]+', user_text.lower())

        for word in words:
            if len(word) < 4:
                continue
            matched_name, score = action_registry.fuzzy_match(word)
            if matched_name and score >= 60:
                logger.info("Registry-Routing: '%s' → '%s' (Score: %d%%)", word, matched_name, score)
                params = {}
                numbers = re.findall(r'\d+', user_text)
                action_def = action_registry.get(matched_name)
                if action_def and numbers:
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
        2. Multi-Step-Analyse → Vision + Audio gleichzeitig
        3. Spezialisierter Agent (höchster can_handle-Score)
        4. Direktes Action-Registry (Fuzzy-Matching auf Aktionsnamen)
        5. Fallback: Weiterleitung an das Text-LLM
        """
        logger.info("Orchestrator empfängt: '%s'", user_text[:100])

        # 1. "Analysiere alle" Spezialfall
        if self._detect_analyze_all(user_text):
            logger.info("Erkannt: 'Analysiere alle importierten Dateien'")
            return self._handle_analyze_all()

        # 2. Multi-Step-Analyse (Vision + Audio)
        if self._detect_multi_step(user_text):
            logger.info("Erkannt: Multi-Step-Analyse (Vision + Audio)")
            return self._handle_multi_step(user_text)

        # 3. Spezialisierter Agent
        agent = self._route_to_agent(user_text)
        if agent is not None:
            # ModelManager: Agent-Modell laden falls nötig
            if self._model_manager and agent.model_id:
                self._model_manager.ensure_loaded(agent.model_id, "vision")
            return agent.process(user_text, context)

        # 4. Direktes Action-Registry (Fuzzy)
        registry_result = self._route_to_registry(user_text)
        if registry_result is not None:
            return registry_result

        # 5. Fallback: Kein passender Agent/Action gefunden
        return {
            "agent": self.name,
            "action": "none",
            "params": {},
            "result": None,
            "message": f"Ich konnte keinen passenden Agenten oder Aktion finden für: '{user_text[:80]}'. "
                       "Verfügbare Agenten: Vision (Szenen-KI), Audio (Transkription), Editor.",
            "error": None,
        }
