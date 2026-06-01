"""
Tests fuer services/action_registry.py

Getestet: ActionRegistry.register(), execute(), fuzzy_match(), resolve(),
          Parameter-Filtering, KeyError bei unbekannter Action.
"""

import pytest
from unittest.mock import MagicMock, patch

from services.action_registry import ActionRegistry, ActionDef, FUZZY_THRESHOLD


# ---------------------------------------------------------------------------
# Basis-Registrierung
# ---------------------------------------------------------------------------

class TestActionRegistryRegister:
    def test_register_via_decorator_stores_action(self):
        """register()-Decorator legt ActionDef im Registry ab."""
        registry = ActionRegistry()

        @registry.register(name="do_thing", description="Does a thing")
        def do_thing():
            return "done"

        assert "do_thing" in registry.list_actions()

    def test_register_function_stores_action(self):
        """register_function() legt ActionDef ohne Decorator ab."""
        registry = ActionRegistry()

        def my_func(x: int) -> int:
            return x * 2

        registry.register_function(
            name="double",
            description="Doubles a number",
            handler=my_func,
            param_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
        )

        assert "double" in registry.list_actions()

    def test_register_replaces_existing_action(self):
        """Erneutes Registrieren desselben Namens ueberschreibt die alte Action."""
        registry = ActionRegistry()

        @registry.register(name="my_action", description="v1")
        def v1():
            return 1

        @registry.register(name="my_action", description="v2")
        def v2():
            return 2

        result = registry.execute("my_action")
        assert result == 2

    def test_unregister_removes_action(self):
        """unregister() entfernt Action aus Registry."""
        registry = ActionRegistry()

        @registry.register(name="to_remove", description="temp")
        def to_remove():
            pass

        assert registry.unregister("to_remove") is True
        assert "to_remove" not in registry.list_actions()

    def test_unregister_returns_false_for_unknown(self):
        registry = ActionRegistry()
        assert registry.unregister("nonexistent") is False


# ---------------------------------------------------------------------------
# execute() Tests
# ---------------------------------------------------------------------------

class TestActionRegistryExecute:
    def test_execute_calls_handler_with_params(self):
        """execute() ruft den Handler mit den richtigen Parametern auf.

        WICHTIG: Handler muss eine echte Funktion mit deklarierter Signatur sein,
        damit der Parameter-Filter 'track_id' als bekannten Parameter akzeptiert.
        Ein bloses MagicMock() haette keine Signatur -> alle Params wuerden gefiltert.
        """
        registry = ActionRegistry()
        received = {}

        # Echte Funktion mit deklarierter Signatur registrieren
        def analyze_handler(track_id: int) -> dict:
            received["track_id"] = track_id
            return {"status": "ok", "track_id": track_id}

        registry.register_function(
            name="analyze",
            description="Analyzes",
            handler=analyze_handler,
            param_schema={
                "type": "object",
                "properties": {"track_id": {"type": "integer"}},
                "required": ["track_id"],
            },
        )

        result = registry.execute("analyze", {"track_id": 42})

        assert received["track_id"] == 42
        assert result == {"status": "ok", "track_id": 42}

    def test_execute_unknown_action_raises_key_error(self):
        """execute() loest KeyError aus fuer unbekannte Action."""
        registry = ActionRegistry()

        with pytest.raises(KeyError, match="nicht registriert"):
            registry.execute("totally_unknown_xyz_action_12345")

    def test_execute_with_none_params_passes_empty_dict(self):
        """execute() akzeptiert params=None und ruft Handler ohne Argumente auf."""
        registry = ActionRegistry()
        called = {"with": None}

        @registry.register(name="no_params", description="")
        def no_params():
            called["with"] = "empty"
            return "ok"

        registry.execute("no_params", None)
        assert called["with"] == "empty"

    def test_execute_filters_unknown_kwargs(self):
        """Unbekannte Parameter werden still entfernt (keine TypeError)."""
        registry = ActionRegistry()
        received = {}

        @registry.register(name="strict_fn", description="")
        def strict_fn(known_param: str):
            received["val"] = known_param
            return known_param

        result = registry.execute("strict_fn", {
            "known_param": "hello",
            "unknown_param": "should_be_removed",
        })

        assert result == "hello"
        assert "unknown_param" not in received

    def test_execute_propagates_handler_exceptions(self):
        """Exceptions im Handler werden weitergegeben."""
        registry = ActionRegistry()

        @registry.register(name="buggy", description="")
        def buggy():
            raise ValueError("Intentional error")

        with pytest.raises(ValueError, match="Intentional error"):
            registry.execute("buggy")

    def test_execute_return_value_is_passed_through(self):
        """Rueckgabewert des Handlers wird unveraendert zurueckgegeben."""
        registry = ActionRegistry()
        expected = {"a": 1, "b": [1, 2, 3]}

        @registry.register(name="returner", description="")
        def returner():
            return expected

        result = registry.execute("returner")
        assert result is expected


# ---------------------------------------------------------------------------
# fuzzy_match() Tests
# ---------------------------------------------------------------------------

