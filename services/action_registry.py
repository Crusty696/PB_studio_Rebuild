"""
Dynamisches Action-Registry für den lokalen KI-Agenten.

Jede App-Funktion registriert sich hier mit Name, Beschreibung und Parameter-Schema.
Die KI nutzt dieses Registry, um verfügbare Aktionen zu kennen und auszuführen.

Fuzzy Matching: Wenn die KI einen ungenauen Aktionsnamen liefert (z.B. 'analyse_files'
statt 'analyze_audio'), findet das Registry per thefuzz die beste Übereinstimmung.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from thefuzz import fuzz, process

logger = logging.getLogger(__name__)

# Minimaler Score (0-100) für Fuzzy-Matching. Darunter wird keine Aktion akzeptiert.
FUZZY_THRESHOLD = 55

# L-17 FIX: Cache for inspect.signature results to avoid repeated calls
_signature_cache: dict[Callable, Any] = {}


@dataclass
class ActionDef:
    """Definition einer registrierten Aktion."""
    name: str
    description: str
    param_schema: dict
    handler: Callable[..., Any]


class ActionRegistry:
    """Zentrales Registry für alle KI-steuerbaren App-Aktionen.

    Beispiel:
        registry = ActionRegistry()

        @registry.register(
            name="analyze_audio",
            description="Analysiert eine Audiodatei und gibt BPM, Beats und Energie zurück.",
            param_schema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Pfad zur Audiodatei"}
                },
                "required": ["file_path"]
            }
        )
        def analyze_audio(file_path: str) -> dict:
            return AudioAnalyzer().analyze(file_path)
    """

    def __init__(self):
        self._actions: dict[str, ActionDef] = {}

    def register(
        self,
        name: str,
        description: str,
        param_schema: dict | None = None,
    ) -> Callable:
        """Decorator zum Registrieren einer Aktion.

        Args:
            name: Eindeutiger Aktionsname (z.B. "analyze_audio").
            description: Kurzbeschreibung für den KI-System-Prompt.
            param_schema: JSON-Schema der erwarteten Parameter.
        """
        if param_schema is None:
            param_schema = {"type": "object", "properties": {}}

        def decorator(func: Callable) -> Callable:
            self._actions[name] = ActionDef(
                name=name,
                description=description,
                param_schema=param_schema,
                handler=func,
            )
            return func

        return decorator

    def register_function(
        self,
        name: str,
        description: str,
        handler: Callable,
        param_schema: dict | None = None,
    ) -> None:
        """Registriert eine Funktion direkt (ohne Decorator)."""
        if param_schema is None:
            param_schema = {"type": "object", "properties": {}}
        self._actions[name] = ActionDef(
            name=name,
            description=description,
            param_schema=param_schema,
            handler=handler,
        )

    def unregister(self, name: str) -> bool:
        """Entfernt eine Aktion. Gibt True zurück wenn sie existierte."""
        return self._actions.pop(name, None) is not None

    def get(self, name: str) -> ActionDef | None:
        """Gibt die ActionDef zurück oder None."""
        return self._actions.get(name)

    def fuzzy_match(self, name: str) -> tuple[str | None, int]:
        """Findet die ähnlichste registrierte Aktion per Fuzzy-Matching.

        Returns:
            (best_match_name, score) oder (None, 0) wenn kein Match über Threshold.
        """
        if not self._actions:
            return None, 0

        choices = list(self._actions.keys())

        # Exakter Treffer → sofort zurück
        if name in choices:
            return name, 100

        result = process.extractOne(
            name, choices, scorer=fuzz.token_sort_ratio
        )
        if result is None:
            return None, 0

        best_name, score, *_ = result
        if score >= FUZZY_THRESHOLD:
            return best_name, score
        return None, score

    def resolve(self, name: str) -> ActionDef | None:
        """Löst einen (evtl. ungenauen) Aktionsnamen auf.

        Gibt die ActionDef zurück oder None.
        Loggt Fuzzy-Korrekturen als Warnung.
        """
        # 1. Exakter Treffer
        action = self._actions.get(name)
        if action is not None:
            return action

        # 2. Fuzzy-Matching
        matched_name, score = self.fuzzy_match(name)
        if matched_name is not None:
            logger.warning(
                "Fuzzy-Match: '%s' → '%s' (Score: %d%%)",
                name, matched_name, score,
            )
            return self._actions[matched_name]

        logger.warning("Keine Aktion gefunden für '%s' (bester Score: %d%%)", name, score)
        return None

    def list_actions(self) -> list[str]:
        """Gibt alle registrierten Aktionsnamen zurück."""
        return list(self._actions.keys())

    def execute(self, name: str, params: dict | None = None) -> Any:
        """Führt eine registrierte Aktion aus.

        Nutzt Fuzzy-Matching: Wenn der exakte Name nicht existiert,
        wird die ähnlichste registrierte Aktion verwendet.

        Raises:
            KeyError: Wenn auch per Fuzzy kein Match gefunden wird.
            TypeError: Wenn die Parameter nicht zum Handler passen.
        """
        action = self.resolve(name)
        if action is None:
            raise KeyError(f"Aktion '{name}' nicht registriert (auch kein Fuzzy-Match). "
                           f"Verfügbar: {self.list_actions()}")
        if params is None:
            params = {}

        # Tolerante Parameter: Unbekannte Keys werden entfernt (mit Hinweis)
        import inspect
        # L-17 FIX: Use cached signature instead of calling inspect.signature every time
        if action.handler not in _signature_cache:
            _signature_cache[action.handler] = inspect.signature(action.handler)
        sig = _signature_cache[action.handler]
        valid_params = set(sig.parameters.keys())
        filtered = {k: v for k, v in params.items() if k in valid_params}

        dropped_params: set[str] = set()
        if filtered != params:
            dropped_params = set(params.keys()) - valid_params
            logger.warning(
                "Parameter bereinigt für '%s': entfernt %s, behalten %s",
                action.name, dropped_params, set(filtered.keys()),
            )

        try:
            result = action.handler(**filtered)
            if dropped_params and isinstance(result, dict):
                result = {**result, "_dropped_params": sorted(dropped_params)}
            return result
        except TypeError as exc:
            logger.error(
                "TypeError beim Ausführen von '%s' mit Params %s: %s",
                action.name, filtered, exc,
            )
            raise
        except Exception as exc:  # broad catch intentional — re-raised after logging, action functions can raise anything
            logger.error(
                "Fehler beim Ausführen von '%s': %s",
                action.name, exc, exc_info=True,
            )
            raise

    def get_schema_for_prompt(self) -> str:
        """Erzeugt eine kompakte Beschreibung aller Aktionen für den KI-System-Prompt.

        Rückgabe-Format (JSON-Array):
        [
          {
            "name": "analyze_audio",
            "description": "Analysiert eine Audiodatei ...",
            "parameters": { ... JSON-Schema ... }
          }
        ]
        """
        actions_list = []
        for action in self._actions.values():
            actions_list.append({
                "name": action.name,
                "description": action.description,
                "parameters": action.param_schema,
            })
        return json.dumps(actions_list, ensure_ascii=False, indent=2)


# Globale Singleton-Instanz
action_registry = ActionRegistry()
