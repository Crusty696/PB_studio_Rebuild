"""
Integration-Tests fuer die Verkabelung des Systems (Wiring).

Prueft:
- ActionRegistry ist korrekt befuellt (nach register_actions Import)
- Alle COMPOUND_ACTION_MAP Eintraege haben eine zugehoerige registrierte Action
- ActionDef-Felder sind vollstaendig (name, description, handler)
- Jede registrierte Action ist ausfuehrbar (kein ImportError im Handler)
"""

import pytest
import sys
from pathlib import Path

# Projektroot sicherstellen
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


@pytest.fixture(autouse=True)
def _reset_global_action_registry():
    """Reset the global ActionRegistry singleton before each test.

    When wiring tests run after other tests that mutate the global registry
    (e.g. by registering or unregistering actions), the singleton carries
    stale state. This fixture clears it and re-registers all actions so
    every test in this module starts from a known-good state.
    """
    from services.action_registry import ActionRegistry, action_registry
    # Clear all registered actions from the global singleton
    action_registry._actions.clear()
    yield
    # No teardown needed — next test will clear again


# ---------------------------------------------------------------------------
# Hilfsfunktion: Isoliertes Registry (verhindert QApplication-Abhaengigkeit)
# ---------------------------------------------------------------------------

def _get_isolated_registry():
    """
    Importiert register_actions in eine FRISCHE ActionRegistry-Instanz.
    Da register_actions PySide6.QApplication benutzt, werden alle
    PySide6-Importe und TaskManager-Aufrufe gepatcht.

    RC-9 Fix: Also reloads the individual action modules so their
    @action_registry.register decorators re-fire against the fresh registry.
    Without this, module-level `from services.action_registry import action_registry`
    in each action module would still reference the (possibly stale) original singleton.
    """
    from unittest.mock import patch, MagicMock

    # Frische Registry-Instanz
    from services.action_registry import ActionRegistry
    fresh_registry = ActionRegistry()

    # PySide6 und QApplication komplett mocken
    mock_pyside = MagicMock()
    mock_pyside.QtWidgets.QApplication.instance.return_value = None

    with patch.dict(sys.modules, {
        "PySide6": mock_pyside,
        "PySide6.QtWidgets": mock_pyside.QtWidgets,
        "PySide6.QtCore": MagicMock(),
        "PySide6.QtGui": MagicMock(),
    }):
        # action_registry-Singleton durch frische Instanz ersetzen
        import services.action_registry as ar_module
        original_registry = ar_module.action_registry
        ar_module.action_registry = fresh_registry

        try:
            import importlib

            # RC-9 Fix: Reload individual action modules first so their
            # module-level `action_registry` reference picks up the fresh instance.
            _action_modules = [
                "services.actions.audio_actions",
                "services.actions.video_actions",
                "services.actions.edit_actions",
                "services.actions.ai_actions",
            ]
            for mod_name in _action_modules:
                if mod_name in sys.modules:
                    importlib.reload(sys.modules[mod_name])

            import services.register_actions as ra_module
            # Erzwinge Reload damit Dekoratoren neu ausgefuehrt werden
            importlib.reload(ra_module)
        finally:
            ar_module.action_registry = original_registry

    return fresh_registry


# ---------------------------------------------------------------------------
# Registrierte Actions – Vollstaendigkeit
# ---------------------------------------------------------------------------

# Erwartete Actions die nach register_actions vorhanden sein MUESSEN
EXPECTED_ACTIONS = [
    "analyze_audio",
    "separate_stems",
    "analyze_video",
    "auto_edit",
    "import_file",
    "export_timeline",
    "analyze_video_content",
    "create_proxy",
    "detect_scenes",
    "analyze_motion",
    "generate_embeddings",
    "search_video",
    "list_actions",
    "generate_keyframe_strings",
    # AI actions (AUD-67)
    "ask_ai",
    "summarize_project",
    "suggest_pacing",
    "model_status",
    "search_knowledge",
    "explain_clip",
]