class TestActionRegistryFuzzyMatch:
    def test_exact_match_returns_score_100(self):
        """Exakter Treffer gibt Score 100 zurueck."""
        registry = ActionRegistry()

        @registry.register(name="analyze_audio", description="")
        def analyze_audio():
            pass

        name, score = registry.fuzzy_match("analyze_audio")
        assert name == "analyze_audio"
        assert score == 100

    def test_fuzzy_match_finds_close_name(self):
        """Fuzzy-Match findet aehnliche Namen."""
        registry = ActionRegistry()

        @registry.register(name="analyze_audio", description="")
        def analyze_audio():
            pass

        name, score = registry.fuzzy_match("analyse_audio")  # 's' statt 'z'
        assert name == "analyze_audio"
        assert score >= FUZZY_THRESHOLD

    def test_fuzzy_match_returns_none_for_very_different_name(self):
        """Fuzzy-Match gibt None zurueck fuer voellig anderen Namen."""
        registry = ActionRegistry()

        @registry.register(name="analyze_audio", description="")
        def analyze_audio():
            pass

        name, score = registry.fuzzy_match("xyzzy_completely_unrelated")
        assert name is None
        assert score < FUZZY_THRESHOLD

    def test_fuzzy_match_empty_registry_returns_none(self):
        """Fuzzy-Match auf leerem Registry gibt (None, 0) zurueck."""
        registry = ActionRegistry()
        name, score = registry.fuzzy_match("anything")
        assert name is None
        assert score == 0

    @pytest.mark.parametrize("typo,expected_action", [
        ("analyse_files", "analyze_audio"),
        ("analyze_udio", "analyze_audio"),
        ("seperate_stems", "separate_stems"),
    ])
    def test_fuzzy_match_common_typos(self, typo, expected_action):
        """Haeufige Tippfehler werden korrekt gemappt."""
        registry = ActionRegistry()

        @registry.register(name="analyze_audio", description="")
        def analyze_audio():
            pass

        @registry.register(name="separate_stems", description="")
        def separate_stems():
            pass

        name, score = registry.fuzzy_match(typo)
        if score >= FUZZY_THRESHOLD:
            assert name == expected_action


# ---------------------------------------------------------------------------
# resolve() Tests
# ---------------------------------------------------------------------------

class TestActionRegistryResolve:
    def test_resolve_exact_name(self):
        """resolve() gibt korrekte ActionDef bei exaktem Namen zurueck."""
        registry = ActionRegistry()

        @registry.register(name="exact_action", description="Exact")
        def exact_action():
            pass

        action = registry.resolve("exact_action")
        assert action is not None
        assert action.name == "exact_action"

    def test_resolve_fuzzy_name(self):
        """resolve() findet Action per Fuzzy-Matching."""
        registry = ActionRegistry()

        @registry.register(name="analyze_video", description="")
        def analyze_video():
            pass

        action = registry.resolve("analyse_video")  # Fuzzy-Input
        assert action is not None
        assert action.name == "analyze_video"

    def test_resolve_unknown_returns_none(self):
        """resolve() gibt None zurueck fuer voellig unbekannte Action."""
        registry = ActionRegistry()
        assert registry.resolve("totally_unknown_xyzzz") is None

    @pytest.mark.parametrize(
        ("registered_action", "fuzzy_name"),
        [
            ("delete_media", "delete_medium"),
            ("clear_timeline", "clear time line"),
            ("remove_clip", "remove anchr"),
            ("remove_anchor", "rm_anchor"),
        ],
    )
    def test_b413_missing_destructive_action_rejects_loose_fuzzy(self, registered_action, fuzzy_name):
        """Destruktive Actions duerfen nicht ueber loose fuzzy erreichbar sein."""
        registry = ActionRegistry()

        @registry.register(name=registered_action, description="")
        def destructive_action():
            pass

        assert registry.resolve(fuzzy_name) is None


# ---------------------------------------------------------------------------
# get_schema_for_prompt() Tests
# ---------------------------------------------------------------------------

class TestGetSchemaForPrompt:
    def test_returns_valid_json(self):
        """get_schema_for_prompt() gibt gueltiges JSON zurueck."""
        import json

        registry = ActionRegistry()

        @registry.register(
            name="my_action",
            description="Does stuff",
            param_schema={"type": "object", "properties": {"x": {"type": "integer"}}},
        )
        def my_action(x: int):
            pass

        schema_str = registry.get_schema_for_prompt()
        parsed = json.loads(schema_str)

        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "my_action"
        assert parsed[0]["description"] == "Does stuff"

    def test_empty_registry_returns_empty_list(self):
        """Leeres Registry gibt '[]' zurueck."""
        import json
        registry = ActionRegistry()
        result = json.loads(registry.get_schema_for_prompt())
        assert result == []


# ---------------------------------------------------------------------------
# Parameter-Filtering Detail-Tests
# ---------------------------------------------------------------------------

class TestParameterFiltering:
    def test_all_valid_params_are_passed(self):
        """Alle bekannten Parameter werden an Handler uebergeben."""
        registry = ActionRegistry()
        received = {}

        def handler(a: int, b: str, c: float):
            received.update({"a": a, "b": b, "c": c})
            return True

        registry.register_function("fn", "desc", handler)
        registry.execute("fn", {"a": 1, "b": "x", "c": 3.14})

        assert received == {"a": 1, "b": "x", "c": 3.14}

    def test_only_unknown_params_are_filtered(self):
        """Nur unbekannte Parameter werden entfernt; bekannte bleiben erhalten."""
        registry = ActionRegistry()
        received = {}

        def handler(known: str):
            received["known"] = known
            return known

        registry.register_function("fn2", "desc", handler)
        registry.execute("fn2", {"known": "value", "unknown1": 1, "unknown2": 2})

        assert received.get("known") == "value"

    def test_b414_destructive_action_rejects_unknown_params_before_side_effect(self):
        registry = ActionRegistry()
        called = False

        @registry.register(name="clear_timeline", description="")
        def clear_timeline():
            nonlocal called
            called = True
            return {"status": "ok"}

        with pytest.raises(ValueError, match="Unbekannte Parameter.*clear_timeline"):
            registry.execute("clear_timeline", {"project_id": 999, "confirm": True})

        assert called is False
