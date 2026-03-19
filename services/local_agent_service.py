"""
Lokaler KI-Agent auf Basis eines Small Language Model (SLM).

Läuft 100% offline auf CPU/GPU. Nutzt das ActionRegistry,
um App-Funktionen per natürlicher Sprache auszuführen.
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

SYSTEM_PROMPT_TEMPLATE = """\
Du bist der KI-Assistent von PB Studio, einer Video- und Audio-Produktionssoftware.
Du kannst dem Benutzer helfen, indem du Aktionen in der App auslöst.

VERFÜGBARE AKTIONEN:
{actions_json}

REGELN:
1. Antworte IMMER mit exakt einem JSON-Objekt. Kein Text davor oder danach.
2. Format: {{"action": "<name>", "params": {{...}}}}
3. Wenn keine Aktion passt: {{"action": "none", "params": {{}}, "message": "<Antwort>"}}
4. Verwende nur Aktionen aus der obigen Liste.
5. Fülle die Parameter gemäß dem Schema der Aktion."""


class LocalAgentService:
    """Lokaler KI-Agent mit einem Small Language Model.

    Lädt das Modell lazy beim ersten Aufruf, um Startzeit zu sparen.
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

        self._tokenizer = None
        self._model = None
        self._pipe = None
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load_model(self) -> None:
        """Lädt Modell und Tokenizer. Wird beim ersten process()-Aufruf automatisch aufgerufen."""
        if self._loaded:
            return

        logger.info("Lade lokales KI-Modell: %s auf %s ...", self.model_id, self.device)

        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_id,
            trust_remote_code=True,
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
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

        self._loaded = True
        logger.info("KI-Modell geladen: %s", self.model_id)

    def unload_model(self) -> None:
        """Gibt GPU/RAM frei."""
        self._pipe = None
        self._model = None
        self._tokenizer = None
        self._loaded = False
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
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

    def _generate(self, user_text: str, max_new_tokens: int = 256) -> str:
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
    def _extract_json(raw: str) -> dict:
        """Extrahiert das erste JSON-Objekt aus der Modellantwort."""
        # Versuche direktes Parsing
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Suche nach JSON-Block in der Antwort
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Fallback: keine gültige Aktion erkannt
        return {"action": "none", "params": {}, "message": raw}

    def process(self, user_text: str) -> dict[str, Any]:
        """Verarbeitet eine Benutzeranfrage und gibt das Ergebnis zurück.

        Rückgabe:
            {
                "action": str,        # Name der ausgeführten Aktion oder "none"
                "params": dict,        # Parameter die verwendet wurden
                "result": Any,         # Ergebnis der Aktion (oder None)
                "message": str | None, # Nachricht der KI (bei action=none)
                "error": str | None,   # Fehlermeldung falls etwas schiefging
            }
        """
        response = {
            "action": "none",
            "params": {},
            "result": None,
            "message": None,
            "error": None,
        }

        try:
            raw_output = self._generate(user_text)
            logger.debug("KI-Rohantwort: %s", raw_output)

            parsed = self._extract_json(raw_output)
            action_name = parsed.get("action", "none")
            params = parsed.get("params", {})

            response["action"] = action_name
            response["params"] = params
            response["message"] = parsed.get("message")

            # Aktion ausführen wenn es keine "none"-Antwort ist
            if action_name != "none":
                action_def = self.registry.get(action_name)
                if action_def is None:
                    response["error"] = f"Unbekannte Aktion: {action_name}"
                    response["action"] = "none"
                else:
                    result = self.registry.execute(action_name, params)
                    response["result"] = result

        except Exception as e:
            logger.exception("Fehler bei KI-Verarbeitung")
            response["error"] = str(e)

        return response
