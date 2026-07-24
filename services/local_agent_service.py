"""
Lokaler KI-Agent — Gemma 4 E4B via Ollama.

Laeuft 100% offline. Nutzt das ActionRegistry,
um App-Funktionen per natuerlicher Sprache auszufuehren.

Unterstuetzt Multi-Action: Die KI kann mehrere Aktionen als
JSON-Array zurueckgeben, wenn der User mehrere Dinge verlangt.
"""

import json
import logging
import threading
import time
from typing import Any

from services.action_registry import ActionRegistry, action_registry
from services.errors import PBStudioError

logger = logging.getLogger(__name__)

# B-239: Default-Modell wird jetzt live ueber OllamaService.get_default_model()
# resolved (Family-Match auf 'gemma4' in /api/tags). Hartcoded "gemma4:e4b"
# existierte nirgends als Tag und blockierte alle LLM-Calls.
# DEFAULT_MODEL_ID bleibt als Sentinel fuer Aufrufer die den ModelManager-
# Lookup verlangen (nur HuggingFace-Fallback-Pfad nutzt das noch).
DEFAULT_MODEL_ID = "gemma3:4b"

# Ollama-Einstellungen (werden von Settings-Dialog gesetzt)
OLLAMA_DEFAULT_URL = "http://localhost:11434"
OLLAMA_ENABLED_ENV = "PB_OLLAMA_ENABLED"   # "1" oder "0"
OLLAMA_URL_ENV = "PB_OLLAMA_URL"
OLLAMA_MODEL_ENV = "PB_OLLAMA_MODEL"

# B-434: Throttle fuer den defensiven Ollama-Reprobe (gecachtes _use_ollama=False).
_OLLAMA_REPROBE_INTERVAL_SEC = 30.0

SYSTEM_PROMPT_TEMPLATE = """\
Du bist der KI-Assistent von PB Studio, einer Video- und Audio-Produktionssoftware.
Du hast eine Doppelrolle:
1. AKTIONS-ASSISTENT: Du fuehrst Aktionen in der App aus.
2. LEAD QA TESTER: Du pruefst autonom die App-Qualitaet.

GRUNDREGEL: "Audio ist der Master, Video ist der Sklave."
Die Musik diktiert die Laenge der Schnitte. Das Video passt sich an.

STEMS (getrennte Audio-Spuren via Demucs):
- Vocals: Gesang/Sprache → fuer Auto-Ducking (Musik leiser bei Narration)
- Drums: Kick/Snare/HiHat → fuer beat-praezise Schnitte (Drum-Onsets = Cut-Trigger)
- Bass: Bassline/Sub → fuer Drop-Erkennung (RMS-Sprung im Bass = maximale Cut-Rate)
- Other: Synths/Pads/Gitarre → fuer Mood/Atmosphere-Matching
Die KI nutzt Einzelspuren statt der Summe fuer PRAEZISERE Pacing-Entscheidungen.
Drum-Stem → exakte Kick-Positionen. Bass-Stem → Drop-Zeitpunkte. Vocals → Ducking-Trigger.

PHD-LEVEL PACING-REGELN:
- S_eff = f(S_base, Energy, Reactivity, Breakdown, Curve, Motion)
- Hohe Energie (>0.7): S_eff ÷ speed_boost (max 1.9×)
- Bass-Drop: RMS vorher<0.2 nachher>0.7 → S_eff=1 fuer 16-32 Beats
- Vocal-Active: S_eff × 2 (visuelle Stabilitaet fuer Textverstaendnis)
- Motion-Match: combined = E×0.6 + M×0.4 → Skalierung der Cut-Rate
- Stem-Gewichte: Drums=0.40, Bass=0.30, Vocals=0.10, Other=0.20
- DJ-Set Sektionen: WARMUP→BUILDUP→DROP→BREAKDOWN→TRANSITION→COOLDOWN

QA-PRUEFPUNKTE (bei Tests automatisch pruefen):
- Ladebalken: Jeder Hintergrundprozess MUSS einen Fortschrittsbalken haben.
- Fenster: Keine schwebenden oder ueberlappenden Fenster erlaubt.
- Threading: UI darf waehrend KI-Berechnungen NICHT einfrieren.
- Pacing: Schnitte fallen NUR auf Beat-Timestamps.
- GPU: ModelManager entlaedt Modell VOR naechstem Load.
- Stems: Drum-Onset-Analyse VOR Pacing, Vocal-Erkennung VOR Ducking.

VERFÜGBARE AKTIONEN:
{actions_json}

REGELN:
1. Antworte IMMER mit reinem JSON. Kein Text davor oder danach.
2. Wenn der Benutzer EINE Aktion verlangt, antworte mit einem JSON-Objekt:
   {{"action": "<name>", "params": {{...}}}}
3. Wenn der Benutzer MEHRERE Aktionen verlangt, antworte mit einem JSON-Array:
   [{{"action": "<name1>", "params": {{...}}}}, {{"action": "<name2>", "params": {{...}}}}]
4. Wenn keine Aktion passt: {{"action": "none", "params": {{}}, "message": "<Antwort>"}}
5. Verwende nur Aktionen aus der obigen Liste.
6. Fülle die Parameter gemäß dem Schema der Aktion.
7. Bei mehreren Aktionen: Führe sie in logischer Reihenfolge auf.
8. Bei QA-Fragen: Pruefe anhand der QA-Pruefpunkte und melde Vertoesse."""

