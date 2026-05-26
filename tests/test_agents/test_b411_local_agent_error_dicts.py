from __future__ import annotations

from services.action_registry import ActionRegistry
from services.local_agent_service import LocalAgentService


def test_b411_action_error_dict_promotes_to_top_level_error():
    registry = ActionRegistry()

    @registry.register(name="needs_app", description="Requires initialized app")
    def needs_app():
        return {"error": "App nicht initialisiert"}

    service = LocalAgentService(registry=registry, use_ollama=False)

    result = service._execute_single_action({"action": "needs_app", "params": {}})

    assert result["action"] == "needs_app"
    assert result["result"] is None
    assert result["error"] == "Fehler bei 'needs_app': App nicht initialisiert"
