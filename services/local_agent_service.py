"""
Lokaler KI-Agent auf Basis eines Small Language Model (SLM).

Läuft 100% offline auf CPU/GPU. Nutzt das ActionRegistry,
um App-Funktionen per natürlicher Sprache auszuführen.

Unterstützt Multi-Action: Die KI kann mehrere Aktionen als
JSON-Array zurückgeben, wenn der User mehrere Dinge verlangt.

Enthält den ModelManager für Ressourcen-Schutz:
Nur EIN Modell darf gleichzeitig im RAM/VRAM liegen.
"""

import json
import logging
import re
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline

from services.action_registry import ActionRegistry, action_registry

logger = logging.getLogger(__name__)

# Standard-Modell: winzig, schnell, Instruction-tuned
DEFAULT_MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"


class ModelManager:
    """Verwaltet Modell-Ressourcen: Nur EIN Modell gleichzeitig im RAM/VRAM.

    Wenn ein neues Modell geladen werden soll, wird das aktuelle zuerst
    entladen. Verhindert OOM auf GPUs mit wenig VRAM (z.B. GTX 1060 6GB).
    """

    def __init__(self, device: str | None = None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._current_model_id: str | None = None
        self._model = None
        self._tokenizer = None
        self._pipe = None

    @property
    def current_model_id(self) -> str | None:
        return self._current_model_id

    @property
    def is_loaded(self) -> bool:
        return self._current_model_id is not None

    def unload(self) -> None:
        """Entlädt das aktuelle Modell und gibt GPU/RAM frei."""
        if self._current_model_id is None:
            return

        logger.info("ModelManager: Entlade '%s'...", self._current_model_id)
        self._pipe = None
        self._model = None
        self._tokenizer = None

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        old_id = self._current_model_id
        self._current_model_id = None
        logger.info("ModelManager: '%s' entladen. GPU-Cache geleert.", old_id)

    def load(self, model_id: str) -> tuple:
        """Lädt ein Modell. Entlädt vorher das aktuelle falls nötig.

        Returns:
            (tokenizer, model, pipeline)
        """
        if self._current_model_id == model_id:
            logger.info("ModelManager: '%s' bereits geladen.", model_id)
            return self._tokenizer, self._model, self._pipe

        # Altes Modell entladen
        if self._current_model_id is not None:
            self.unload()

        logger.info("ModelManager: Lade '%s' auf %s...", model_id, self.device)

        self._tokenizer = AutoTokenizer.from_pretrained(
            model_id, trust_remote_code=True,
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=torch.float32 if self.device == "cpu" else torch.float16,
            trust_remote_code=True,
        )
        self._model.to(self.device)
        self._model.eval()

        self._pipe = pipeline(
            "text-generation",
            model=self._model,
            tokenizer=self._tokenizer,
            device=self.device if self.device != "cpu" else -1,
        )

        self._current_model_id = model_id
        logger.info("ModelManager: '%s' geladen.", model_id)

        return self._tokenizer, self._model, self._pipe

    def ensure_loaded(self, model_id: str) -> tuple:
        """Stellt sicher, dass das angegebene Modell geladen ist."""
        return self.load(model_id)

SYSTEM_PROMPT_TEMPLATE = """\
Du bist der KI-Assistent von PB Studio, einer Video- und Audio-Produktionssoftware.
Du kannst dem Benutzer helfen, indem du Aktionen in der App auslöst.

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
7. Bei mehreren Aktionen: Führe sie in logischer Reihenfolge auf."""


class LocalAgentService:
    """Lokaler KI-Agent mit einem Small Language Model.

    Lädt das Modell lazy beim ersten Aufruf, um Startzeit zu sparen.
    Unterstützt Single- und Multi-Action-Ausgabe.

    Nutzt den zentralen ModelManager für Ressourcen-Schutz:
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
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        # Zentraler ModelManager — nur 1 Modell im RAM/VRAM
        self.model_manager = ModelManager(device=self.device)

        self._tokenizer = None
        self._model = None
        self._pipe = None
        self._loaded = False

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
    def is_loaded(self) -> bool:
        return self._loaded

    def load_model(self) -> None:
        """Lädt Modell und Tokenizer über den ModelManager."""
        if self._loaded:
            return

        logger.info("Lade lokales KI-Modell: %s auf %s ...", self.model_id, self.device)

        self._tokenizer, self._model, self._pipe = self.model_manager.load(self.model_id)
        self._loaded = True
        logger.info("KI-Modell geladen: %s", self.model_id)

    def unload_model(self) -> None:
        """Gibt GPU/RAM frei über den ModelManager."""
        self.model_manager.unload()
        self._pipe = None
        self._model = None
        self._tokenizer = None
        self._loaded = False
        logger.info("KI-Modell entladen.")

    def _build_system_prompt(self) -> str:
        """Baut den System-Prompt mit den aktuell registrierten Aktionen."""
        return SYSTEM_PROMPT_TEMPLATE.format(
            actions_json=self.registry.get_schema_for_prompt()
        )

    def _build_messages(self, user_text: str) -> list[dict]:
        """Erstellt das Chat-Messages-Format für das Modell."""
        return [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": user_text},
        ]

    def _generate(self, user_text: str, max_new_tokens: int = 512) -> str:
        """Erzeugt die rohe Modellantwort."""
        if not self._loaded:
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

        outputs = self._pipe(
            prompt_text,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=0.1,
            return_full_text=False,
        )

        return outputs[0]["generated_text"].strip()

    @staticmethod
    def _extract_json(raw: str) -> list[dict]:
        """Extrahiert JSON aus der Modellantwort.

        Unterstützt:
        - Einzelnes JSON-Objekt → wird in Liste verpackt
        - JSON-Array von Objekten → wird direkt zurückgegeben
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

        # Suche nach JSON-Array in der Antwort
        array_match = re.search(r'\[[\s\S]*?\]', raw)
        if array_match:
            try:
                parsed = json.loads(array_match.group())
                if isinstance(parsed, list) and all(isinstance(item, dict) for item in parsed):
                    return parsed
            except json.JSONDecodeError:
                pass

        # Suche nach einzelnem JSON-Objekt in der Antwort
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw)
        if match:
            try:
                parsed = json.loads(match.group())
                if isinstance(parsed, dict):
                    return [parsed]
            except json.JSONDecodeError:
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
