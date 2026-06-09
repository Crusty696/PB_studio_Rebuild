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
from services.ollama_service import OllamaService

logger = logging.getLogger(__name__)

# B-243: Whitelist nur lese-/abfragender Tools fuer den LLM-Fallback.
# Trigger-Tools (Worker-Spawns), destruktive Aktionen und auto_edit/export
# sind ausgeschlossen — Brain darf Daten lesen, aber keine Pipelines
# eigenmaechtig starten.
# B-245 + B-246: describe_video_clip + describe_set_overview ergaenzt.
_BRAIN_SAFE_TOOLS: tuple[str, ...] = (
    "summarize_project",
    "describe_audio_track",
    "describe_video_clip",       # B-245
    "describe_set_overview",     # B-246 Phase 1
    "match_clips_to_segment",    # B-246 Phase 2 — Cross-Modal SigLIP
    "explain_clip",
    "suggest_pacing",
    "search_video",
    "search_knowledge",
    "model_status",
    "list_actions",
)

_DIRECT_READ_TOOL_MESSAGES: frozenset[str] = frozenset({
    "summarize_project",
    "describe_audio_track",
    "describe_video_clip",
    "describe_set_overview",
})

# B-243: Tool-Use-aware System-Prompt. Im Tool-Loop ersetzt dieser
# den generischen _GENERAL_SYSTEM_PROMPT — der LLM weiss damit
# welche Tools er rufen soll und dass er KEINE Zahlen halluzinieren darf.
_TOOL_USE_SYSTEM_PROMPT = """\
Du bist der KI-Assistent von PB Studio, einem professionellen Tool fuer
DJ-Video-Produktion. Antworte praezise, hilfreich und auf Deutsch.

Du hast Zugriff auf die Projekt-Datenbank ueber Tool-Calls. Nutze die
Tools wenn die Anfrage konkrete Daten braucht — halluziniere keine
Zahlen, BPM-Werte, Drop-Zeitstempel oder Track-Namen.

Tool-Wahl-Hinweise:
- "Was ist importiert?" / "Projekt-Stand"   -> summarize_project
- "Beschreibe Track X" / "Wann sind Drops"  -> describe_audio_track
- "Was ist auf Video X" / "Clip-Inhalt"     -> explain_clip
- "Wie schneiden?" / "Pacing fuer Track X"  -> suggest_pacing
- "Finde Clips wie ..." / Semantische Suche -> search_video / search_knowledge

Bei offenen, mehrteiligen Fragen: rufe mehrere Tools nacheinander.
Wenn keine Tool-Daten noetig sind: antworte direkt mit Text.
"""

# System-Prompt für die LLM-basierte Intent-Klassifizierung (AP-5)
_CLASSIFY_SYSTEM_PROMPT = """\
Du bist ein Router in PB Studio, einem DJ-Video-Editor.
Klassifiziere die Anfrage in GENAU EINE dieser Kategorien:

- "pacing": Auto-Edit, Schnitte zur Musik, Beat-Sync, BPM, Pacing-Strategie, Auto-Edit
- "vision": Video-Inhalt analysieren, Szenen beschreiben, visuelle Analyse, Moondream
- "audio": Stems trennen, Audio-Analyse, BPM-Erkennung, Key-Erkennung
- "editor": Timeline bearbeiten, Clips verschieben, Export, Render
- "action": Direkte App-Aktion (Proxy erstellen, Datei importieren, Einstellungen)
- "general": Allgemeine Frage, kein konkreter App-Befehl

Antworte NUR mit dem Kategorie-Namen (einem Wort, lowercase). Kein anderer Text.
"""

# System-Prompt für allgemeine Fragen (Fallback)
_GENERAL_SYSTEM_PROMPT = """\
Du bist der KI-Assistent von PB Studio, einem professionellen Tool für DJ-Video-Produktion.
Beantworte Fragen präzise, hilfreich und auf Deutsch.
Wenn du Pacing-Aufgaben oder Auto-Edits erklärst, sei fachlich fundiert (BPM, Phrasen-Schnitt, Energie-Level).
Du hast Zugriff auf spezialisierte Agenten für Vision, Audio und Pacing.
"""

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

