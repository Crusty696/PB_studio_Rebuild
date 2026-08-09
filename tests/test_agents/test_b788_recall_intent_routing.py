"""B-788: Expliziter Recall-Intent schlaegt das Keyword-Score-Routing.

Eine ausdrueckliche Gedaechtnis-Frage ("Was weisst du ueber Clip X?") darf
nicht vom Score-Routing gekapert werden, nur weil sie Vision-Vokabular wie
"Clip" enthaelt — sie endete sonst in "Video-Analyse benoetigt eine clip_id".

Umgekehrt darf eine echte Video-Analyse-Anfrage ("Analysiere Clip 42",
"Was ist auf Clip 42 zu sehen?") NICHT gekapert werden. Die Abgrenzung
laeuft — analog zu has_explicit_learn_intent (B-782) — ueber reservierte
Satz-Praefixe, die sich an das Gedaechtnis des Assistenten richten.

Kein echter LLM-Round-Trip: der Chat-Service wird gemockt wie in
test_b782_learn_intent_priority.py. Getestet wird die Routing-Entscheidung.
"""

from unittest.mock import MagicMock, patch

import pytest


RECALL_TEXT = "Was weisst du ueber Clip X?"
RECALL_TEXT_UMLAUT = "Was weißt du über den Clip Nachtaufnahme_B738?"
RECALL_TEXT_REMEMBER = "Erinnerst du dich an Clip 42?"
RECALL_TEXT_NOTED = "Was hast du dir zu Clip 42 gemerkt?"

VISION_TEXT_IMPERATIVE = "Analysiere Clip 42."
VISION_TEXT_QUESTION = "Was ist auf Clip 42 zu sehen?"
NEUTRAL_TEXT = "Hallo, wie geht es dir?"

LEARN_TEXT_WITH_PACING = (
    "Merke dir: Der Clip Nachtaufnahme_B738 ist verwackelt "
    "und darf nicht in den Drop."
)


class _FakeVisionAgent:
    """Minimaler Stand-in fuer den VisionAgent (Score 0.45 auf 'clip'/'video')."""

    name = "vision"
    domain = "vision"
    model_id = None

    def __init__(self):
        self.processed = []

    def can_handle(self, user_text: str) -> float:
        text = (user_text or "").lower()
        if any(w in text for w in ("clip", "video", "analysiere", "sehen")):
            return 0.45
        return 0.0

    def process(self, user_text, context=None):
        self.processed.append(user_text)
        return {
            "agent": self.name,
            "action": "drop_analysis",
            "params": {},
            "result": None,
            "message": "Video-Analyse benoetigt eine clip_id.",
            "error": None,
        }


def _make_orchestrator(vision_agent):
    from agents.orchestrator_agent import OrchestratorAgent

    orch = OrchestratorAgent.__new__(OrchestratorAgent)
    orch.name = "orchestrator"
    orch._model_manager = None
    orch._agents = [vision_agent]
    return orch


def _gateway_service(action, payload_params):
    class _Svc:
        is_ready = True

        @staticmethod
        def get_default_model():
            return "phi3:mini"

        @staticmethod
        def chat(**_kwargs):
            from services.brain_gateway import encode_gateway_request

            return encode_gateway_request(action, payload_params)

    return _Svc