class TestRegisteredActions:
    @pytest.fixture(autouse=True)
    def setup_registry(self):
        """Laedt ein isoliertes Registry fuer jeden Test."""
        self.registry = _get_isolated_registry()

    @pytest.mark.parametrize("action_name", EXPECTED_ACTIONS)
    def test_expected_action_is_registered(self, action_name):
        """Jede erwartete Action muss im Registry vorhanden sein."""
        available = self.registry.list_actions()
        assert action_name in available, \
            f"Action '{action_name}' fehlt im Registry. Vorhanden: {available}"

    def test_all_actions_have_description(self):
        """Jede registrierte Action hat eine nicht-leere Beschreibung."""
        for name in self.registry.list_actions():
            action = self.registry.get(name)
            assert action is not None
            assert len(action.description.strip()) > 0, \
                f"Action '{name}' hat eine leere Beschreibung"

    def test_all_actions_have_callable_handler(self):
        """Jeder Handler ist callable."""
        for name in self.registry.list_actions():
            action = self.registry.get(name)
            assert callable(action.handler), \
                f"Action '{name}' hat keinen callable Handler"

    def test_all_actions_have_param_schema(self):
        """Jede Action hat ein param_schema."""
        for name in self.registry.list_actions():
            action = self.registry.get(name)
            assert isinstance(action.param_schema, dict), \
                f"Action '{name}' hat kein gueltiges param_schema"
            assert "type" in action.param_schema, \
                f"Action '{name}' param_schema fehlt 'type'"


# ---------------------------------------------------------------------------
# COMPOUND_ACTION_MAP Konsistenz
# ---------------------------------------------------------------------------

class TestCompoundActionMapConsistency:
    def test_all_compound_actions_are_registered(self):
        """Alle COMPOUND_ACTION_MAP Eintraege verweisen auf registrierte Actions."""
        from agents.orchestrator_agent import COMPOUND_ACTION_MAP

        registry = _get_isolated_registry()
        available = registry.list_actions()

        for entry in COMPOUND_ACTION_MAP:
            action_name = entry["action"]
            assert action_name in available, \
                f"COMPOUND_ACTION_MAP referenziert unregistrierte Action: '{action_name}'"

    def test_compound_action_map_has_keywords(self):
        """Jeder COMPOUND_ACTION_MAP Eintrag hat mindestens ein Keyword."""
        from agents.orchestrator_agent import COMPOUND_ACTION_MAP

        for entry in COMPOUND_ACTION_MAP:
            assert len(entry["keywords"]) > 0, \
                f"Eintrag '{entry['action']}' hat keine Keywords"

    def test_compound_action_map_keywords_are_lowercase(self):
        """Alle Keywords sind klein geschrieben (fuer case-insensitive Matching)."""
        from agents.orchestrator_agent import COMPOUND_ACTION_MAP

        for entry in COMPOUND_ACTION_MAP:
            for kw in entry["keywords"]:
                assert kw == kw.lower(), \
                    f"Keyword '{kw}' in Action '{entry['action']}' ist nicht lowercase"


# ---------------------------------------------------------------------------
# ActionRegistry Singleton
# ---------------------------------------------------------------------------

class TestActionRegistrySingleton:
    def test_singleton_exists_in_module(self):
        """Das globale action_registry Singleton ist eine ActionRegistry-Instanz."""
        from services.action_registry import action_registry, ActionRegistry
        assert isinstance(action_registry, ActionRegistry)

    def test_singleton_is_same_object(self):
        """Mehrfachimport des Moduls liefert dasselbe Singleton-Objekt."""
        import importlib
        import services.action_registry as mod1
        import services.action_registry as mod2

        assert mod1.action_registry is mod2.action_registry


# ---------------------------------------------------------------------------
# COMPOUND_ACTION_MAP Struktur
# ---------------------------------------------------------------------------

class TestCompoundActionMapStructure:
    def test_entries_have_required_keys(self):
        """Jeder Eintrag hat 'keywords' und 'action'."""
        from agents.orchestrator_agent import COMPOUND_ACTION_MAP

        for i, entry in enumerate(COMPOUND_ACTION_MAP):
            assert "keywords" in entry, f"Eintrag {i} fehlt 'keywords'"
            assert "action" in entry, f"Eintrag {i} fehlt 'action'"
            assert isinstance(entry["keywords"], list), \
                f"Eintrag {i}: 'keywords' muss eine Liste sein"
            assert isinstance(entry["action"], str), \
                f"Eintrag {i}: 'action' muss ein String sein"

    def test_no_duplicate_action_names_in_map(self):
        """Keine doppelten Action-Namen im COMPOUND_ACTION_MAP."""
        from agents.orchestrator_agent import COMPOUND_ACTION_MAP

        action_names = [entry["action"] for entry in COMPOUND_ACTION_MAP]
        assert len(action_names) == len(set(action_names)), \
            f"Doppelte Action-Namen gefunden: {action_names}"