LOCAL_LLM_SYSTEM_PROMPT_MAX_CHARS = 1200

COMPACT_SYSTEM_PROMPT = """\
Du bist der lokale KI-Assistent von PB Studio.
Antworte kurz, deutsch und praktisch.

App-Kontext:
- PB Studio ist private Video-/Audio-Produktionssoftware.
- Audio ist Master, Video folgt Beat/Pacing.
- Bekannte App-Befehle wie analysiere, schneide, auto-edit und gpu status werden vor dem LLM direkt geroutet.

Regeln:
1. Wenn der User freie Hilfe will: antworte normal.
2. Wenn eine App-Aktion eindeutig ist: gib JSON {"action": "<name>", "params": {...}}.
3. Wenn keine Aktion passt: gib JSON {"action": "none", "params": {}, "message": "<Antwort>"}.
4. Erfinde keine Dateipfade, Modelle oder App-Zustaende.
5. Bei Unsicherheit: sage, was geprueft werden muss."""


class LocalAgentService:
    """Lokaler KI-Agent mit einem Small Language Model.

    Lädt das Modell lazy beim ersten Aufruf, um Startzeit zu sparen.
    Unterstützt Single- und Multi-Action-Ausgabe.

    Nutzt den zentralen Singleton-ModelManager für Ressourcen-Schutz:
    Nur EIN Modell gleichzeitig im RAM/VRAM.

    Enthält den OrchestratorAgent für intelligentes Routing.
    """

    def __init__(
        self,
        registry: ActionRegistry | None = None,
        model_id: str = DEFAULT_MODEL_ID,
        device: str | None = None,
        ollama_url: str | None = None,
        ollama_model: str | None = None,
        use_ollama: bool | None = None,
    ):
        self.registry = registry or action_registry
        self.model_id = model_id
        # GPU-ZWANG: Device wird lazy ermittelt (torch-Import blockiert 5-15s)
        self._device_override = device
        self._device_resolved = False
        self.device = device  # None = ModelManager waehlt automatisch (GPU-ZWANG)

        # Thread-Safety: RLock erlaubt rekursive Aufrufe im selben Thread
        self._lock = threading.RLock()

        # Multi-Agenten-Orchestrator
        self._orchestrator = None

        # --- AP-5: Konversationsgedächtnis ---
        # Lazy-Init: ConversationMemory wird erst beim ersten process_with_history()-Aufruf erstellt
        self._conversation_memory = None

        # --- Ollama-Konfiguration ---
        # Reihenfolge: Konstruktor-Argument > Env-Var > Auto-detect
        import os as _os
        self._ollama_url = (
            ollama_url
            or _os.environ.get(OLLAMA_URL_ENV, OLLAMA_DEFAULT_URL)
        )
        self._ollama_model: str | None = (
            ollama_model
            or _os.environ.get(OLLAMA_MODEL_ENV)
        )
        # use_ollama=None → Auto-detect beim ersten Aufruf
        if use_ollama is not None:
            self._use_ollama: bool | None = use_ollama
        elif _os.environ.get(OLLAMA_ENABLED_ENV) == "0":
            self._use_ollama = False
        else:
            self._use_ollama = None  # Auto-detect
        self._ollama_client = None  # Lazy init

        # B-434: Ein gecachtes _use_ollama=False aus dem Auto-Detect darf den Chat
        # nicht die ganze Session tot halten (Boot-Race: Ollama-Subprocess noch
        # nicht API-ready, Power-Event-Sturm). Wir reprobben throttled — AUSSER
        # Ollama wurde explizit deaktiviert (Konstruktor use_ollama=False oder ENV=0).
        self._ollama_disabled_explicit = (
            use_ollama is False or _os.environ.get(OLLAMA_ENABLED_ENV) == "0"
        )
        self._last_ollama_reprobe_ts = 0.0

        # B-082: Caches fuer System-Prompt-Bestandteile, damit nicht jeder
        # User-Turn 2 DB-Queries + 5000-Row-Hydrate triggert. TTLs:
        #  - base (Registry-Schema): bis Process-Ende, Registry-Aenderung
        #    aendert ihn nur durch Reboot.
        #  - media_context: 30s — kurz nach Ingest neu zu laden ist gewuenscht.
        #  - few_shots: 300s — Feedback-Listen aendern sich selten.
        self._sysprompt_base_cache: str | None = None
        self._sysprompt_media_cache: str | None = None
        self._sysprompt_media_ts: float = 0.0
        self._sysprompt_few_shots_cache: str | None = None
        self._sysprompt_few_shots_ts: float = 0.0

    def health_check(self) -> dict[str, Any]:
        """Schneller Boot-Time-Status-Check für die UI.

        B-180: liefert (ohne Modell zu laden) ob Ollama erreichbar ist und
        welches Modell konfiguriert ist. UI nutzt das Ergebnis um eine
        klare Banner-Message anzuzeigen statt den User raten zu lassen
        warum der Chat hängt.

        Returns:
            dict mit Keys: backend ('ollama'|'fallback'), ollama_reachable
            (bool), model (str|None), message (str für Anzeige).
        """
        # B-434: gecachtes False defensiv neu proben, damit der UI-Banner sich
        # erholt, sobald Ollama gesund ist.
        self._maybe_reprobe_ollama()
        auto_detected = False
        if self._use_ollama is None:
            auto_detected = True
            self._use_ollama = self._auto_detect_ollama()

        result = {
            "backend": "ollama" if self._use_ollama else "fallback",
            "ollama_reachable": False,
            "model": self._ollama_model,
            "message": "",
        }
        if not self._use_ollama:
            if auto_detected:
                result["message"] = (
                    f"Ollama nicht erreichbar an {self._ollama_url}. "
                    "Starte Ollama via 'ollama serve' oder pruefe die Settings. "
                    "Quick-Commands funktionieren weiterhin."
                )
            else:
                result["message"] = (
                    "Ollama deaktiviert — keine echten LLM-Antworten. "
                    "Quick-Commands ('analysiere', 'schneide', 'gpu status') "
                    "funktionieren weiterhin."
                )
            return result
        try:
            client = self._get_ollama_client()
            reachable = client.is_available()
            result["ollama_reachable"] = reachable
            if not reachable:
                result["message"] = (
                    f"Ollama nicht erreichbar an {self._ollama_url}. "
                    "Starte Ollama via 'ollama serve' oder Tray-App. "
                    "Quick-Commands funktionieren weiterhin."
                )
                return result
            if not self._ollama_model:
                # B-650: Auto-Select ueber den Task-Router (Vision-First-Modelle
                # sind fuer Text-Chat ausgeschlossen); Router-None faellt auf
                # das bisherige Bestmodell zurueck.
                from services.model_router import resolve_model_for_task
                result["model"] = (
                    resolve_model_for_task(client, "chat")
                    or client.get_best_available_model()
                )
                self._ollama_model = result["model"]
            if not result["model"]:
                result["message"] = (
                    "Ollama läuft, aber kein Modell installiert. "
                    "Tipp: 'ollama pull gemma3:4b' (3.3 GB)."
                )
                return result
            result["message"] = (
                f"Ollama bereit. Modell: {result['model']}."
            )
        except (ConnectionError, TimeoutError, OSError, RuntimeError) as e:
            result["message"] = f"Ollama-Health-Check fehlgeschlagen: {e}"
        return result

    def _get_orchestrator(self):
        """Lazy-Init des Orchestrators.

        B-129: gelockte Doppel-Check-Init verhindert zwei parallele
        OrchestratorAgent-Instanzen (eine wuerde verloren — leak + state-
        divergenz).
        """
        if self._orchestrator is None:
            with self._lock:
                if self._orchestrator is None:
                    from agents.orchestrator_agent import OrchestratorAgent
                    orch = OrchestratorAgent()
                    from services.model_manager import ModelManager
                    orch.set_model_manager(ModelManager())
                    self._orchestrator = orch
        return self._orchestrator

    # ------------------------------------------------------------------
    # Ollama-Backend
    # ------------------------------------------------------------------

    def _get_ollama_client(self):
        """Gibt den Ollama-Client zurück (lazy init).

        B-129: Doppel-Check-Lock — verhindert zwei parallele Client-
        Instanzen mit obsoleten Connection-Pools.
        """
        if self._ollama_client is None:
            with self._lock:
                if self._ollama_client is None:
                    self._ollama_client = self._make_ollama_client(self._ollama_url)
        return self._ollama_client

    def _make_ollama_client(self, url: str):
        """Erzeugt OllamaClient fuer eine URL; eigener Helper fuer Fallback-Tests."""
        from services.ollama_client import get_ollama_client
        return get_ollama_client(url)

    def _auto_detect_ollama(self) -> bool:
        """Prüft ob Ollama verfügbar ist und wählt das beste Modell.

        Returns:
            True wenn Ollama genutzt werden soll, False für HuggingFace-Fallback.
        """
        try:
            client = self._get_ollama_client()
            if not client.is_available():
                if self._ollama_url.rstrip("/") != OLLAMA_DEFAULT_URL:
                    local_client = self._make_ollama_client(OLLAMA_DEFAULT_URL)
                    if local_client.is_available():
                        logger.warning(
                            "LocalAgentService: konfigurierte Ollama-URL '%s' nicht erreichbar; "
                            "nutze lokalen Default '%s'.",
                            self._ollama_url,
                            OLLAMA_DEFAULT_URL,
                        )
                        self._ollama_url = OLLAMA_DEFAULT_URL
                        self._ollama_client = local_client
                        client = local_client
                    else:
                        logger.info("LocalAgentService: Ollama nicht verfügbar → HuggingFace-Fallback.")
                        return False
                else:
                    logger.info("LocalAgentService: Ollama nicht verfügbar → HuggingFace-Fallback.")
                    return False

            # Modell wählen falls noch nicht gesetzt
            # B-239: Erst OllamaService-Auto-Detect (matcht Gemma-4-Family
            # auch bei Community-Tags), dann Fallback auf RECOMMENDED_MODELS.
            if self._ollama_model and not client.model_exists(self._ollama_model):
                logger.warning(
                    "LocalAgentService: konfiguriertes Ollama-Modell '%s' nicht installiert; "
                    "waehle bestes verfuegbares Modell.",
                    self._ollama_model,
                )
                self._ollama_model = None

            if not self._ollama_model:
                try:
                    from services.ollama_service import OllamaService
                    self._ollama_model = OllamaService.get().get_default_model()
                except Exception as e:
                    logger.debug("OllamaService-Default-Lookup fehlgeschlagen: %s", e)
                if not self._ollama_model:
                    # B-650: Router statt blindem Bestmodell (Vision-First-
                    # Ausschluss fuer Text-Chat), Fallback bleibt erhalten.
                    from services.model_router import resolve_model_for_task
                    self._ollama_model = (
                        resolve_model_for_task(client, "chat")
                        or client.get_best_available_model()
                    )

            if not self._ollama_model:
                logger.warning(
                    "LocalAgentService: Ollama läuft, aber keine Modelle installiert. "
                    "Tipp: 'ollama pull gemma3:4b' (3.3 GB)"
                )
                return False

            version = client.get_version()
            logger.info(
                "LocalAgentService: Ollama verfügbar (v%s) — Modell: '%s'.",
                version, self._ollama_model,
            )
            return True
        except (ConnectionError, TimeoutError, OSError, RuntimeError) as e:
            logger.warning("LocalAgentService: Ollama-Check fehlgeschlagen: %s", e)
            return False

    def configure_ollama(
        self,
        url: str,
        model: str | None = None,
        enabled: bool = True,
    ) -> None:
        """Konfiguriert Ollama zur Laufzeit (z.B. aus Settings-Dialog).

        Args:
            url: Ollama-Server-URL (z.B. "http://localhost:11434")
            model: Modellname oder None für Auto-Select
            enabled: False deaktiviert Ollama komplett (HuggingFace-Fallback)
        """
        self._ollama_url = url
        self._ollama_model = model
        self._use_ollama = enabled if enabled else False
        self._ollama_client = None  # Client neu erstellen beim nächsten Zugriff
        logger.info(
            "LocalAgentService: Ollama neu konfiguriert — URL=%s, Modell=%s, Aktiv=%s",
            url, model, enabled,
        )

    def _generate_ollama(self, user_text: str, max_new_tokens: int = 512) -> str:
        """Erzeugt Modellantwort via Ollama-HTTP-API."""
        client = self._get_ollama_client()
        system_prompt = self._build_system_prompt(user_query=user_text)
        # B-650: KI-Chat meldet Modell + Aufgabe ans ModelStatusField
        # (Muster: pacing_strategist._generate).
        from services.model_router import emit_task_status
        emit_task_status("loading", self._ollama_model, "chat")
        try:
            result = client.chat(
                model=self._ollama_model,
                user_message=user_text,
                system_prompt=system_prompt,
                temperature=0.1,
                max_tokens=max_new_tokens,
            )
        except Exception:
            emit_task_status("error", self._ollama_model, "chat")
            raise
        emit_task_status("ready", self._ollama_model, "chat")
        return result

    def _generate_ollama_with_history(
        self, user_text: str, max_new_tokens: int = 512
    ) -> str:
        """Erzeugt Modellantwort via Ollama mit Konversationsgedächtnis (AP-5).

        Nutzt chat_with_history() statt chat(), damit der Kontext erhalten bleibt.
        """
        client = self._get_ollama_client()
        mem = self._get_conversation_memory()
        system_prompt = self._build_system_prompt(user_query=user_text)
        messages = mem.get_messages(system_prompt)
        # Aktuelle User-Nachricht anhängen
        messages.append({"role": "user", "content": user_text})
        from services.model_router import emit_task_status
        emit_task_status("loading", self._ollama_model, "chat")
        try:
            result = client.chat_with_history(
                model=self._ollama_model,
                messages=messages,
                temperature=0.1,
                max_tokens=max_new_tokens,
            )
        except Exception:
            emit_task_status("error", self._ollama_model, "chat")
            raise
        emit_task_status("ready", self._ollama_model, "chat")
        return result

    def _generate_ollama_with_tools(
        self, user_text: str, max_new_tokens: int = 512
    ) -> dict:
        """Erzeugt Modellantwort via Ollama Tool-Use / Function-Calling (AP-5).

        Übersetzt das ActionRegistry in Ollama-Tool-Definitionen und nutzt
        strukturiertes Function-Calling statt JSON-Freitext-Parsing.

        Returns:
            dict mit "type": "tool_calls" | "text" und entsprechenden Feldern
        """
        client = self._get_ollama_client()
        system_prompt = self._build_system_prompt(user_query=user_text)

        # ActionRegistry → Ollama Tool-Definitionen
        tools = self._registry_to_tools()

        # Konversationsgedächtnis einbinden
        mem = self._get_conversation_memory()
        messages = mem.get_messages(system_prompt)
        messages.append({"role": "user", "content": user_text})

        from services.model_router import emit_task_status
        emit_task_status("loading", self._ollama_model, "chat")
        try:
            result = client.chat_with_tools(
                model=self._ollama_model,
                user_message=user_text,
                tools=tools,
                messages=messages,
                temperature=0.1,
                max_tokens=max_new_tokens,
            )
        except Exception:
            emit_task_status("error", self._ollama_model, "chat")
            raise
        emit_task_status("ready", self._ollama_model, "chat")
        return result

    def _registry_to_tools(self) -> list[dict]:
        """Übersetzt das ActionRegistry in das Ollama-Tool-Format.

        Format: [{"type": "function", "function": {"name", "description", "parameters"}}]
        """
        tools = []
        for action_def in self.registry.list_all():
            tools.append({
                "type": "function",
                "function": {
                    "name": action_def.name,
                    "description": action_def.description or f"Aktion: {action_def.name}",
                    "parameters": action_def.param_schema or {
                        "type": "object",
                        "properties": {},
                        "required": [],
                    },
                },
            })
        return tools

    # ------------------------------------------------------------------
    # AP-5: Konversationsgedächtnis
    # ------------------------------------------------------------------

    def _get_conversation_memory(self):
        """Lazy-Init der ConversationMemory für die Default-Session.

        B-129: Doppel-Check-Lock — sonst wuerden zwei parallele Threads
        zwei separate ConversationMemory-Instanzen anlegen, jede mit
        eigener History → User sieht abgeschnittenen Dialog-Kontext.
        """
        if self._conversation_memory is None:
            with self._lock:
                if self._conversation_memory is None:
                    from services.conversation_memory import ConversationMemory
                    self._conversation_memory = ConversationMemory(
                        session_id="local_agent_default",
                        max_turns=8,
                    )
        return self._conversation_memory

    def clear_conversation_history(self) -> None:
        """Löscht die Konversationshistorie."""
        mem = self._get_conversation_memory()
        mem.clear()
        logger.info("LocalAgentService: Konversationshistorie gelöscht.")

    # ------------------------------------------------------------------
    # AP-5: Auto-Prompt-Optimization (Feedback)
    # ------------------------------------------------------------------

    def record_feedback(
        self,
        user_query: str,
        ai_response: str,
        rating: int,
        action_name: str | None = None,
        user_comment: str | None = None,
    ) -> None:
        """Speichert Nutzerfeedback auf eine KI-Antwort in der DB.

        Args:
            user_query: Die ursprüngliche Benutzeranfrage
            ai_response: Die KI-Antwort (als String oder JSON)
            rating: 1 = positiv, -1 = negativ, 0 = neutral
            action_name: Erkannte Aktion (falls bekannt)
            user_comment: Optionaler Freitext-Kommentar
        """
        try:
            from datetime import datetime, timezone  # B-130: timezone-aware
            from database import nullpool_session, AgentFeedback
            with nullpool_session() as session:
                feedback = AgentFeedback(
                    created_at=datetime.now(timezone.utc),
                    session_id="local_agent_default",
                    model_id=self._ollama_model or self.model_id,
                    backend="ollama" if self._use_ollama else "huggingface",
                    user_query=user_query[:2000],
                    ai_response=str(ai_response)[:4000],
                    action_name=action_name,
                    rating=rating,
                    user_comment=user_comment,
                )
                session.add(feedback)
                session.commit()
            logger.info(
                "LocalAgentService: Feedback gespeichert (Rating=%d, Aktion='%s').",
                rating, action_name or "?",
            )
        except Exception as e:  # broad catch intentional — SQLAlchemy commit can raise many error types
            logger.warning("LocalAgentService: Feedback konnte nicht gespeichert werden: %s", e)

    def _get_positive_few_shots(self, limit: int = 3) -> str:
        """Lädt positive Feedback-Beispiele für den System-Prompt (Few-Shot).

        Gibt einen String zurück, der direkt in den System-Prompt eingefügt wird.
        Enthält bis zu `limit` gut bewertete (User-Query → Aktion)-Paare.
        """
        try:
            from database import nullpool_session, AgentFeedback
            with nullpool_session() as session:
                good = (
                    session.query(AgentFeedback)
                    .filter(AgentFeedback.rating == 1)
                    .filter(AgentFeedback.action_name.isnot(None))
                    .order_by(AgentFeedback.created_at.desc())
                    .limit(limit)
                    .all()
                )
                if not good:
                    return ""
                lines = ["ERFOLGREICHE BEISPIELE (lerne daraus):"]
                for fb in good:
                    lines.append(
                        f'  User: "{fb.user_query[:80]}" → Aktion: "{fb.action_name}"'
                    )
                return "\n".join(lines)
        except Exception as e:  # broad catch intentional — SQLAlchemy query can raise many error types
            logger.debug("Few-Shot-Laden fehlgeschlagen: %s", e)
            return ""

    @property
    def is_loaded(self) -> bool:
        """Ollama ist 'geladen' wenn verfuegbar und Modell gewaehlt."""
        return self._use_ollama is True and self._ollama_model is not None

    def _build_system_prompt(self, user_query: str = "") -> str:
        """Baut den System-Prompt mit Aktionen + Medien-Kontext + Knowledge-Base + Few-Shots.

        B-082 Fix: Schritte mit DB-/IO-Last sind jetzt gecached:
        - base (Registry-Schema): persistent bis Process-Ende
        - media_context: TTL 30s (oder per invalidate_media_context)
        - few_shots (Feedback-DB-Query): TTL 300s
        Knowledge-Context bleibt query-spezifisch und wird bei jedem Call
        neu gebaut.
        """
        import time as _time

        with self._lock:
            if self._sysprompt_base_cache is None:
                base_prompt = SYSTEM_PROMPT_TEMPLATE.format(
                    actions_json=self.registry.get_schema_for_prompt()
                )
                if len(base_prompt) > LOCAL_LLM_SYSTEM_PROMPT_MAX_CHARS:
                    logger.info(
                        "LocalAgentService: Systemprompt von %d auf kompaktes GTX-1060-Budget begrenzt.",
                        len(base_prompt),
                    )
                    base_prompt = COMPACT_SYSTEM_PROMPT
                self._sysprompt_base_cache = base_prompt
            now = _time.monotonic()
            if (self._sysprompt_media_cache is None
                    or (now - self._sysprompt_media_ts) > 30.0):
                self._sysprompt_media_cache = self._build_media_context()
                self._sysprompt_media_ts = now
            if (self._sysprompt_few_shots_cache is None
                    or (now - self._sysprompt_few_shots_ts) > 300.0):
                self._sysprompt_few_shots_cache = self._get_positive_few_shots(limit=3)
                self._sysprompt_few_shots_ts = now

            parts: list[str] = [self._sysprompt_base_cache]
            if self._sysprompt_media_cache:
                parts.append(self._sysprompt_media_cache)

        # Knowledge-Context ausserhalb des Locks (File-IO, query-spezifisch)
        try:
            from services.knowledge_loader import get_knowledge_loader
            loader = get_knowledge_loader()
            knowledge_context = loader.build_context(query=user_query)
            if knowledge_context:
                parts.append(knowledge_context)
        except (ImportError, ValueError, RuntimeError, OSError) as e:
            logger.debug("Knowledge-Base konnte nicht geladen werden: %s", e)

        with self._lock:
            if self._sysprompt_few_shots_cache:
                parts.append(self._sysprompt_few_shots_cache)

        prompt = "\n\n".join(parts)
        if len(prompt) > LOCAL_LLM_SYSTEM_PROMPT_MAX_CHARS:
            logger.info(
                "LocalAgentService: finaler Systemprompt von %d auf %d Zeichen gekuerzt.",
                len(prompt),
                LOCAL_LLM_SYSTEM_PROMPT_MAX_CHARS,
            )
            prompt = (
                prompt[: LOCAL_LLM_SYSTEM_PROMPT_MAX_CHARS - 80].rstrip()
                + "\n\n[Systemprompt gekuerzt fuer lokale GTX-1060-Inference.]"
            )
        return prompt

    def invalidate_system_prompt_cache(self, kind: str = "all") -> None:
        """B-082: Cache-Invalidation Hook.

        ``kind`` ist eines von ``"all"``, ``"media"``, ``"few_shots"``,
        ``"base"``. Wird z.B. von Ingest-/Feedback-Workflows aufgerufen,
        damit der naechste LLM-Call den frischen Stand sieht.
        """
        with self._lock:
            if kind in ("all", "media"):
                self._sysprompt_media_cache = None
                self._sysprompt_media_ts = 0.0
            if kind in ("all", "few_shots"):
                self._sysprompt_few_shots_cache = None
                self._sysprompt_few_shots_ts = 0.0
            if kind in ("all", "base"):
                self._sysprompt_base_cache = None

    @staticmethod
    def _build_media_context() -> str:
        """Lädt alle importierten Medien aus der DB und formatiert sie als Kontext."""
        try:
            from services.ingest_service import get_all_audio, get_all_video

            audios = get_all_audio()
            videos = get_all_video()

            if not audios and not videos:
                return ""

            lines = ["AKTUELLER PROJEKT-STATUS:"]

            if videos:
                lines.append(f"Importierte Videos ({len(videos)}):")
                for v in videos:
                    res = f", Auflösung={v.get('resolution', '?')}" if v.get('resolution') else ""
                    lines.append(f"  - ID={v['id']}, Name=\"{v['title']}\", Pfad=\"{v['file_path']}\"{res}")

            if audios:
                lines.append(f"Importierte Audios ({len(audios)}):")
                for a in audios:
                    bpm = f", BPM={a['bpm']}" if a.get('bpm') else ""
                    stems = f", Stems={a['stems']}" if a.get('stems', '-') != '-' else ""
                    lines.append(f"  - ID={a['id']}, Name=\"{a['title']}\", Pfad=\"{a['file_path']}\"{bpm}{stems}")

            lines.append("")
            lines.append("WICHTIG: Nutze die oben genannten IDs als Parameter für Aktionen.")
            lines.append("Wenn der User 'alle' oder 'die Videos/Audios' sagt, lasse den ID-Parameter weg — die Aktion verarbeitet dann automatisch alle.")

            return "\n".join(lines)
        except Exception as e:  # broad catch intentional — DB query + string formatting errors
            logger.warning("Medien-Kontext konnte nicht geladen werden: %s", e)
            return ""

    def _build_messages(self, user_text: str) -> list[dict]:
        """Erstellt das Chat-Messages-Format für das Modell."""
        return [
            {"role": "system", "content": self._build_system_prompt(user_query=user_text)},
            {"role": "user", "content": user_text},
        ]

    def _maybe_reprobe_ollama(self) -> None:
        """B-434: Reprobt ein gecachtes ``_use_ollama=False`` (throttled).

        Wurde Ollama beim Boot faelschlich als nicht-erreichbar erkannt (Subprocess
        noch nicht API-ready, 0x000A-Power-Event-Sturm), blieb der Chat sonst die
        ganze Session tot, weil nur ``None`` neu geprobt wurde. Hier proben wir
        ``_use_ollama is False`` hoechstens alle ``_OLLAMA_REPROBE_INTERVAL_SEC``
        Sekunden erneut und schalten bei Erfolg auf den Ollama-Pfad zurueck.
        Explizit deaktiviertes Ollama wird NICHT reprobed.
        """
        if self._use_ollama is not False or self._ollama_disabled_explicit:
            return
        now = time.monotonic()
        if now - self._last_ollama_reprobe_ts < _OLLAMA_REPROBE_INTERVAL_SEC:
            return
        self._last_ollama_reprobe_ts = now
        if self._auto_detect_ollama():
            self._use_ollama = True
            logger.info("B-434: Ollama wieder erreichbar — Chat-Backend reaktiviert.")

    def _generate(self, user_text: str, max_new_tokens: int = 512) -> str:
        """Erzeugt die rohe Modellantwort via Ollama (Gemma 4 E4B)."""
        if self._use_ollama is None:
            self._use_ollama = self._auto_detect_ollama()
        else:
            # B-434: gecachtes False defensiv (throttled) neu proben.
            self._maybe_reprobe_ollama()

        if self._use_ollama and self._ollama_model:
            try:
                return self._generate_ollama(user_text, max_new_tokens)
            except (ConnectionError, TimeoutError, OSError, RuntimeError) as e:
                logger.warning("LocalAgentService: Ollama-Fehler: %s", e)

        return ("Der KI-Dienst (Ollama) ist aktuell nicht erreichbar. "
                "Bitte starte Ollama oder nutze die manuellen Funktionen.")

    @staticmethod
    def _extract_json(raw: str) -> list[dict]:
        """Extrahiert JSON aus der Modellantwort.

        Unterstützt:
        - Einzelnes JSON-Objekt → wird in Liste verpackt
        - JSON-Array von Objekten → wird direkt zurückgegeben
        - Beliebig tief verschachtelte JSON-Strukturen
        """
        # Versuche direktes Parsing
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
        except json.JSONDecodeError as e:
            logger.warning("Direct JSON parsing of AI response failed: %s", e)

        # Iteratives String-Scanning: Suche nach '[' oder '{' und versuche json.loads()
        for i, ch in enumerate(raw):
            if ch in ('[', '{'):
                try:
                    parsed = json.loads(raw[i:])
                    if isinstance(parsed, list) and all(isinstance(item, dict) for item in parsed):
                        return parsed
                    if isinstance(parsed, dict):
                        return [parsed]
                except json.JSONDecodeError:
                    # json.loads() konsumiert nur gültiges JSON vom Anfang,
                    # also weiter zum nächsten '[' or '{'
                    continue

        # Fallback: keine gültige Aktion erkannt
        return [{
            "action": "none",
            "params": {},
            "message": raw,
            "error": "Malformed action JSON",
        }]

    def _execute_single_action(self, parsed: dict) -> dict[str, Any]:
        """Führt eine einzelne geparste Aktion aus und gibt das Ergebnis zurück.

        Nutzt Fuzzy-Matching: Wenn die KI einen ungenauen Aktionsnamen liefert,
        wird automatisch die ähnlichste registrierte Aktion verwendet.
        """
        action_name = parsed.get("action", "none")
        params = parsed.get("params", {})

        result = {
            "action": action_name,
            "params": params,
            "result": None,
            "message": parsed.get("message"),
            "error": parsed.get("error"),
        }

        if action_name != "none":
            # Fuzzy-Auflösung: 'analyse_files' → 'analyze_audio' etc.
            action_def = self.registry.resolve(action_name)
            if action_def is None:
                result["error"] = f"Unbekannte Aktion: {action_name} (auch kein Fuzzy-Match)"
                result["action"] = "none"
            else:
                # Aktualisiere den Aktionsnamen auf den aufgelösten
                result["action"] = action_def.name
                try:
                    action_result = self.registry.execute(action_def.name, params)
                    if isinstance(action_result, dict) and action_result.get("error"):
                        result["error"] = f"Fehler bei '{action_def.name}': {action_result['error']}"
                    else:
                        result["result"] = action_result
                except (ValueError, RuntimeError, TypeError, OSError, PBStudioError) as e:
                    # B-685: PBStudioError (u.a. OllamaError/FFmpegError/DatabaseError)
                    # erbt direkt von Exception, nicht von RuntimeError/OSError. Ohne
                    # diesen Zweig entkam z.B. ein OllamaError aus dem synchronen
                    # ask_ai-Handler dem Tupel, riss den Multi-Action-Loop ab und
                    # verwarf ALLE Per-Aktion-Ergebnisse (statt strukturierter
                    # Per-Aktion-Fehlermeldung).
                    result["error"] = f"Fehler bei '{action_def.name}': {e}"

        return result

    def process(self, user_text: str, use_history: bool = True) -> dict[str, Any]:
        """Verarbeitet eine Benutzeranfrage über das Multi-Agenten-System.

        Routing-Reihenfolge (AP-5 erweitert):
        1. Orchestrator prüft, ob ein spezialisierter Agent zuständig ist
        2. Falls Ollama + Tool-Use-fähiges Modell: Function-Calling-Pfad
        3. Falls Ollama: Chat mit History (Multi-Turn-Dialog)
        4. Fallback: HuggingFace-Modell (Freitext-JSON-Parsing)
        5. Fuzzy-Matching korrigiert ungenaue Aktionsnamen

        Args:
            user_text: Benutzeranfrage
            use_history: Ob Konversationsgedächtnis genutzt werden soll (Standard: True)

        Rückgabe:
            {
                "action": str,                  # Name der Aktion oder "multi"
                "params": dict,                 # Parameter (bei single action)
                "result": Any,                  # Ergebnis (bei single action)
                "message": str | None,          # KI-Nachricht
                "error": str | None,            # Fehler
                "actions": list[dict] | None,   # Alle Ergebnisse (bei multi action)
            }
        """
        # Lazy Device-Resolution (torch-Import nur beim ersten Aufruf)
        if not self._device_resolved:
            self._device_resolved = True
            try:
                import torch
                cuda_available = torch.cuda.is_available()
                self.device = "cuda" if cuda_available else "cpu"
                if self._device_override and self._device_override != self.device and cuda_available:
                    logger.warning("GPU-ZWANG: Device '%s' → 'cuda' erzwungen", self._device_override)
            except ImportError:
                self.device = "cpu"

        response = {
            "action": "none",
            "params": {},
            "result": None,
            "message": None,
            "error": None,
            "actions": None,
        }

        try:
            # --- Phase 1: Orchestrator versucht direkte Zuordnung ---
            orchestrator = self._get_orchestrator()
            orch_result = orchestrator.process(user_text)

            # Wenn der Orchestrator eine Aktion gefunden hat (nicht "none"-Fallback)
            if orch_result.get("action") != "none":
                response.update(orch_result)
                # Konversationsgedächtnis aktualisieren
                if use_history:
                    answer = orch_result.get("message") or str(orch_result.get("result", "OK"))
                    self._get_conversation_memory().add_turn(user_text, answer[:500])
                return response

            # --- Phase 2: LLM-basierte Verarbeitung (Fallback) ---

            # Ollama-Status sicherstellen
            if self._use_ollama is None:
                self._use_ollama = self._auto_detect_ollama()

            # AP-5 Phase 2a: Tool-Use via Ollama (wenn Modell es unterstützt)
            if self._use_ollama and self._ollama_model:
                client = self._get_ollama_client()
                if client.supports_tools(self._ollama_model):
                    logger.debug(
                        "LocalAgentService: Tool-Use-Pfad für Modell '%s'.", self._ollama_model
                    )
                    try:
                        tool_result = self._generate_ollama_with_tools(user_text)
                        if tool_result["type"] == "tool_calls" and tool_result["tool_calls"]:
                            # Tool-Calls ausführen
                            calls = tool_result["tool_calls"]
                            if len(calls) == 1:
                                fn = calls[0]["function"]
                                single = self._execute_single_action({
                                    "action": fn["name"],
                                    "params": fn["arguments"],
                                })
                                response.update(single)
                                if use_history:
                                    answer = single.get("message") or str(single.get("result", ""))
                                    self._get_conversation_memory().add_turn(user_text, answer[:500])
                                return response
                            else:
                                # Multi-Tool-Call
                                response["action"] = "multi"
                                results = []
                                for call in calls:
                                    fn = call["function"]
                                    r = self._execute_single_action({
                                        "action": fn["name"],
                                        "params": fn["arguments"],
                                    })
                                    results.append(r)
                                response["actions"] = results
                                errors = [r["error"] for r in results if r.get("error")]
                                if errors:
                                    response["error"] = " | ".join(errors)
                                action_names = [r["action"] for r in results if r["action"] != "none"]
                                response["message"] = (
                                    f"{len(action_names)} Tool-Calls: {', '.join(action_names)}"
                                )
                                if use_history:
                                    self._get_conversation_memory().add_turn(
                                        user_text, response["message"][:500]
                                    )
                                return response
                        # Kein Tool-Call → Fallback zu Text-Antwort
                        if tool_result["content"]:
                            raw_output = tool_result["content"]
                            # Konversationsgedächtnis nach Text-Antwort aktualisieren
                            if use_history:
                                self._get_conversation_memory().add_turn(
                                    user_text, raw_output[:500]
                                )
                            parsed_list = self._extract_json(raw_output)
                            if len(parsed_list) == 1:
                                single = self._execute_single_action(parsed_list[0])
                                response.update(single)
                                return response
                    except Exception as e:
                        logger.warning(
                            "LocalAgentService: Tool-Use fehlgeschlagen → JSON-Fallback. Fehler: %s", e
                        )

            # AP-5 Phase 2b: Generierung mit Konversationsgedächtnis (Multi-Turn)
            raw_output: str
            if self._use_ollama and self._ollama_model and use_history:
                try:
                    raw_output = self._generate_ollama_with_history(user_text)
                except Exception as e:
                    logger.warning(
                        "LocalAgentService: History-Chat fehlgeschlagen → einfacher Ollama-Chat. Fehler: %s", e
                    )
                    raw_output = self._generate(user_text)
            else:
                raw_output = self._generate(user_text)

            logger.debug("KI-Rohantwort: %s", raw_output)
            parsed_list = self._extract_json(raw_output)

            if len(parsed_list) == 1:
                # Single Action (mit Fuzzy-Matching)
                single = self._execute_single_action(parsed_list[0])
                response.update(single)
                # History nach erfolgreicher Antwort aktualisieren
                if use_history:
                    answer = single.get("message") or str(single.get("result", raw_output[:200]))
                    self._get_conversation_memory().add_turn(user_text, answer[:500])
            else:
                # Multi Action
                response["action"] = "multi"
                results = []
                for parsed in parsed_list:
                    action_result = self._execute_single_action(parsed)
                    results.append(action_result)
                response["actions"] = results

                # Sammle Fehler
                errors = [r["error"] for r in results if r.get("error")]
                if errors:
                    response["error"] = " | ".join(errors)

                # Zusammenfassung
                action_names = [r["action"] for r in results if r["action"] != "none"]
                if action_names:
                    response["message"] = f"{len(action_names)} Aktionen ausgeführt: {', '.join(action_names)}"
                if use_history:
                    self._get_conversation_memory().add_turn(
                        user_text, response.get("message", raw_output[:200])
                    )

        except Exception as e:  # broad catch intentional — top-level process() safety net
            logger.exception("Fehler bei KI-Verarbeitung")
            response["error"] = str(e)

        return response

    def process_with_history(self, user_text: str) -> dict[str, Any]:
        """Alias für process() mit explizit aktiviertem Konversationsgedächtnis.

        Für die GUI-Integration: process_with_history("Analysiere Track 1").
        """
        return self.process(user_text, use_history=True)
