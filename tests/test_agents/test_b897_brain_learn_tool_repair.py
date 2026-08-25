from unittest.mock import MagicMock, call, patch


def test_native_learn_tool_derives_missing_title_before_registry_execute():
    from agents.orchestrator_agent import OrchestratorAgent

    orchestrator = OrchestratorAgent.__new__(OrchestratorAgent)
    orchestrator.name = "orchestrator"
    orchestrator._ollama_model = "qwen2.5:3b"

    ollama_service = MagicMock(is_ready=True)
    ollama_client = MagicMock()
    ollama_client.supports_tools.return_value = True
    ollama_client.chat_with_tools.side_effect = [
        {
            "type": "tool_calls",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "brain_learn_note",
                        "arguments": {
                            "body": "Chorus bevorzugt Clip 32.",
                            "source": "agent",
                            "linked_entity_id": None,
                        },
                    }
                }
            ],
        },
        {"type": "text", "content": "Gespeichert", "tool_calls": []},
    ]
    registry = MagicMock()
    registry.build_tool_definitions.return_value = [
        {"function": {"name": "brain_learn_note"}}
    ]
    registry.execute.side_effect = [
        {"status": "error"},
        {"status": "ok", "message": "Notiz gespeichert"},
    ]

    with patch(
        "agents.orchestrator_agent.OllamaService.get",
        return_value=ollama_service,
    ), patch(
        "services.ollama_client.get_ollama_client",
        return_value=ollama_client,
    ), patch(
        "services.action_registry.action_registry",
        registry,
    ):
        result = orchestrator._chat_with_tools_loop(
            "Merke dir: Chorus bevorzugt Clip 32."
        )

    assert result == "Gespeichert"
    assert registry.execute.call_args_list == [
        call("summarize_project", {}),
        call(
            "brain_learn_note",
            {
                "title": "Chorus bevorzugt Clip 32",
                "body": "Chorus bevorzugt Clip 32.",
                "source": "agent",
            },
        ),
    ]
