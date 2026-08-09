"""B-791: Projekt-Statusfragen duerfen nicht im Vision-Agenten landen.

Live-Befund 2026-08-09 (Abnahme-Smoke): "Wie viele Clips hat dieses
Projekt?" wurde per Score-Routing (0.45 wegen "Clips") an den
VisionAgent geroutet und endete sichtbar in "Malformed action JSON"
(Log: ``Direct JSON parsing of AI response failed``) — obwohl
``summarize_project`` die Zahl direkt aus der DB liefert.

Zwei Ursachen, beide gefixt:
1. "wie viele" fehlte in ``READ_INTENT_KEYWORDS``.
2. ``_handle_project_status_read`` (B-468) lief ERST NACH dem
   Agent-Routing — der VisionAgent war vorher dran.

Vertraege:
(a) Projekt-Statusfrage -> summarize_project, VisionAgent unberuehrt,
(b) echte Vision-Fragen routen unveraendert zum VisionAgent,
(c) die UND-Bedingung bleibt scharf: Mengenfrage OHNE Projektbezug
    bleibt beim VisionAgent,
(d) B-782/B-788-Pfade unveraendert (Regression).
"""
from __future__ import annotations

import pytest

from agents.orchestrator_agent import OrchestratorAgent


# ---------------------------------------------------------------- Prädikat
@pytest.mark.parametrize("text", [
    "Wie viele Clips hat dieses Projekt?",
    "Wieviele Szenen sind im Projekt?",
    "Zeige Projektstatus",
    "Gib mir einen Überblick",
    "How many clips does this project have?",
])
def test_status_read_intent_recognised(text):
    assert OrchestratorAgent._is_project_status_read(text) is True


@pytest.mark.parametrize("text", [
    # Mengenfrage OHNE Projektbezug -> bleibt Vision-Sache
    "Wie viele Clips sind unscharf?",
    # echte Bildinhalts-Frage
    "Was ist auf Clip 42 zu sehen?",
    "Analysiere Clip 42",
    # Aktion, kein Lesen
    "Speichere das Projekt",
])
def test_non_status_text_not_recognised(text):
    assert OrchestratorAgent._is_project_status_read(text) is False


# ---------------------------------------------------------------- Routing
class _SpyAgent:
    """Minimaler Vision-Agent-Ersatz, der jeden Aufruf protokolliert."""

    def __init__(self):
        self.name = "vision"
        self.domain = "vision"
        self.model_id = None
        self.processed: list[str] = []

    def process(self, user_text, context=None):
        self.processed.append(user_text)
        return {"agent": "vision", "action": "analyze_video",
                "result": None, "error": "Video-Analyse benötigt eine clip_id"}


@pytest.fixture()
def orch(monkeypatch):
    o = OrchestratorAgent.__new__(OrchestratorAgent)
    o.name = "orchestrator"
    o._model_manager = None
    spy = _SpyAgent()
    monkeypatch.setattr(o, "_route_to_agent", lambda _t: spy)
    o._spy = spy
    return o


def test_status_question_reaches_summarize_project(orch, monkeypatch):
    """Vertrag (a): der Kern des Bugs."""
    called = {}

    def _fake_status(user_text):
        called["text"] = user_text
        return {"agent": "orchestrator", "action": "summarize_project",
                "result": {"clips": 486}, "error": None}

    monkeypatch.setattr(orch, "_handle_project_status_read", _fake_status)

    result = orch.process("Wie viele Clips hat dieses Projekt?")

    assert orch._spy.processed == [], "VisionAgent hat die Statusfrage gekapert"
    assert result["action"] == "summarize_project"
    assert called["text"] == "Wie viele Clips hat dieses Projekt?"


def test_real_vision_question_still_routes_to_vision(orch, monkeypatch):
    """Vertrag (b) + (c): der Bypass darf nicht zu weit greifen."""
    monkeypatch.setattr(orch, "_handle_project_status_read", lambda _t: None)

    orch.process("Was ist auf Clip 42 zu sehen?")
    assert orch._spy.processed == ["Was ist auf Clip 42 zu sehen?"]

    orch.process("Wie viele Clips sind unscharf?")
    assert "Wie viele Clips sind unscharf?" in orch._spy.processed


def test_learn_and_recall_paths_unchanged():
    """Vertrag (d): B-782/B-788 bleiben unberuehrt."""
    from agents.orchestrator_agent import _has_explicit_recall_intent
    from services.brain_gateway import has_explicit_learn_intent

    assert has_explicit_learn_intent("Merke dir: Clip X ist unscharf.") is True
    assert _has_explicit_recall_intent("Was weisst du ueber Clip X?") is True
    # Die Statusfrage ist keines von beiden — sie braucht den eigenen Bypass.
    q = "Wie viele Clips hat dieses Projekt?"
    assert has_explicit_learn_intent(q) is False
    assert _has_explicit_recall_intent(q) is False
