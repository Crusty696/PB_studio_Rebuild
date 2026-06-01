from __future__ import annotations

from services.action_registry import ActionRegistry
from services.local_agent_service import LocalAgentService


def test_destructive_action_with_unknown_params_rejected_before_handler_call():
    registry = ActionRegistry()
    called = False

    @registry.register(name="delete_media", description="delete")
    def delete_media(media_id: int):
        nonlocal called
        called = True
        return {"deleted": media_id}

    service = LocalAgentService(registry=registry, use_ollama=False)

    result = service._execute_single_action(
        {"action": "delete_media", "params": {"media_id": 7, "surprise": "x", "confirm": True}}
    )

    assert called is False
    assert result["result"] is None
    assert "Fehler bei 'delete_media'" in result["error"]


def test_destructive_action_without_confirmation_rejected_before_handler_call():
    registry = ActionRegistry()
    called = False

    @registry.register(name="delete_media", description="delete")
    def delete_media(media_id: int):
        nonlocal called
        called = True
        return {"deleted": media_id}

    service = LocalAgentService(registry=registry, use_ollama=False)

    result = service._execute_single_action(
        {"action": "delete_media", "params": {"media_id": 7}}
    )

    assert called is False
    assert result["result"] is None
    assert "Confirmation required" in result["error"]


def test_safe_action_with_exact_params_executes_once():
    registry = ActionRegistry()
    calls: list[int] = []

    @registry.register(name="analyze_audio", description="safe")
    def analyze_audio(track_id: int):
        calls.append(track_id)
        return {"track_id": track_id}

    service = LocalAgentService(registry=registry, use_ollama=False)

    result = service._execute_single_action(
        {"action": "analyze_audio", "params": {"track_id": 42}}
    )

    assert calls == [42]
    assert result["result"] == {"track_id": 42}
    assert result["error"] is None


def test_malformed_action_json_returns_structured_error_without_side_effect():
    registry = ActionRegistry()
    called = False

    @registry.register(name="delete_media", description="delete")
    def delete_media(media_id: int):
        nonlocal called
        called = True
        return {"deleted": media_id}

    service = LocalAgentService(registry=registry, use_ollama=False)
    parsed = service._extract_json("not json {broken")

    assert len(parsed) == 1
    result = service._execute_single_action(parsed[0])

    assert called is False
    assert result["action"] == "none"
    assert result["result"] is None
    assert result["error"] == "Malformed action JSON"
