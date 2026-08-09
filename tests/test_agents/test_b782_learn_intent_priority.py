"""B-782: Expliziter Learn-Intent schlaegt das Keyword-Score-Routing.

Ein ausdruecklicher Merk-Auftrag ("Merke dir: ...") darf nicht vom
Score-Routing gekapert werden, nur weil er Pacing-Vokabular wie "Drop"
enthaelt. Beilaeufige Erwaehnungen von "merken" duerfen umgekehrt das
Pacing-Routing NICHT kapern.

Kein echter LLM-Round-Trip: Ollama ist auf dieser Maschine defekt (B-780),
deshalb wird der Chat-Service gemockt. Getestet wird die Routing-Entscheidung.
"""

from unittest.mock import MagicMock, patch

import pytest


LEARN_TEXT_WITH_PACING = (
    "Merke dir: Der Clip Nachtaufnahme_B738 ist verwackelt "
    "und darf nicht in den Drop."
)
LEARN_TEXT_PLAIN = "Merke dir: Nachtaufnahme_B738 ist verwackelt."
PACING_TEXT = "Analysiere den Drop von Track 1 und das Pacing."
CASUAL_MENTION_TEXT = "Analysiere das Pacing beim Drop und merke dir den Cut."


class _FakePacingAgent:
    """Minimaler Stand-in fuer den PacingAgent (hoher can_handle-Score)."""

    name = "pacing"
    domain = "pacing"
    model_id = None

    def __init__(self):
        self.processed = []

    def can_handle(self, user_text: str) -> float:
        text = (user_text or "").lower()
        if any(w in text for w in ("drop", "pacing", "beat")):
            return 0.55
        return 0.0

    def process(self, user_text, context=None):
        self.processed.append(user_text)
        return {
            "agent": self.name,
            "action": "drop_analysis",
            "params": {},
            "result": None,
            "message": "Drop-Analyse benötigt eine audio_track_id.",
            "error": None,
        }


def _make_orchestrator(pacing_agent):
    from agents.orchestrator_agent import OrchestratorAgent

    orch = OrchestratorAgent.__new__(OrchestratorAgent)
    orch.name = "orchestrator"
    orch._model_manager = None
    orch._agents = [pacing_agent]
    return orch


def _gateway_service(payload_params):
    class _Svc:
        is_ready = True

        @staticmethod
        def get_default_model():
            return "phi3:mini"

        @staticmethod
        def chat(**_kwargs):
            from services.brain_gateway import encode_gateway_request

            return encode_gateway_request("brain_learn_note", payload_params)

    return _Svc


def _run(orch, user_text, monkeypatch, execute=None):
    """process() fahren; alle Nicht-Routing-Vorstufen deaktiviert."""
    from services.action_registry import action_registry

    if execute is None:
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
         patch.object(orch, "_build_context", return_value={}), \
         patch.object(orch, "_route_to_registry", return_value=None), \
         patch("agents.orchestrator_agent.OllamaService") as ollama_service, \
         patch(
             "services.ollama_client.get_ollama_client",
             return_value=fake_client,
         ):
        ollama_service.get.return_value = _gateway_service(
            {"title": "Nachtaufnahme_B738", "body": "verwackelt, nicht in den Drop"}
        )()
        return orch.process(user_text), execute


def test_has_explicit_learn_intent_only_matches_prefix():
    """Vorbedingung: nur Satz-Praefix zaehlt, beilaeufiges 'merken' nicht."""
    from services.brain_gateway import has_explicit_learn_intent

    assert has_explicit_learn_intent(LEARN_TEXT_WITH_PACING) is True
    assert has_explicit_learn_intent(LEARN_TEXT_PLAIN) is True
    assert has_explicit_learn_intent(CASUAL_MENTION_TEXT) is False
    assert has_explicit_learn_intent(PACING_TEXT) is False


def test_learn_intent_with_pacing_vocab_does_not_route_to_pacing(monkeypatch):
    """(a) B-782-Kern: Merk-Auftrag mit 'Drop' geht in den Brain-Gateway."""
    pacing = _FakePacingAgent()
    orch = _make_orchestrator(pacing)

    result, execute = _run(orch, LEARN_TEXT_WITH_PACING, monkeypatch)

    assert pacing.processed == [], "PacingAgent hat den Merk-Auftrag gekapert"
    assert result["action"] != "drop_analysis"
    assert result["action"] == "brain_learn_note"
    assert execute.call_args[0][0] == "brain_learn_note"


def test_learn_intent_without_pacing_vocab_still_gateway(monkeypatch):
    """(c) Regression: Merk-Auftrag ohne Pacing-Vokabular bleibt Gateway."""
    pacing = _FakePacingAgent()
    orch = _make_orchestrator(pacing)

    result, _ = _run(orch, LEARN_TEXT_PLAIN, monkeypatch)

    assert pacing.processed == []
    assert result["action"] == "brain_learn_note"


@pytest.mark.parametrize("text", [PACING_TEXT, CASUAL_MENTION_TEXT])
def test_pacing_question_without_learn_intent_still_routes_to_pacing(
    text, monkeypatch
):
    """(b) Ohne expliziten Learn-Intent bleibt das Pacing-Routing aktiv."""
    pacing = _FakePacingAgent()
    orch = _make_orchestrator(pacing)

    result, _ = _run(orch, text, monkeypatch)

    assert pacing.processed == [text]
    assert result["agent"] == "pacing"
    assert result["action"] == "drop_analysis"


def test_route_to_agent_itself_unchanged_for_pacing_text():
    """Das Score-Routing selbst bleibt unveraendert (kein Refactoring)."""
    pacing = _FakePacingAgent()
    orch = _make_orchestrator(pacing)

    assert orch._route_to_agent(PACING_TEXT) is pacing
    assert orch._route_to_agent("Hallo") is None