# B-468: Zustands-aendernde (nicht-destruktive) Actions duerfen im
# _route_to_registry-Loose-Pfad NICHT von einem schwachen Einzelwort-Fuzzy-Match
# ausgeloest werden. "zeige Projektstatus" fuzzy-matchte "save_project" mit 64%
# und fuehrte einen Write aus. Destruktive Actions sind separat geschuetzt
# (DESTRUCTIVE_FUZZY_THRESHOLD im Registry); dies erweitert dieselbe Idee auf
# Writes — sie matchen weiter bei quasi-exaktem Score. create_proxy/separate_stems
# werden bereits frueher ueber COMPOUND_ACTION_MAP abgefangen.
WRITE_ACTION_FUZZY_THRESHOLD = 90
WRITE_ACTIONS: frozenset[str] = frozenset({
    "save_project", "save_project_as", "create_project", "open_project",
    "import_file", "convert_videos", "auto_edit", "add_to_timeline",
    "set_clip_effects", "move_clip", "apply_style_preset", "add_anchor",
    "sync_anchors", "learn_anchor", "auto_ducking", "rl_feedback",
    "undo_timeline", "redo_timeline", "create_proxy",
})

# B-468: Read-Intent-Verben. Eine Lese-Anfrage nach dem Projektstatus soll zur
# Read-Action summarize_project gehen, nicht per Fuzzy zu einer Write-Action.
READ_INTENT_KEYWORDS = (
    "zeige", "zeig ", "zeig'", "show", "anzeige", "anzeigen",
    "wie ist", "wie steht", "gib mir", "was ist der",
)
PROJECT_MENTION_KEYWORDS = (
    "projektstatus", "projekt", "project", "ueberblick", "überblick", "overview",
)