def _run(orch, user_text, monkeypatch, gateway_action="brain_recall",
         gateway_params=None):
    """process() fahren; alle Nicht-Routing-Vorstufen deaktiviert."""
    from services.action_registry import action_registry

    if gateway_params is None:
        gateway_params = {"query": user_text}
    execute = MagicMock(
        return_value={
            "status": "ok",
            "action": gateway_action,
            "message": "Treffer aus dem Projektgedaechtnis",
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
         patch.object(orch, "_build_context", return_value={}), \
         patch.object(orch, "_route_to_registry", return_value=None), \
         patch("agents.orchestrator_agent.OllamaService") as ollama_service, \
         patch(
             "services.ollama_client.get_ollama_client",
             return_value=fake_client,
         ):
        ollama_service.get.return_value = _gateway_service(
            gateway_action, gateway_params
        )()
        return orch.process(user_text), execute


@pytest.mark.parametrize(
    "text",
    [RECALL_TEXT, RECALL_TEXT_UMLAUT, RECALL_TEXT_REMEMBER, RECALL_TEXT_NOTED],
)
def test_has_explicit_recall_intent_matches_only_memory_questions(text):
    """Vorbedingung: Praefix-Matching erkennt Gedaechtnis-Fragen."""
    from agents.orchestrator_agent import _has_explicit_recall_intent

    assert _has_explicit_recall_intent(text) is True


@pytest.mark.parametrize(
    "text",
    [
        VISION_TEXT_IMPERATIVE,
        VISION_TEXT_QUESTION,
        NEUTRAL_TEXT,
        LEARN_TEXT_WITH_PACING,
        "Analysiere das Pacing beim Drop und merke dir was du weisst.",
        "Ich weiss nicht, was auf Clip 42 zu sehen ist.",
    ],
)
def test_has_explicit_recall_intent_ignores_non_recall(text):
    """Abgrenzung: Vision-/Learn-/Neutral-Texte sind kein Recall."""
    from agents.orchestrator_agent import _has_explicit_recall_intent

    assert _has_explicit_recall_intent(text) is False


@pytest.mark.parametrize(
    "text",
    [RECALL_TEXT, RECALL_TEXT_UMLAUT, RECALL_TEXT_REMEMBER, RECALL_TEXT_NOTED],
)
def test_recall_question_does_not_route_to_vision(text, monkeypatch):
    """(a) B-788-Kern: Recall-Frage erreicht den Gateway-/Recall-Pfad."""
    vision = _FakeVisionAgent()
    orch = _make_orchestrator(vision)

    result, execute = _run(orch, text, monkeypatch)

    assert vision.processed == [], "VisionAgent hat die Recall-Frage gekapert"
    assert result["action"] != "drop_analysis"
    assert result["action"] == "brain_recall"
    assert execute.call_args[0][0] == "brain_recall"


@pytest.mark.parametrize("text", [VISION_TEXT_IMPERATIVE, VISION_TEXT_QUESTION])
def test_real_vision_request_still_routes_to_vision(text, monkeypatch):
    """(b) Echte Video-Analyse-Anfragen bleiben beim Vision-Agenten."""
    vision = _FakeVisionAgent()
    orch = _make_orchestrator(vision)

    result, _ = _run(orch, text, monkeypatch)

    assert vision.processed == [text]
    assert result["agent"] == "vision"
    assert result["action"] == "drop_analysis"


def test_learn_intent_path_unchanged(monkeypatch):
    """(c) Regression B-782: Merk-Auftrag geht weiter in den Learn-Zweig."""
    vision = _FakeVisionAgent()
    orch = _make_orchestrator(vision)

    result, execute = _run(
        orch,
        LEARN_TEXT_WITH_PACING,
        monkeypatch,
        gateway_action="brain_learn_note",
        gateway_params={
            "title": "Nachtaufnahme_B738",
            "body": "verwackelt, nicht in den Drop",
        },
    )

    assert vision.processed == []
    assert result["action"] == "brain_learn_note"
    assert execute.call_args[0][0] == "brain_learn_note"


def test_neutral_request_unchanged(monkeypatch):
    """(d) Neutrale Anfrage ohne Agent-Treffer bleibt normaler Chat."""
    vision = _FakeVisionAgent()
    orch = _make_orchestrator(vision)

    with patch.object(orch, "_chat_with_tools_loop", return_value=None):
        result, _ = _run(
            orch,
            NEUTRAL_TEXT,
            monkeypatch,
            gateway_action="brain_stats",
            gateway_params={},
        )

    assert vision.processed == []
    assert result["agent"] == "orchestrator"


def test_route_to_agent_itself_unchanged_for_vision_text():
    """Das Score-Routing selbst bleibt unveraendert (kein Refactoring)."""
    vision = _FakeVisionAgent()
    orch = _make_orchestrator(vision)

    assert orch._route_to_agent(VISION_TEXT_IMPERATIVE) is vision
    assert orch._route_to_agent("Hallo") is None
