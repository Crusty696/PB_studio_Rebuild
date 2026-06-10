"""B-411: Tool-loser Chat-Fallback darf keinen Action-Erfolg vortäuschen.

Wenn ein Aktions-Befehl ("sperre cut id 99999") bis zum Chat-Fallback durchläuft
(kein Agent/keine Action hat ihn ausgeführt, Modell ohne Tool-Support), antwortete
das LLM frei und halluzinierte Erfolg ("Verstanden. Ich sperre Cut ID 99999."),
obwohl nichts passierte. Fix: solche Befehle werden transparent abgelehnt statt an
das frei-halluzinierende chat() zu gehen.
"""

from __future__ import annotations

from unittest.mock import patch

from agents.orchestrator_agent import OrchestratorAgent, _GENERAL_SYSTEM_PROMPT


def _orch():
    return OrchestratorAgent.__new__(OrchestratorAgent)


class TestLooksLikeActionCommand:
    def test_action_commands_detected(self):
        o = _orch()
        for t in ["sperre cut id 99999", "lösche projekt", "exportiere timeline",
                  "Generiere Proxys", "  entferne clip 3"]:
            assert o._looks_like_action_command(t) is True, t

    def test_questions_not_detected(self):
        o = _orch()
        for t in ["wie sperre ich einen cut?", "kannst du mir erklären wie export geht",
                  "was ist auf video 1?", "warum ist die timeline leer", ""]:
            assert o._looks_like_action_command(t) is False, t


class TestProcessFallbackGuard:
    def test_action_command_returns_not_executable_at_fallback(self):
        o = _orch()
        o._model_manager = None
        with patch.object(o, "_detect_analyze_all", return_value=False), \
             patch.object(o, "_detect_multi_step", return_value=False), \
             patch.object(o, "_detect_compound_actions", return_value=[]), \
             patch.object(o, "_handle_cross_modal_clip_match", return_value=None), \
             patch.object(o, "_handle_destructive_intent", return_value=None), \
             patch.object(o, "_handle_project_status_read", return_value=None), \
             patch.object(o, "_route_to_agent", return_value=None), \
             patch.object(o, "_route_to_registry", return_value=None), \
             patch.object(o, "_chat_with_tools_loop", return_value=None) as mock_chat:
            result = o.process("sperre cut id 99999")
        assert result["action"] == "action_not_executable"
        assert "nicht direkt ausführen" in result["message"]
        assert "nichts verändert" in result["message"]
        mock_chat.assert_called_once()  # tool-loop versucht, aber kein Erfolg vorgetäuscht

    def test_question_falls_through_to_chat(self):
        """Eine Frage (kein Action-Befehl) geht weiter zum normalen LLM-Chat."""
        o = _orch()
        o._model_manager = None
        fake_svc = type("S", (), {"is_ready": True,
                                  "chat": staticmethod(lambda **k: "Antwort-Text")})()
        with patch.object(o, "_detect_analyze_all", return_value=False), \
             patch.object(o, "_detect_multi_step", return_value=False), \
             patch.object(o, "_detect_compound_actions", return_value=[]), \
             patch.object(o, "_handle_cross_modal_clip_match", return_value=None), \
             patch.object(o, "_handle_destructive_intent", return_value=None), \
             patch.object(o, "_handle_project_status_read", return_value=None), \
             patch.object(o, "_route_to_agent", return_value=None), \
             patch.object(o, "_route_to_registry", return_value=None), \
             patch.object(o, "_chat_with_tools_loop", return_value=None), \
             patch("agents.orchestrator_agent.OllamaService") as mock_os:
            mock_os.get.return_value = fake_svc
            result = o.process("wie sperre ich einen cut?")
        assert result["action"] == "chat"
        assert result["message"] == "Antwort-Text"


def test_b411_general_prompt_forbids_claiming_actions():
    assert "KEINE Aktionen" in _GENERAL_SYSTEM_PROMPT
    assert "Behaupte NIEMALS" in _GENERAL_SYSTEM_PROMPT