class OrchestratorAgent(BaseAgent):
    """Orchestrator: Verteilt Anfragen an spezialisierte Agenten oder das Action-Registry.

    Architektur:
        User-Input → Orchestrator → [VisionAgent | AudioAgent | EditorAgent | Multi-Step | ActionRegistry | LLM]
    """

    name = "orchestrator"
    domain = "orchestrator"

    def __init__(self, agents: list[BaseAgent] | None = None):
        """Initialisiert den Orchestrator.

        Args:
            agents: Liste von spezialisierten Agenten. Falls None, wird die
                   Default-Liste verwendet. P2-FIX: Dependency Injection für Testbarkeit.
        """
        super().__init__()
        self._agents: list[BaseAgent] = agents or [
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
        try:
            from thefuzz import fuzz
        except ImportError:
            # P3-FIX: Log warning when fuzzy matching is unavailable
            logger.warning("thefuzz not available - fuzzy matching disabled for analyze-all detection")
            return False  # Fuzzy-Matching nicht verfuegbar

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

    # B-131: Anchored ID-Regex. Verlangt expliziten Keyword-Praefix
    # ("Track 5", "Audio 3", "Clip 12") — verhindert dass nackte Zahlen
    # wie "140 BPM" oder "4 Beats" als track_id missinterpretiert werden.
    _ID_KEYWORD_RE = re.compile(
        r'\b(?:track|audio|video|clip|set|projekt|project)\s*(\d+)',
        re.IGNORECASE,
    )

    def _extract_id_from_text(self, user_text: str) -> int | None:
        """Extrahiert eine ID (Zahl) aus dem Text — nur mit Keyword-Anker.

        B-131 Fix: ``\\d+``-greedy-Match wuerde "BPM 140" als track_id=140
        interpretieren (silent misroute). Anchored-Regex verlangt einen
        expliziten Praefix ("Track 5", "Audio 3", ...). Bare Zahlen werden
        ignoriert — User muss dann explizit kontextualisieren oder den
        Track UI-seitig auswaehlen.
        """
        match = self._ID_KEYWORD_RE.search(user_text)
        if match:
            return int(match.group(1))
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
        except (KeyError, ValueError, RuntimeError, OSError) as e:
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

        # Schritt 2: Zusammenfassung erstellen
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
        """Holt alle importierten Audio-Track- und Video-Clip-IDs aus der Datenbank.

        B-083 Fix: Tuple-Query statt ORM-Hydration. Frueher hydrierten zwei
        Full-Table-Scans bis zu 5000+5000 ORM-Objekte mit allen
        ``lazy='joined'``-Relationships (B-090) — fuer eine reine
        ID-Liste. Jetzt nur SELECT id, kein Hydrate.
        """
        try:
            from database import nullpool_session, AudioTrack, VideoClip

            with nullpool_session() as session:
                audio_ids = [
                    row[0] for row in session.query(AudioTrack.id)
                    .filter(AudioTrack.deleted_at.is_(None)).all()
                ]
                video_ids = [
                    row[0] for row in session.query(VideoClip.id)
                    .filter(VideoClip.deleted_at.is_(None)).all()
                ]

            return {"audio_track_ids": audio_ids, "video_clip_ids": video_ids}
        except Exception as e:  # broad catch intentional — SQLAlchemy query can raise many error types
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
            except (KeyError, ValueError, RuntimeError, OSError) as e:
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
            except (KeyError, ValueError, RuntimeError, OSError) as e:
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
            except (KeyError, ValueError, RuntimeError, OSError) as e:
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

    def _chat_with_tools_loop(self, user_text: str, max_iters: int = 3) -> str | None:
        """B-243: LLM-Fallback mit Tool-Use-Loop und DB-Kontext-Injection.

        Statt einfach ``OllamaService.chat()`` mit nacktem User-Text aufzurufen,
        passiert hier:

        1. ``summarize_project`` wird vorab als Context in den System-Prompt geschrieben
        2. ``OllamaClient.chat_with_tools`` mit Whitelist sicherer Read-Tools
        3. Tool-Use-Loop bis max_iters: bei tool_calls -> execute -> tool-result
           als role="tool"-message ans LLM zurueck -> naechste Iteration
        4. Endet entweder mit Text-Antwort oder ``None`` (Caller fallback'd)

        Returns:
            Final-Text-Antwort des LLM oder ``None`` wenn Tool-Use nicht moeglich
            (Modell ohne Tool-Support, Ollama down, Max-Iters ohne Final-Text).
        """
        import json
        from services.ollama_client import get_ollama_client, OllamaError
        from services.action_registry import action_registry

        svc = OllamaService.get()
        if not svc.is_ready:
            return None

        model = svc.get_default_model()
        if not model:
            return None

        oc = get_ollama_client()
        if not oc.supports_tools(model):
            logger.info(
                "Tool-Use-Loop: Modell '%s' unterstuetzt keine Tools — Fallback auf chat()",
                model,
            )
            return None

        tool_defs = action_registry.build_tool_definitions(names=list(_BRAIN_SAFE_TOOLS))
        if not tool_defs:
            return None

        # System-Prompt + DB-Kontext (summarize_project)
        logger.info("Tool-Use-Loop: starte mit model=%s, %d tools", model, len(tool_defs))
        system_content = _TOOL_USE_SYSTEM_PROMPT
        try:
            logger.info("Tool-Use-Loop: rufe summarize_project fuer DB-Kontext")
            proj = action_registry.execute("summarize_project", {})
            if isinstance(proj, dict) and proj.get("status") == "ok":
                system_content += "\n\nAktueller Projekt-Stand:\n" + proj.get("message", "")
                logger.info("Tool-Use-Loop: DB-Kontext injiziert (%d chars)", len(system_content))
        except Exception as e:  # broad catch — context-injection darf nicht den ganzen Pfad kippen
            logger.warning("Tool-Use-Loop: summarize_project im Setup fehlgeschlagen: %s", e)

        messages: list[dict] = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_text},
        ]

        for iter_idx in range(max_iters):
            logger.info("Tool-Use-Loop Iter %d/%d: chat_with_tools call beginnt", iter_idx + 1, max_iters)
            try:
                result = oc.chat_with_tools(
                    model=model,
                    user_message=user_text,  # ignoriert wenn messages gesetzt
                    tools=tool_defs,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1024,
                )
                logger.info(
                    "Tool-Use-Loop Iter %d: chat_with_tools zurueck, type=%s, tool_calls=%d",
                    iter_idx + 1, result.get("type"), len(result.get("tool_calls") or []),
                )
            except OllamaError as e:
                logger.warning("Tool-Use-Loop Iter %d OllamaError: %s", iter_idx, e)
                return None
            except Exception as e:  # broad catch — Tool-Use ist Best-Effort
                logger.warning("Tool-Use-Loop Iter %d unerwarteter Fehler: %s", iter_idx, e)
                return None

            if result.get("type") == "text":
                content = (result.get("content") or "").strip()
                if content:
                    logger.info(
                        "Tool-Use-Loop: Final-Antwort nach %d Iteration(en).", iter_idx + 1
                    )
                    return content
                return None

            tool_calls = result.get("tool_calls") or []
            if not tool_calls:
                return (result.get("content") or "").strip() or None

            # Assistant-Message mit tool_calls + Tool-Results anhaengen
            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": tool_calls,
            })
            direct_message: str | None = None
            for tc in tool_calls:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                tool_args = fn.get("arguments", {}) or {}

                # Sicherheit: nur Whitelist-Tools, auch wenn das LLM was anderes vorschlaegt
                if tool_name not in _BRAIN_SAFE_TOOLS:
                    tool_content = (
                        f"Tool '{tool_name}' nicht erlaubt. Verfuegbar: "
                        f"{', '.join(_BRAIN_SAFE_TOOLS)}"
                    )
                    logger.warning(
                        "Tool-Use-Loop: LLM hat '%s' angefragt (nicht in Whitelist).",
                        tool_name,
                    )
                else:
                    try:
                        logger.info("Tool-Use-Loop: execute tool=%s, args=%s", tool_name, tool_args)
                        tool_result = action_registry.execute(tool_name, tool_args)
                        if (
                            len(tool_calls) == 1
                            and tool_name in _DIRECT_READ_TOOL_MESSAGES
                            and isinstance(tool_result, dict)
                            and tool_result.get("status") == "ok"
                            and tool_result.get("message")
                        ):
                            direct_message = str(tool_result["message"])
                        tool_content = json.dumps(
                            tool_result, default=str, ensure_ascii=False
                        )
                        logger.info("Tool-Use-Loop: tool=%s OK, result-len=%d", tool_name, len(tool_content))
                    except Exception as e:  # broad catch — Tool-Fehler durchreichen, nicht crashen
                        tool_content = f"Fehler beim Aufruf von {tool_name}: {e}"
                        logger.warning(
                            "Tool-Use-Loop: '%s' fehlgeschlagen: %s", tool_name, e
                        )

                # Tool-Result truncaten damit der Context nicht explodiert
                if len(tool_content) > 4000:
                    tool_content = tool_content[:4000] + "...[truncated]"

                messages.append({
                    "role": "tool",
                    "content": tool_content,
                })

            if direct_message:
                logger.info(
                    "Tool-Use-Loop: direkte Tool-Antwort ohne LLM-Rewrite (%d chars).",
                    len(direct_message),
                )
                return direct_message

        logger.warning("Tool-Use-Loop: Max-Iterationen (%d) erreicht ohne Final-Text.", max_iters)
        return None

    def _llm_classify_intent(self, user_text: str) -> str | None:
        """Nutzt Ollama zur Intent-Klassifizierung wenn Keyword-Routing unentschieden ist (AP-5).

        Gibt eine Kategorie zurück: "pacing" | "vision" | "audio" | "editor" | "action" | "general"
        Gibt None zurück wenn Ollama nicht verfügbar.
        """
        svc = OllamaService.get()
        if not svc.is_ready:
            return None

        try:
            result = svc.chat(
                messages=[
                    {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_text}
                ],
            )
            
            category = result.strip().lower().split()[0] if result.strip() else ""
            valid_categories = {"pacing", "vision", "audio", "editor", "action", "general"}
            if category in valid_categories:
                logger.info("LLM-Klassifizierung: '%s' → '%s'", user_text[:50], category)
                return category
        except Exception as e:
            logger.debug("LLM-Klassifizierung fehlgeschlagen: %s", e)

        return None

    def _route_to_agent(self, user_text: str) -> BaseAgent | None:
        """Findet den besten spezialisierten Agenten für die Anfrage.

        Strategie (AP-5):
        1. Score-basiertes Routing (schnell, kein LLM)
        2. Wenn Score zu niedrig (unentschieden): LLM-Klassifizierung als Tiebreaker
        """
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

        # AP-5: LLM-Klassifizierung als Tiebreaker wenn Score zu niedrig
        if best_score >= 0.1:
            category = self._llm_classify_intent(user_text)
            if category:
                domain_map = {
                    "pacing": "pacing",
                    "vision": "vision",
                    "audio": "audio",
                    "editor": "editor",
                }
                target_domain = domain_map.get(category)
                if target_domain:
                    for agent in self._agents:
                        if agent.domain == target_domain:
                            logger.info(
                                "LLM-Routing an '%s' (Kategorie: '%s')",
                                agent.name, category,
                            )
                            return agent

        return None

    def _handle_project_status_read(self, user_text: str) -> dict[str, Any] | None:
        """B-468: Routet Read-Intent-Projektstatus-Anfragen zu summarize_project.

        Eine Lese-Anfrage wie "zeige Projektstatus" darf nicht per Fuzzy auf die
        Write-Action save_project laufen. Wenn ein Read-Verb UND ein Projekt-Bezug
        vorliegt, wird die nicht-mutierende summarize_project-Action ausgefuehrt.
        Liefert None, wenn keine Projektstatus-Lese-Absicht erkennbar ist.
        """
        from services.action_registry import action_registry

        text_lower = user_text.lower()
        has_read = any(kw in text_lower for kw in READ_INTENT_KEYWORDS)
        mentions_project = any(kw in text_lower for kw in PROJECT_MENTION_KEYWORDS)
        if not (has_read and mentions_project):
            return None

        logger.info(
            "B-468: Read-Intent-Projektstatus erkannt → summarize_project ('%s')",
            user_text[:60],
        )
        try:
            result = action_registry.execute("summarize_project", {})
            return {
                "agent": self.name,
                "action": "summarize_project",
                "params": {},
                "result": result,
                "message": None,
                "error": None,
            }
        except (KeyError, ValueError, RuntimeError, OSError) as e:
            return {
                "agent": self.name,
                "action": "summarize_project",
                "params": {},
                "result": None,
                "message": None,
                "error": str(e),
            }

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
                # B-468: Write-Actions brauchen in diesem Loose-Pfad einen
                # quasi-exakten Score. Sonst loest ein schwacher Fuzzy-Treffer
                # (z.B. "projektstatus" -> "save_project" 64%) ungewollt einen
                # Write aus. Destruktive Actions sind im Registry separat gesperrt.
                if matched_name in WRITE_ACTIONS and score < WRITE_ACTION_FUZZY_THRESHOLD:
                    logger.info(
                        "B-468: Loose-Write-Match abgelehnt: '%s' → '%s' "
                        "(Score %d%% < %d%%)",
                        word, matched_name, score, WRITE_ACTION_FUZZY_THRESHOLD,
                    )
                    continue
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
            except (KeyError, ValueError, RuntimeError, OSError) as e:
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
            except (KeyError, ValueError, RuntimeError, OSError) as e:
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

        FIX B-1001: Alle Fehler werden geloggt und in der Error-Response zurückgegeben
        """
        logger.info("Orchestrator empfängt: '%s'", user_text[:100])

        try:
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

            # B-246: Cross-Modal-Fragen ("Welche Clips passen zum Drop von Track 1?")
            # muessen vor AudioAgent/PacingAgent abgefangen werden. Sonst gewinnt
            # oft AudioAgent wegen "Track" + "Drop" und startet analyze_audio.
            cross_modal = self._handle_cross_modal_clip_match(user_text)
            if cross_modal is not None:
                return cross_modal

            # 3. Spezialisierter Agent
            agent = self._route_to_agent(user_text)
            if agent is not None:
                # ModelManager: Agent-Modell laden falls nötig (mit korrektem model_type)
                if self._model_manager and agent.model_id:
                    # model_type aus der Agent-Domain ableiten
                    model_type_map = {"vision": "vision"}
                    model_type = model_type_map.get(agent.domain, "transformers")
                    self._model_manager.ensure_loaded(agent.model_id, model_type)
                # Context aufbauen und an den Agenten weiterreichen
                agent_context = self._build_context(user_text, context)
                return agent.process(user_text, agent_context)

            # B-468: Read-Intent-Projektstatus-Anfragen ("zeige Projektstatus")
            # gehen zur Read-Action summarize_project, nicht per Fuzzy zu einer
            # Write-Action wie save_project.
            status_read = self._handle_project_status_read(user_text)
            if status_read is not None:
                return status_read

            # 4. Direktes Action-Registry (Fuzzy)
            registry_result = self._route_to_registry(user_text)
            if registry_result is not None:
                return registry_result

            # 5. Fallback: Keine passender Agent/Action gefunden -> Ollama-Chat
            # B-243: Erst Tool-Use-Loop (mit DB-Kontext + Whitelist sicherer
            # Read-Tools); wenn der scheitert (Modell unterstuetzt keine Tools,
            # Ollama down, Max-Iters ohne Final-Text), Fallback auf einfachen
            # chat() ohne Tools.
            tool_response = self._chat_with_tools_loop(user_text)
            if tool_response:
                return {
                    "agent": self.name,
                    "action": "chat_with_tools",
                    "params": {"user_text": user_text},
                    "result": tool_response,
                    "message": tool_response,
                    "error": None,
                }

            svc = OllamaService.get()
            if svc.is_ready:
                llm_response = svc.chat(
                    messages=[
                        {"role": "system", "content": _GENERAL_SYSTEM_PROMPT},
                        {"role": "user", "content": user_text}
                    ],
                )
                return {
                    "agent": self.name,
                    "action": "chat",
                    "params": {"user_text": user_text},
                    "result": llm_response,
                    "message": llm_response,
                    "error": None,
                }

            return {
                "agent": self.name,
                "action": "none",
                "params": {},
                "result": None,
                "message": f"Ich konnte keinen passenden Agenten oder Aktion finden für: '{user_text[:80]}'. "
                           "Die KI-Engine (Ollama) ist zudem nicht aktiv.",
                "error": None,
            }
        except Exception as e:  # broad catch intentional — top-level orchestrator safety net
            # FIX B-1001: Fehler aus allen Agenten und Methoden loggen und zur UI schicken
            error_msg = f"Orchestrator-Fehler: {type(e).__name__}: {e}"
            logger.exception("Unerwarteter Fehler im Orchestrator-Agent")
            return {
                "agent": self.name,
                "action": "error",
                "params": {"user_text": user_text[:100]},
                "result": None,
                "message": f"Ein Fehler ist im Orchestrator aufgetreten: {str(e)[:200]}",
                "error": error_msg,
        }

    def _handle_cross_modal_clip_match(self, user_text: str) -> dict[str, Any] | None:
        """B-246: Route Audio-Segment+Video-Match-Fragen direkt zum Read/Search-Tool."""
        from agents.pacing_agent import PacingAgent
        from services.action_registry import action_registry

        text_lower = user_text.lower()
        if not PacingAgent._wants_cross_modal_clip_match(text_lower):
            return None

        params: dict[str, Any] = {
            "segment_label": PacingAgent._segment_label_from_text(text_lower),
            "top_n": 5,
            "max_segments": 10,
        }
        track_id = self._extract_id_from_text(user_text)
        if track_id is not None:
            params["track_id"] = track_id

        try:
            result = action_registry.execute("match_clips_to_segment", params)
            return {
                "agent": self.name,
                "action": "match_clips_to_segment",
                "params": params,
                "result": result,
                "message": result.get("message") if isinstance(result, dict) else None,
                "error": None,
            }
        except (KeyError, ValueError, RuntimeError, OSError) as e:
            return {
                "agent": self.name,
                "action": "match_clips_to_segment",
                "params": params,
                "result": None,
                "message": None,
                "error": str(e),
            }
