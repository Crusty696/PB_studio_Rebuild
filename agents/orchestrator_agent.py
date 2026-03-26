"""
Orchestrator Agent — Zentrale Steuerung des Multi-Agenten-Systems.

Entscheidet anhand der Benutzeranfrage, ob:
1. Ein spezialisierter Agent (Vision, Audio, Editor) zuständig ist
2. Direkt das Action-Registry angesprochen wird (Fuzzy-Matching)
3. Das Text-LLM für freie Antworten gefragt wird

NEU: Multi-Step-Analyse — Kann Prompts wie "Was passiert in Video 1
und was wird gesagt?" in sequentielle Agent-Aufrufe zerlegen:
  1. Vision-Agent → Szenen beschreiben
  2. Audio-Agent → Text transkribieren
  3. Ergebnisse zusammenfassen

WICHTIG — DJ-MIX KONTEXT:
Wir verarbeiten mehrstündige DJ-Sets (1-4h), KEINE 3-Minuten-Tracks!
Die Stems (Drums, Bass, Vocals, Other) dienen dazu, Makro-Spannungsbögen
über Stunden zu erkennen: wechselnde Energie-Level, lange Übergänge (30-120s),
wechselnde BPM, Breakdowns und Drops. Das Video-Pacing wird an diese
gigantischen Bögen angepasst.

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
from agents.pacing_agent import PacingAgent

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

# Compound-Action Keywords: Mehrere unabhängige Aktionen in einem Satz
# Jeder Eintrag: (keywords_set, action_name, param_builder)
COMPOUND_ACTION_MAP = [
    {
        "keywords": ["proxy", "proxy-daten", "proxy daten", "proxy-video", "vorschau"],
        "action": "create_proxy",
    },
    {
        "keywords": ["stem", "stems", "stem-file", "stem files", "spuren trennen",
                      "vocals", "separation", "separier"],
        "action": "separate_stems",
    },
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
            PacingAgent(),   # Highest priority for pacing/auto-edit queries
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

        if media_id is None:
            return {
                "agent": self.name,
                "action": "multi",
                "params": {},
                "result": None,
                "message": "Multi-Step-Analyse benötigt eine Medien-ID. "
                           "Beispiel: 'Was passiert in Video 1 und was wird gesagt?'",
                "error": "Keine Medien-ID im Text gefunden.",
                "actions": [],
            }

        logger.info("Multi-Step-Analyse gestartet für ID: %s", media_id)

        # Schritt 1: Vision-Agent (Moondream2)
        try:
            vision_params = {"clip_id": media_id}

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
        audio_params: dict = {}
        try:
            if media_id is not None:
                # Versuche file_path des VideoClips für Whisper
                try:
                    from sqlalchemy.orm import Session as SASession
                    from database import engine, VideoClip
                    with SASession(engine) as session:
                        clip = session.get(VideoClip, media_id)
                        if clip and clip.file_path:
                            audio_params["file_path"] = clip.file_path
                except Exception as e:
                    # Bug-34 Fix: Fehler protokollieren statt zu verschlucken
                    logger.warning("Konnte VideoClip %d nicht laden für Transcription: %s", media_id, e)
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

    def _detect_compound_actions(self, user_text: str) -> list[str]:
        """Erkennt ob mehrere unabhängige Aktionen im Satz stecken (z.B. 'proxy + stems').

        Gibt Liste der erkannten Action-Namen zurück. Nur relevant wenn >= 2 Aktionen.
        """
        text_lower = user_text.lower()
        matched_actions = []

        for entry in COMPOUND_ACTION_MAP:
            for kw in entry["keywords"]:
                if kw in text_lower:
                    if entry["action"] not in matched_actions:
                        matched_actions.append(entry["action"])
                    break

        return matched_actions

    def _handle_compound_actions(self, action_names: list[str]) -> dict[str, Any]:
        """Führt mehrere erkannte Aktionen nacheinander aus (Batch-Modus)."""
        from services.action_registry import action_registry

        results = []
        errors = []

        for action_name in action_names:
            try:
                # Ohne Parameter → Batch-Modus (alle Medien)
                action_result = action_registry.execute(action_name, {})
                results.append({
                    "agent": self.name,
                    "action": action_name,
                    "params": {},
                    "result": action_result,
                    "error": None,
                })
            except Exception as e:
                error_msg = f"{action_name}: {e}"
                logger.error("Compound-Action fehlgeschlagen: %s", error_msg)
                errors.append(error_msg)
                results.append({
                    "agent": self.name,
                    "action": action_name,
                    "params": {},
                    "result": None,
                    "error": error_msg,
                })

        succeeded = sum(1 for r in results if r.get("error") is None)
        return {
            "agent": self.name,
            "action": "multi",
            "params": {},
            "result": None,
            "message": f"{succeeded}/{len(results)} Aktionen erfolgreich: {', '.join(action_names)}",
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
        """Versucht über das Action-Registry (mit Fuzzy) zu routen.

        Sammelt ALLE Matches und führt sie aus (Multi-Action-fähig).
        """
        from services.action_registry import action_registry

        # Extrahiere mögliche Aktionsnamen aus dem Text
        words = re.findall(r'[a-z_]+', user_text.lower())
        numbers = re.findall(r'\d+', user_text)

        matched_actions: list[tuple[str, dict]] = []
        seen_actions: set[str] = set()

        for word in words:
            if len(word) < 4:
                continue
            matched_name, score = action_registry.fuzzy_match(word)
            if matched_name and score >= 60 and matched_name not in seen_actions:
                seen_actions.add(matched_name)
                logger.info("Registry-Routing: '%s' → '%s' (Score: %d%%)", word, matched_name, score)

                params = {}
                action_def = action_registry.get(matched_name)
                if action_def and numbers:
                    schema = action_def.param_schema
                    required = schema.get("required", [])
                    props = schema.get("properties", {})
                    for i, req in enumerate(required):
                        if i < len(numbers) and props.get(req, {}).get("type") == "integer":
                            params[req] = int(numbers[i])

                matched_actions.append((matched_name, params))

        if not matched_actions:
            return None

        # Single action
        if len(matched_actions) == 1:
            name, params = matched_actions[0]
            try:
                result = action_registry.execute(name, params)
                return {
                    "agent": self.name,
                    "action": name,
                    "params": params,
                    "result": result,
                    "message": None,
                    "error": None,
                }
            except Exception as e:
                return {
                    "agent": self.name,
                    "action": name,
                    "params": params,
                    "result": None,
                    "message": None,
                    "error": str(e),
                }

        # Multi action
        results = []
        errors = []
        for name, params in matched_actions:
            try:
                res = action_registry.execute(name, params)
                results.append({
                    "action": name, "params": params, "result": res, "error": None,
                })
            except Exception as e:
                errors.append(f"{name}: {e}")
                results.append({
                    "action": name, "params": params, "result": None, "error": str(e),
                })

        action_names = [r["action"] for r in results]
        return {
            "agent": self.name,
            "action": "multi",
            "params": {},
            "result": None,
            "message": f"{len(results)} Aktionen via Registry: {', '.join(action_names)}",
            "error": " | ".join(errors) if errors else None,
            "actions": results,
        }

    def _build_context(self, user_text: str, context: dict[str, Any] | None) -> dict[str, Any]:
        """Baut einen vollstaendigen Context-Dict fuer Sub-Agenten.

        Kombiniert uebergebenen Context mit aus dem Text extrahierten IDs.
        """
        ctx = dict(context) if context else {}

        # ID aus Text extrahieren falls nicht im Context
        if "track_id" not in ctx and "clip_id" not in ctx:
            extracted_id = self._extract_id_from_text(user_text)
            if extracted_id is not None:
                ctx["extracted_id"] = extracted_id

        return ctx

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

        # 2b. Compound-Actions: Mehrere unabhängige Aktionen (z.B. "proxy + stems")
        compound_actions = self._detect_compound_actions(user_text)
        if len(compound_actions) >= 2:
            logger.info("Erkannt: Compound-Actions: %s", compound_actions)
            return self._handle_compound_actions(compound_actions)

        # 2c. Einzelne Compound-Action erkannt (z.B. nur "proxy" oder nur "stems")
        # → Direkt ausführen im Batch-Modus statt an Agent/LLM weiterzuleiten
        if len(compound_actions) == 1:
            action_name = compound_actions[0]
            logger.info("Erkannt: Einzel-Action via Compound-Map: %s", action_name)
            return self._handle_compound_actions(compound_actions)

        # 3. Spezialisierter Agent
        agent = self._route_to_agent(user_text)
        if agent is not None:
            # ModelManager: Agent-Modell laden falls nötig (mit korrektem model_type)
            if self._model_manager and agent.model_id:
                # model_type aus der Agent-Domain ableiten
                model_type_map = {"vision": "vision", "audio": "whisper"}
                model_type = model_type_map.get(agent.domain, "transformers")
                self._model_manager.ensure_loaded(agent.model_id, model_type)
            # Context aufbauen und an den Agenten weiterreichen
            agent_context = self._build_context(user_text, context)
            return agent.process(user_text, agent_context)

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
