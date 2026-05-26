"""
Dynamisches Action-Registry für den lokalen KI-Agenten.

Jede App-Funktion registriert sich hier mit Name, Beschreibung und Parameter-Schema.
Die KI nutzt dieses Registry, um verfügbare Aktionen zu kennen und auszuführen.

Fuzzy Matching: Wenn die KI einen ungenauen Aktionsnamen liefert (z.B. 'analyse_files'
statt 'analyze_audio'), findet das Registry per thefuzz die beste Übereinstimmung.
"""

import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable

from thefuzz import fuzz, process

logger = logging.getLogger(__name__)

# Minimaler Score (0-100) für Fuzzy-Matching. Darunter wird keine Aktion akzeptiert.
# B-081: Threshold von 55 auf 85 angehoben — 55% liess "delete_videos"
# auf "delete_all_media" durchrutschen (Datenverlust-Risiko bei
# LLM-Halluzinationen). 85% bedeutet quasi-exact Match.
FUZZY_THRESHOLD = 85

# B-216: Lockerer Threshold fuer NICHT-destruktive Actions im resolve()-
# Fallback-Pfad. Erlaubt Variations wie "analyse" -> "analyze_audio" (Score 69)
# OHNE die strenge 85%-Hauptregel zu schwaechen. Destructive Actions
# werden in diesem Pfad ausdruecklich ausgeschlossen (siehe resolve()).
LOOSE_FUZZY_THRESHOLD = 55

