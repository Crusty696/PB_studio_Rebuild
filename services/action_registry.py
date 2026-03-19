"""
Dynamisches Action-Registry für den lokalen KI-Agenten.

Jede App-Funktion registriert sich hier mit Name, Beschreibung und Parameter-Schema.
Die KI nutzt dieses Registry, um verfügbare Aktionen zu kennen und auszuführen.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable


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

    def list_actions(self) -> list[str]:
        """Gibt alle registrierten Aktionsnamen zurück."""
        return list(self._actions.keys())

    def execute(self, name: str, params: dict | None = None) -> Any:
        """Führt eine registrierte Aktion aus.

        Raises:
            KeyError: Wenn die Aktion nicht existiert.
            TypeError: Wenn die Parameter nicht zum Handler passen.
        """
        action = self._actions.get(name)
        if action is None:
            raise KeyError(f"Aktion '{name}' nicht registriert. "
                           f"Verfügbar: {self.list_actions()}")
        if params is None:
            params = {}
        return action.handler(**params)

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
