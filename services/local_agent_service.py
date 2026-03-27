"""
Lokaler KI-Agent auf Basis eines Small Language Model (SLM).

Läuft 100% offline auf CPU/GPU. Nutzt das ActionRegistry,
um App-Funktionen per natürlicher Sprache auszuführen.

Unterstützt Multi-Action: Die KI kann mehrere Aktionen als
JSON-Array zurückgeben, wenn der User mehrere Dinge verlangt.

Nutzt den zentralen Singleton-ModelManager für Ressourcen-Schutz:
Nur EIN Modell darf gleichzeitig im RAM/VRAM liegen.
"""

import concurrent.futures as _cf
import json
import logging
import threading
from typing import Any

from services.action_registry import ActionRegistry, action_registry
from services.model_manager import ModelManager

logger = logging.getLogger(__name__)

# Standard-Modell: winzig, schnell, Instruction-tuned
DEFAULT_MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"

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
    ):
        self.registry = registry or action_registry
        self.model_id = model_id
        # GPU-ZWANG: Device wird lazy ermittelt (torch-Import blockiert 5-15s)
        self._device_override = device
        self._device_resolved = False
        self.device = device or "cpu"  # Platzhalter bis erster Aufruf

        # ModelManager wird LAZY initialisiert (spart ~11s Startup durch verzögerten torch-Import)
        self._model_manager = None

        self._tokenizer = None
        self._model = None
        self._pipe = None
        self._loaded = False

        # Thread-Safety: RLock erlaubt rekursive Aufrufe im selben Thread
        self._lock = threading.RLock()

        # Multi-Agenten-Orchestrator
        self._orchestrator = None

    def _get_orchestrator(self):
        """Lazy-Init des Orchestrators."""
        if self._orchestrator is None:
            from agents.orchestrator_agent import OrchestratorAgent
            self._orchestrator = OrchestratorAgent()
            self._orchestrator.set_model_manager(self.model_manager)
        return self._orchestrator

    @property
    def model_manager(self) -> ModelManager:
        """Lazy ModelManager — torch wird erst beim ersten Zugriff importiert."""
        if self._model_manager is None:
            self._model_manager = ModelManager(device=self.device)
        return self._model_manager

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load_model(self) -> None:
        """Lädt Modell und Tokenizer über den ModelManager."""
        with self._lock:
            if self._loaded:
                return

            logger.info("Lade lokales KI-Modell: %s auf %s ...", self.model_id, self.device)

            self._tokenizer, self._model, self._pipe = self.model_manager.load_transformers(
                self.model_id
            )
            self._loaded = True
            logger.info("KI-Modell geladen: %s", self.model_id)

    def unload_model(self) -> None:
        """Gibt GPU/RAM frei über den ModelManager."""
        with self._lock:
            self.model_manager.unload()
            self._pipe = None
            self._model = None
            self._tokenizer = None
            self._loaded = False
            logger.info("KI-Modell entladen.")

    def _build_system_prompt(self) -> str:
        """Baut den System-Prompt mit den aktuell registrierten Aktionen + Medien-Kontext."""
        base = SYSTEM_PROMPT_TEMPLATE.format(
            actions_json=self.registry.get_schema_for_prompt()
        )

        # --- Context Injection: Dem LLM die importierten Medien mitteilen ---
        media_context = self._build_media_context()
        if media_context:
            base += "\n\n" + media_context

        return base

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
        except Exception as e:
            logger.warning("Medien-Kontext konnte nicht geladen werden: %s", e)
            return ""

    def _build_messages(self, user_text: str) -> list[dict]:
        """Erstellt das Chat-Messages-Format für das Modell."""
        return [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": user_text},
        ]

    def _generate(self, user_text: str, max_new_tokens: int = 512) -> str:
        """Erzeugt die rohe Modellantwort."""
        # Stale-Reference-Schutz: ModelManager könnte extern entladen haben
        if not self._loaded or self._pipe is None or not self.model_manager.is_loaded:
            self._loaded = False
            self.load_model()

        messages = self._build_messages(user_text)

        # Nutze das Chat-Template des Tokenizers (Qwen, Llama, etc.)
        if hasattr(self._tokenizer, "apply_chat_template"):
            prompt_text = self._tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        else:
            # Fallback: manuelles Format
            prompt_text = (
                f"<|system|>\n{messages[0]['content']}\n"
                f"<|user|>\n{messages[1]['content']}\n"
                f"<|assistant|>\n"
            )

        with self._lock:
            with _cf.ThreadPoolExecutor(max_workers=1) as _pool:
                _future = _pool.submit(
                    self._pipe,
                    prompt_text,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    return_full_text=False,
                )
                try:
                    outputs = _future.result(timeout=60)
                except _cf.TimeoutError:
                    raise RuntimeError(
                        "LLM-Inference Timeout (60s) — Modell haengt oder zu langsam fuer diese Anfrage."
                    )

        return outputs[0]["generated_text"].strip()

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
        except json.JSONDecodeError:
            pass

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
                    # Versuche kürzere Substrings ab dieser Position nicht —
                    # json.loads() konsumiert nur gültiges JSON vom Anfang,
                    # also weiter zum nächsten '[' oder '{'
                    pass

        # Fallback: keine gültige Aktion erkannt
        return [{"action": "none", "params": {}, "message": raw}]

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
            "error": None,
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
                    result["result"] = self.registry.execute(action_def.name, params)
                except Exception as e:
                    result["error"] = f"Fehler bei '{action_def.name}': {e}"

        return result

    def process(self, user_text: str) -> dict[str, Any]:
        """Verarbeitet eine Benutzeranfrage über das Multi-Agenten-System.

        Routing-Reihenfolge:
        1. Orchestrator prüft, ob ein spezialisierter Agent zuständig ist
        2. Falls nicht, wird das LLM für JSON-Action-Parsing genutzt
        3. Fuzzy-Matching korrigiert ungenaue Aktionsnamen

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
                return response

            # --- Phase 2: LLM-basierte Verarbeitung (Fallback) ---
            raw_output = self._generate(user_text)
            logger.debug("KI-Rohantwort: %s", raw_output)

            parsed_list = self._extract_json(raw_output)

            if len(parsed_list) == 1:
                # Single Action (mit Fuzzy-Matching)
                single = self._execute_single_action(parsed_list[0])
                response.update(single)
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

        except Exception as e:
            logger.exception("Fehler bei KI-Verarbeitung")
            response["error"] = str(e)

        return response