# B-081: Destruktive Aktionen duerfen NIEMALS per Fuzzy-Match getroffen
# werden, ausser bei Score >= 95% (quasi-Tippfehler-Toleranz). Whitelist
# ist explizit, damit neu hinzugefuegte gefaehrliche Actions hier
# eingetragen werden muessen.
DESTRUCTIVE_ACTIONS: frozenset[str] = frozenset({
    "delete_all_media",
    "delete_selected_media",
    "clear_all_media",
    "delete_project",
    "delete_video_clip",
    "delete_audio_track",
    "delete_media",
    "clear_timeline",
    "remove_clip",
    "remove_anchor",
})
DESTRUCTIVE_FUZZY_THRESHOLD = 95

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
        # B-132: RLock erlaubt rekursive Aufrufe im selben Thread (z.B.
        # ``execute`` ruft ``resolve`` ruft ``fuzzy_match``).
        self._lock = threading.RLock()

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
            with self._lock:  # B-132
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
        with self._lock:  # B-132
            self._actions[name] = ActionDef(
                name=name,
                description=description,
                param_schema=param_schema,
                handler=handler,
            )

    def unregister(self, name: str) -> bool:
        """Entfernt eine Aktion. Gibt True zurück wenn sie existierte.

        Cycle 13 BUG-A2: zugehoerigen _signature_cache-Eintrag mit-droppen,
        sonst akkumulieren stale handler-Refs ueber unregister/register-Cycles.
        """
        with self._lock:  # B-132
            removed = self._actions.pop(name, None)
            if removed is not None:
                _signature_cache.pop(removed.handler, None)
                return True
            return False

    @staticmethod
    def clear_signature_cache() -> None:
        """Cycle 13 BUG-A1: Test-Helper / periodischer Memory-Cleanup.

        Das module-level _signature_cache wuechst sonst ueber den ganzen
        App-Lebenszyklus. In Production unkritisch (Anzahl handler ist
        beschraenkt), aber in Tests die viele ActionRegistry-Instanzen
        erzeugen kann es lecken.
        """
        _signature_cache.clear()

    def get(self, name: str) -> ActionDef | None:
        """Gibt die ActionDef zurück oder None."""
        with self._lock:  # B-132
            return self._actions.get(name)

    def fuzzy_match(self, name: str, threshold: int | None = None) -> tuple[str | None, int]:
        """Findet die ähnlichste registrierte Aktion per Fuzzy-Matching.

        Args:
            name: Aktionsname (evtl. mit Tippfehler).
            threshold: optionaler eigener Score-Threshold (0-100).
                None = ``LOOSE_FUZZY_THRESHOLD`` (Default 55). Liefert das
                beste Match, wenn der Score den Threshold erreicht.
                resolve() ueberschreibt das mit der strict-policy
                (FUZZY_THRESHOLD / DESTRUCTIVE_FUZZY_THRESHOLD).

        Returns:
            (best_match_name, score) oder (None, score) wenn kein Match
            über Threshold. Bei kompletter Mismatch: (None, 0).
        """
        if threshold is None:
            threshold = LOOSE_FUZZY_THRESHOLD

        with self._lock:  # B-132
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
        if score >= threshold:
            return best_name, score
        return None, score

    def resolve(self, name: str) -> ActionDef | None:
        """Löst einen (evtl. ungenauen) Aktionsnamen auf.

        Gibt die ActionDef zurück oder None.
        Loggt Fuzzy-Korrekturen als Warnung.

        B-132: Reads happen under self._lock (RLock — fuzzy_match nested
        re-acquire is allowed).
        """
        with self._lock:
            # 1. Exakter Treffer
            action = self._actions.get(name)
            if action is not None:
                return action

            # 2. Fuzzy-Match (loose default — siehe fuzzy_match docstring).
            matched_name, score = self.fuzzy_match(name)
            if matched_name is None:
                logger.warning(
                    "Keine Aktion gefunden für '%s' (bester Score: %d%%)", name, score,
                )
                return None

            is_destructive = matched_name in DESTRUCTIVE_ACTIONS

            # 3a. Destruktive Actions: brauchen 95%+ (B-081 Datenverlust-Schutz).
            if is_destructive:
                if score < DESTRUCTIVE_FUZZY_THRESHOLD:
                    logger.warning(
                        "B-081: REFUSED fuzzy-match '%s' -> destruktive Aktion '%s' "
                        "(Score %d%% < %d%%). User muss exakten Namen liefern.",
                        name, matched_name, score, DESTRUCTIVE_FUZZY_THRESHOLD,
                    )
                    return None
                logger.warning(
                    "Fuzzy-Match (destruktiv): '%s' → '%s' (Score: %d%%)",
                    name, matched_name, score,
                )
                return self._actions[matched_name]

            # 3b. Nicht-destruktive Actions:
            #     - Score >= FUZZY_THRESHOLD (85): direkt durchwinken.
            #     - LOOSE_FUZZY_THRESHOLD (55) <= Score < 85: loose-Pfad
            #       (B-216) — erlaubt mit lautem Warning. Sicher, weil
            #       destruktive Actions weiter oben separat gehandhabt werden.
            if score >= FUZZY_THRESHOLD:
                logger.warning(
                    "Fuzzy-Match: '%s' → '%s' (Score: %d%%)",
                    name, matched_name, score,
                )
            else:
                logger.warning(
                    "B-216: Loose-Fuzzy-Match: '%s' → '%s' (Score: %d%%, "
                    "unter strict-threshold %d%%). Erlaubt fuer nicht-"
                    "destruktive Actions.",
                    name, matched_name, score, FUZZY_THRESHOLD,
                )
            return self._actions[matched_name]

    def list_actions(self) -> list[str]:
        """Gibt alle registrierten Aktionsnamen zurück."""
        with self._lock:  # B-132
            return list(self._actions.keys())

    def list_all(self) -> list[ActionDef]:
        """Gibt alle registrierten ActionDef-Objekte zurück (B3-Fix)."""
        with self._lock:  # B-132
            return list(self._actions.values())

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
            if action.name in DESTRUCTIVE_ACTIONS:
                raise ValueError(
                    f"Unbekannte Parameter fuer destruktive Aktion '{action.name}': "
                    f"{sorted(dropped_params)}"
                )
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

    def build_tool_definitions(
        self,
        names: list[str] | None = None,
    ) -> list[dict]:
        """B-243: Erzeugt OpenAI-/Ollama-kompatible Tool-Definitionen fuer Function-Calling.

        Args:
            names: Wenn gesetzt, werden nur diese Aktionen exportiert
                   (Whitelist-Pattern). None = alle registrierten Aktionen.

        Returns:
            Liste von Tool-Definitionen im Format::

                [
                    {
                        "type": "function",
                        "function": {
                            "name": "<action-name>",
                            "description": "<action-description>",
                            "parameters": <param_schema-json-schema>,
                        },
                    },
                    ...
                ]

            Direkt verwendbar als ``tools=...``-Argument in
            ``OllamaClient.chat_with_tools(...)``.
        """
        with self._lock:  # B-132
            if names is None:
                actions = list(self._actions.values())
            else:
                wanted = set(names)
                actions = [a for a in self._actions.values() if a.name in wanted]

        return [
            {
                "type": "function",
                "function": {
                    "name": a.name,
                    "description": a.description,
                    "parameters": a.param_schema,
                },
            }
            for a in actions
        ]

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
        with self._lock:  # B-132
            actions_list = [
                {
                    "name": action.name,
                    "description": action.description,
                    "parameters": action.param_schema,
                }
                for action in self._actions.values()
            ]
        return json.dumps(actions_list, ensure_ascii=False, indent=2)


# Globale Singleton-Instanz
action_registry = ActionRegistry()
