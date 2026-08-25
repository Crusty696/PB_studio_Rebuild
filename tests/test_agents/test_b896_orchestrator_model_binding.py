from unittest.mock import MagicMock, patch


def _bare_orchestrator(model: str):
    from agents.orchestrator_agent import OrchestratorAgent

    orchestrator = OrchestratorAgent.__new__(OrchestratorAgent)
    orchestrator.name = "orchestrator"
    orchestrator._ollama_model = model
    orchestrator._agents = []
    orchestrator._model_manager = None
    return orchestrator


def test_local_agent_binds_and_reconfigures_orchestrator_model():
    from services.local_agent_service import LocalAgentService

    orchestrator = MagicMock()
    orchestrator_type = MagicMock(return_value=orchestrator)

    with patch(
        "agents.orchestrator_agent.OrchestratorAgent", orchestrator_type
    ), patch("services.model_manager.ModelManager", return_value=MagicMock()):
        service = LocalAgentService(
            ollama_model="gemma3:4b",
            use_ollama=True,
        )
        assert service._get_orchestrator() is orchestrator
        orchestrator_type.assert_called_once_with(ollama_model="gemma3:4b")

        service.configure_ollama(
            "http://127.0.0.1:11434",
            model="ALIENTELLIGENCE/avengineer:latest",
        )

    orchestrator.set_ollama_model.assert_called_once_with(
        "ALIENTELLIGENCE/avengineer:latest"
    )


def test_bound_model_controls_tool_loop_and_intent_classifier():
    orchestrator = _bare_orchestrator("gemma3:4b")
    ollama_service = MagicMock(is_ready=True)
    ollama_service.get_default_model.return_value = (
        "ALIENTELLIGENCE/avengineer:latest"
    )
    ollama_service.chat.return_value = "general"
    ollama_client = MagicMock()
    ollama_client.supports_tools.return_value = False

    with patch(
        "agents.orchestrator_agent.OllamaService.get",
        return_value=ollama_service,
    ), patch(
        "services.ollama_client.get_ollama_client",
        return_value=ollama_client,
    ):
        assert orchestrator._chat_with_tools_loop("Hallo") is None
        assert orchestrator._llm_classify_intent("Hallo") == "general"

    ollama_client.supports_tools.assert_called_once_with("gemma3:4b")
    ollama_service.get_default_model.assert_not_called()
    assert ollama_service.chat.call_args.kwargs["model"] == "gemma3:4b"


def test_bound_model_controls_nontool_fallback():
    orchestrator = _bare_orchestrator("gemma3:4b")
    ollama_service = MagicMock(is_ready=True)
    ollama_service.chat.return_value = "Antwort"

    bypasses = {
        "_detect_analyze_all": False,
        "_detect_multi_step": False,
        "_detect_compound_actions": [],
        "_handle_cross_modal_clip_match": None,
        "_handle_destructive_intent": None,
        "_is_project_status_read": False,
        "_route_to_agent": None,
        "_handle_project_status_read": None,
        "_route_to_registry": None,
        "_chat_with_tools_loop": None,
        "_looks_like_action_command": False,
    }

    patches = [
        patch.object(orchestrator, name, return_value=value)
        for name, value in bypasses.items()
    ]
    for active_patch in patches:
        active_patch.start()
    try:
        with patch(
            "agents.orchestrator_agent.OllamaService.get",
            return_value=ollama_service,
        ), patch(
            "services.brain_gateway.execute_gateway_response",
            return_value=None,
        ):
            result = orchestrator.process("Erzaehle etwas")
    finally:
        for active_patch in reversed(patches):
            active_patch.stop()

    assert result["message"] == "Antwort"
    assert ollama_service.chat.call_args.kwargs["model"] == "gemma3:4b"
