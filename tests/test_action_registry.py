"""Tests für das ActionRegistry."""

import json
import pytest
from services.action_registry import ActionRegistry


@pytest.fixture
def registry():
    return ActionRegistry()


def test_register_and_execute(registry):
    @registry.register(
        name="greet",
        description="Begrüßt jemanden.",
        param_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"}
            },
            "required": ["name"]
        }
    )
    def greet(name: str) -> str:
        return f"Hallo {name}!"

    result = registry.execute("greet", {"name": "David"})
    assert result == "Hallo David!"


def test_register_function(registry):
    def add(a: int, b: int) -> int:
        return a + b

    registry.register_function("add", "Addiert zwei Zahlen.", add, {
        "type": "object",
        "properties": {
            "a": {"type": "integer"},
            "b": {"type": "integer"}
        }
    })
    assert registry.execute("add", {"a": 3, "b": 4}) == 7


def test_list_actions(registry):
    registry.register_function("foo", "Foo.", lambda: None)
    registry.register_function("bar", "Bar.", lambda: None)
    assert set(registry.list_actions()) == {"foo", "bar"}


def test_unregister(registry):
    registry.register_function("temp", "Temporär.", lambda: None)
    assert registry.unregister("temp") is True
    assert registry.unregister("temp") is False
    assert "temp" not in registry.list_actions()


def test_execute_unknown_raises(registry):
    with pytest.raises(KeyError, match="nicht registriert"):
        registry.execute("nope")


def test_get_schema_for_prompt(registry):
    registry.register_function("demo", "Demo-Aktion.", lambda: None, {
        "type": "object",
        "properties": {"x": {"type": "string"}}
    })
    schema_str = registry.get_schema_for_prompt()
    parsed = json.loads(schema_str)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "demo"
    assert parsed[0]["description"] == "Demo-Aktion."


def test_registered_app_actions():
    """Prüft dass register_actions.py die App-Aktionen korrekt registriert."""
    from services.action_registry import action_registry
    import services.register_actions  # noqa: F401 - Seiteneffekt: registriert Aktionen

    expected = {
        "analyze_audio", "separate_stems", "analyze_video",
        "auto_edit", "import_file", "export_timeline", "list_actions",
    }
    assert expected.issubset(set(action_registry.list_actions()))
