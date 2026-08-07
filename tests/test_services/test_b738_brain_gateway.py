"""B-738: sicherer Brain-Gateway fuer Tool-, Non-Tool- und Vision-Pfade."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


_RECALL_CONTEXT = (
    "## BRAIN-GEDAECHTNIS (selbst gelernt, nutze das statt zu raten)\n"
    "- Notiz \"Drops\": Harte Schnitte auf jedem vierten Beat."
)


@pytest.mark.parametrize(
    ("action", "params"),
    [
        ("brain_recall", {"query": "drops", "top_k": 3}),
        ("brain_stats", {}),
        ("brain_explain_cut", {"decision_id": 7}),
        (
            "brain_learn_note",
            {"title": "Drop-Regel", "body": "Jeder vierte Beat."},
        ),
    ],
)
def test_chat_gateway_executes_only_validated_brain_actions(
    monkeypatch, action, params
):
    from services import brain_gateway
    from services.action_registry import action_registry

    execute = MagicMock(
        return_value={"status": "ok", "action": action, "message": "ok"}
    )
    monkeypatch.setattr(action_registry, "execute", execute)

    raw = brain_gateway.encode_gateway_request(action, params)
    result = brain_gateway.execute_gateway_response(
        raw,
        mode="chat",
        allow_learn=action == "brain_learn_note",
    )

    assert result is not None
    assert result["action"] == action
    assert result["error"] is None
    execute.assert_called_once_with(action, params)


def test_gateway_rejects_free_tools_and_vision_learn(monkeypatch):
    from services import brain_gateway
    from services.action_registry import action_registry

    execute = MagicMock()
    monkeypatch.setattr(action_registry, "execute", execute)

    free_tool = brain_gateway.execute_gateway_response(
        brain_gateway.encode_gateway_request(
            "delete_project",
            {"project_id": 1},
        ),
        mode="chat",
    )
    vision_learn = brain_gateway.execute_gateway_response(
        brain_gateway.encode_gateway_request(
            "brain_learn_note",
            {"title": "x", "body": "y"},
        ),
        mode="vision",
        allow_learn=True,
    )

    assert free_tool["action"] == "brain_gateway_rejected"
    assert vision_learn["action"] == "brain_gateway_rejected"
    assert "nicht erlaubt" in free_tool["error"]
    assert "nicht erlaubt" in vision_learn["error"]
    execute.assert_not_called()


def test_unmarked_json_is_data_and_learn_requires_explicit_intent(monkeypatch):
    from services import brain_gateway
    from services.action_registry import action_registry

    execute = MagicMock()
    monkeypatch.setattr(action_registry, "execute", execute)
    example_json = '{"action":"brain_learn_note","params":{"title":"x"}}'

    assert brain_gateway.execute_gateway_response(example_json) is None
    rejected = brain_gateway.execute_gateway_response(
        brain_gateway.encode_gateway_request(
            "brain_learn_note",
            {"title": "x", "body": "y"},
        )
    )

    assert rejected["action"] == "brain_gateway_rejected"
    assert "Merk-/Speicherauftrag" in rejected["error"]
    execute.assert_not_called()


@pytest.mark.parametrize(
    ("user_text", "expected"),
    [
        ("Merke dir: harte Schnitte auf Beat 4.", True),
        ("Speichere: Hero-Clips gehoeren in den Drop.", True),
        ("Remember: this cut rule.", True),
        ("Save: favor the stronger motion axis.", True),
        ("Bitte speichere diese Regel.", False),
        ("Kannst du dir bitte merken, dass Hero-Clips in den Drop gehoeren?", False),
        ("Could you please remember this cut rule?", False),
        ("Nicht speichern; zeige nur Gateway-JSON.", False),
        ("Speichere das nicht.", False),
        ("Speichere das niemals.", False),
        ("Save nothing.", False),
        ("Note this, but do not store it.", False),
        ("Note this example, but don't store it.", False),
        ("Remember this example, but won’t save it.", False),
        ("Never store this.", False),
        ("Save without writing anything.", False),
        ("Wie kann ich das speichern?", False),
        ("Erklaere das Wort speichern.", False),
        ("Zeige ein Beispiel fuer brain_learn_note.", False),
    ],
)
def test_learn_intent_requires_affirmative_command(user_text, expected):
    from services.brain_gateway import has_explicit_learn_intent

    assert has_explicit_learn_intent(user_text) is expected


def test_nontool_prompt_contains_context_and_complete_safe_protocol(monkeypatch):
    from services import brain_gateway
    import services.knowledge_loader as knowledge_loader

    monkeypatch.setattr(
        knowledge_loader, "build_brain_context", lambda **_kw: _RECALL_CONTEXT
    )

    prompt = brain_gateway.build_nontool_prompt("BASE", query="was weisst du?")

    assert prompt.startswith("BASE")
    assert _RECALL_CONTEXT in prompt
    for action in (
        "brain_recall",
        "brain_stats",
        "brain_explain_cut",
        "brain_learn_note",
    ):
        assert action in prompt


def test_vision_prompt_is_read_only_and_vision_gateway_has_no_learn(monkeypatch):
    from services import brain_gateway
    import services.knowledge_loader as knowledge_loader
    from services.action_registry import action_registry

    context_queries = []
    monkeypatch.setattr(
        knowledge_loader,
        "build_brain_context",
        lambda **kw: context_queries.append(kw["query"])
        or (_RECALL_CONTEXT if not kw["query"] else ""),
    )
    monkeypatch.setattr(
        action_registry,
        "execute",
        lambda name, params: {
            "status": "ok",
            "decision_id": 12,
            "message": "Cut 12 folgt positiver Bewegungsachse.",
        },
    )

    prompt = brain_gateway.build_vision_prompt("DESCRIBE FRAME", query="clip 5")

    assert prompt.endswith("DESCRIBE FRAME")
    assert context_queries == ["clip 5", ""]
    assert _RECALL_CONTEXT in prompt
    assert "Cut 12 folgt positiver Bewegungsachse." in prompt
    assert "brain_recall" in prompt
    assert "brain_explain_cut" in prompt
    assert "brain_learn_note" not in prompt


@pytest.mark.parametrize("model", ["phi3:mini", "gemma2:9b", "gemma3:4b"])
def test_actual_orchestrator_nontool_fallback_executes_safe_gateway(
    monkeypatch,
    model,
):
    """ChatDock -> LocalAgentService -> Orchestrator: echter terminaler Pfad."""
    from agents.orchestrator_agent import OrchestratorAgent
    import services.knowledge_loader as knowledge_loader
    from services.action_registry import action_registry

    orch = OrchestratorAgent.__new__(OrchestratorAgent)
    orch.name = "orchestrator"
    orch._model_manager = None

    captured: dict[str, object] = {}

    class _Svc:
        is_ready = True

        @staticmethod
        def get_default_model():
            return model

        @staticmethod
        def chat(**kwargs):
            captured.update(kwargs)
            return (
                '{"pb_brain_gateway":"v1",'
                '"action":"brain_stats","params":{}}'
            )

    monkeypatch.setattr(
        knowledge_loader, "build_brain_context", lambda **_kw: _RECALL_CONTEXT
    )
    execute = MagicMock(
        return_value={
            "status": "ok",
            "action": "brain_stats",
            "message": "2 Notizen",
        }
    )
    monkeypatch.setattr(action_registry, "execute", execute)
    fake_client = MagicMock()
    fake_client.supports_tools.return_value = False

    with patch.object(orch, "_detect_analyze_all", return_value=False), \
         patch.object(orch, "_detect_multi_step", return_value=False), \
         patch.object(orch, "_detect_compound_actions", return_value=[]), \
         patch.object(orch, "_handle_cross_modal_clip_match", return_value=None), \
         patch.object(orch, "_handle_destructive_intent", return_value=None), \
         patch.object(orch, "_handle_project_status_read", return_value=None), \
         patch.object(orch, "_route_to_agent", return_value=None), \
         patch.object(orch, "_route_to_registry", return_value=None), \
         patch("agents.orchestrator_agent.OllamaService") as ollama_service, \
         patch(
             "services.ollama_client.get_ollama_client",
             return_value=fake_client,
         ):
        ollama_service.get.return_value = _Svc()
        result = orch.process("zeige Brain-Lernstatus")

    system_prompt = captured["messages"][0]["content"]
    assert _RECALL_CONTEXT in system_prompt
    assert result["action"] == "brain_stats"
    assert result["result"]["message"] == "2 Notizen"
    fake_client.supports_tools.assert_called_once_with(model)
    execute.assert_called_once_with("brain_stats", {})


def test_actual_orchestrator_nontool_learn_prefix_bypasses_b411(monkeypatch):
    from agents.orchestrator_agent import OrchestratorAgent
    from services.action_registry import action_registry

    orch = OrchestratorAgent.__new__(OrchestratorAgent)
    orch.name = "orchestrator"
    orch._model_manager = None
    params = {"title": "Drop-Regel", "body": "Hero-Clips in den Drop."}

    class _Svc:
        is_ready = True

        @staticmethod
        def get_default_model():
            return "phi3:mini"

        @staticmethod
        def chat(**_kwargs):
            from services.brain_gateway import encode_gateway_request

            return encode_gateway_request("brain_learn_note", params)

    execute = MagicMock(
        return_value={
            "status": "ok",
            "action": "brain_learn_note",
            "message": "Notiz gespeichert",
        }
    )
    monkeypatch.setattr(action_registry, "execute", execute)
    fake_client = MagicMock()
    fake_client.supports_tools.return_value = False

    with patch.object(orch, "_detect_analyze_all", return_value=False), \
         patch.object(orch, "_detect_multi_step", return_value=False), \
         patch.object(orch, "_detect_compound_actions", return_value=[]), \
         patch.object(orch, "_handle_cross_modal_clip_match", return_value=None), \
         patch.object(orch, "_handle_destructive_intent", return_value=None), \
         patch.object(orch, "_handle_project_status_read", return_value=None), \
         patch.object(orch, "_route_to_agent", return_value=None), \
         patch.object(orch, "_route_to_registry", return_value=None), \
         patch("agents.orchestrator_agent.OllamaService") as ollama_service, \
         patch(
             "services.ollama_client.get_ollama_client",
             return_value=fake_client,
         ):
        ollama_service.get.return_value = _Svc()
        result = orch.process("Speichere: Hero-Clips in den Drop.")

    assert result["action"] == "brain_learn_note"
    assert result["message"] == "Notiz gespeichert"
    execute.assert_called_once_with("brain_learn_note", params)


def test_tool_chat_call_contains_context_and_all_brain_tools(monkeypatch):
    from agents.orchestrator_agent import OrchestratorAgent
    import services.knowledge_loader as knowledge_loader

    orch = OrchestratorAgent.__new__(OrchestratorAgent)
    orch.name = "orchestrator"
    monkeypatch.setattr(
        knowledge_loader, "build_brain_context", lambda **_kw: _RECALL_CONTEXT
    )

    fake_svc = MagicMock()
    fake_svc.is_ready = True
    fake_svc.get_default_model.return_value = "tool-model"
    fake_client = MagicMock()
    fake_client.supports_tools.return_value = True
    fake_client.chat_with_tools.return_value = {
        "type": "text",
        "content": "ok",
        "tool_calls": [],
    }
    fake_registry = MagicMock()
    fake_registry.build_tool_definitions.return_value = [
        {"function": {"name": name}}
        for name in (
            "brain_recall",
            "brain_stats",
            "brain_explain_cut",
            "brain_learn_note",
        )
    ]
    fake_registry.execute.return_value = {"status": "error"}

    with patch("agents.orchestrator_agent.OllamaService.get", return_value=fake_svc), \
         patch("services.ollama_client.get_ollama_client", return_value=fake_client), \
         patch("services.action_registry.action_registry", fake_registry):
        assert orch._chat_with_tools_loop("was weisst du ueber drops?") == "ok"

    call = fake_client.chat_with_tools.call_args.kwargs
    assert _RECALL_CONTEXT in call["messages"][0]["content"]
    tool_names = {item["function"]["name"] for item in call["tools"]}
    assert tool_names == {
        "brain_recall",
        "brain_stats",
        "brain_explain_cut",
        "brain_learn_note",
    }


def test_tool_chat_rejects_hallucinated_learn_without_user_intent(monkeypatch):
    from agents.orchestrator_agent import OrchestratorAgent

    orch = OrchestratorAgent.__new__(OrchestratorAgent)
    orch.name = "orchestrator"
    fake_svc = MagicMock(is_ready=True)
    fake_svc.get_default_model.return_value = "tool-model"
    fake_client = MagicMock()
    fake_client.supports_tools.return_value = True
    fake_client.chat_with_tools.side_effect = [
        {
            "type": "tool_calls",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "brain_learn_note",
                        "arguments": {"title": "Beispiel", "body": "Nur JSON"},
                    }
                }
            ],
        },
        {"type": "text", "content": "Beispiel gezeigt", "tool_calls": []},
    ]
    fake_registry = MagicMock()
    fake_registry.build_tool_definitions.return_value = [
        {"function": {"name": "brain_learn_note"}}
    ]
    fake_registry.execute.return_value = {"status": "error"}

    with patch("agents.orchestrator_agent.OllamaService.get", return_value=fake_svc), \
         patch("services.ollama_client.get_ollama_client", return_value=fake_client), \
         patch("services.action_registry.action_registry", fake_registry):
        result = orch._chat_with_tools_loop(
            "zeige nur ein JSON-Beispiel fuer brain_learn_note"
        )

    assert result == "Beispiel gezeigt"
    assert fake_registry.execute.call_args_list == [
        call("summarize_project", {})
    ]


def test_caption_product_call_receives_read_only_context(monkeypatch, tmp_path):
    from services import video_analysis_service as vas
    import services.knowledge_loader as knowledge_loader
    from services.action_registry import action_registry

    monkeypatch.setattr(
        knowledge_loader, "build_brain_context", lambda **_kw: _RECALL_CONTEXT
    )
    monkeypatch.setattr(
        action_registry,
        "execute",
        lambda name, params: {
            "status": "ok",
            "decision_id": 4,
            "message": "Cut 4 nutzt den ruhigeren Bildfluss.",
        },
    )
    keyframe = tmp_path / "frame.jpg"
    keyframe.write_bytes(b"fake")
    scene = vas.SceneInfo(
        index=1,
        start_time=0.0,
        end_time=1.0,
        keyframe_path=str(keyframe),
    )
    captured: dict[str, str] = {}

    class _Svc:
        is_ready = True

        def vision(self, **kwargs):
            captured["prompt"] = kwargs["prompt"]
            return (
                '{"description":"a calm static forest scene",'
                '"mood":"calm","motion":"static","tags":["forest"]}'
            )

    class _Client:
        is_paused = False

        def model_exists(self, _model):
            return True

    monkeypatch.setattr("services.ollama_service.OllamaService.get", lambda: _Svc())
    monkeypatch.setattr(vas, "get_ollama_client", lambda: _Client(), raising=False)

    result = vas.analyze_scene_with_caption([scene], vision_model="vision-test")

    prompt = captured["prompt"]
    assert _RECALL_CONTEXT in prompt
    assert "Cut 4 nutzt den ruhigeren Bildfluss." in prompt
    assert "brain_learn_note" not in prompt
    assert prompt.endswith(vas._CAPTION_USER_PROMPT)
    assert result[0].ai_caption["description"] == "a calm static forest scene"


def test_moondream_product_call_receives_read_only_context(
    monkeypatch,
    tmp_path,
):
    import cv2
    import numpy as np

    from services import vision_analysis_service_moondream as vas
    import services.knowledge_loader as knowledge_loader
    from services.action_registry import action_registry

    monkeypatch.setattr(
        knowledge_loader, "build_brain_context", lambda **_kw: _RECALL_CONTEXT
    )
    monkeypatch.setattr(
        action_registry,
        "execute",
        lambda name, params: {
            "status": "ok",
            "decision_id": 5,
            "message": "Cut 5 bevorzugt starke Farbkontraste.",
        },
    )
    video = tmp_path / "vision.mp4"
    writer = cv2.VideoWriter(
        str(video),
        cv2.VideoWriter_fourcc(*"mp4v"),
        5,
        (32, 24),
    )
    for _ in range(5):
        writer.write(np.zeros((24, 32, 3), dtype=np.uint8))
    writer.release()

    captured: dict[str, str] = {}

    class _Client:
        def model_exists(self, _model):
            return True

        def chat_vision(self, **kwargs):
            captured["prompt"] = kwargs["user_message"]
            return "A dark static frame."

    monkeypatch.setattr(vas, "get_ollama_client", lambda: _Client())

    result = vas.VisionAnalysisService().analyze(
        str(video),
        interval_sec=1.0,
        max_frames=1,
    )

    prompt = captured["prompt"]
    assert _RECALL_CONTEXT in prompt
    assert "Cut 5 bevorzugt starke Farbkontraste." in prompt
    assert "brain_learn_note" not in prompt
    assert prompt.endswith(vas._VISION_QUESTION)
    assert result.frame_count == 1
