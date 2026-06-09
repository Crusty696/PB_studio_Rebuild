"""B-464: Destruktive NL-Befehle muessen den Confirm-Gate erreichen.

"loesche alle Videos" wurde vom VisionAgent abgefangen (Score 0.45 wegen
"Videos") und erreichte nie den Confirm-Gate im Action-Registry. Fix: ein
Pre-Router VOR dem Agent-Routing erkennt destruktive Intent und ruft die
destruktive Action ohne confirm auf -> der Gate schlaegt an.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agents.orchestrator_agent import OrchestratorAgent
from agents.vision_agent import VisionAgent


def _orch():
    return OrchestratorAgent.__new__(OrchestratorAgent)


def _patched_registry(execute_side_effect=None):
    reg = MagicMock()
    if execute_side_effect is not None:
        reg.execute.side_effect = execute_side_effect
    return reg


class TestDestructiveIntent:
    def test_loesche_alle_videos_hits_confirm_gate(self):
        orch = _orch()
        gate_err = ValueError(
            "Confirmation required for destructive action 'delete_media'"
        )
        reg = _patched_registry(execute_side_effect=gate_err)
        with patch("services.action_registry.action_registry", reg):
            result = orch._handle_destructive_intent("loesche alle Videos")
        assert result is not None
        assert result["action"] == "delete_media"
        assert result["result"] is None
        assert "Sicherheitsabfrage" in result["message"]
        assert "Confirmation required" in result["error"]
        reg.execute.assert_called_once_with("delete_media", {})

    def test_leere_timeline_routes_to_clear_timeline(self):
        orch = _orch()
        reg = _patched_registry(
            execute_side_effect=ValueError("Confirmation required for destructive action 'clear_timeline'")
        )
        with patch("services.action_registry.action_registry", reg):
            result = orch._handle_destructive_intent("leere die Timeline")
        assert result["action"] == "clear_timeline"
        reg.execute.assert_called_once_with("clear_timeline", {})

    def test_loesche_projekt_falls_through(self):
        """Projekt-Loeschung hat KEINE registrierte Action -> kein Pre-Route."""
        orch = _orch()
        reg = _patched_registry()
        with patch("services.action_registry.action_registry", reg):
            assert orch._handle_destructive_intent("loesche das Projekt") is None
        reg.execute.assert_not_called()

    def test_non_destructive_returns_none(self):
        orch = _orch()
        reg = _patched_registry()
        with patch("services.action_registry.action_registry", reg):
            assert orch._handle_destructive_intent("analysiere alle Videos") is None
            assert orch._handle_destructive_intent("zeige alle Medien") is None
        reg.execute.assert_not_called()

    def test_destructive_verb_without_clear_target_returns_none(self):
        """Verb ohne eindeutiges Bulk/Timeline/Projekt-Ziel -> normales Routing."""
        orch = _orch()
        reg = _patched_registry()
        with patch("services.action_registry.action_registry", reg):
            # "audio" (singular) ist nicht in DESTRUCTIVE_MEDIA_WORDS, kein bulk
            assert orch._handle_destructive_intent("loesche das audio") is None
            assert orch._handle_destructive_intent("entferne den Effekt") is None
        reg.execute.assert_not_called()

    def test_confirmed_delete_executes(self):
        """Wenn der Gate nicht anschlaegt (z.B. bestaetigt), wird das Ergebnis durchgereicht."""
        orch = _orch()
        reg = _patched_registry()
        reg.execute.return_value = {"status": "ok", "deleted": 3}
        with patch("services.action_registry.action_registry", reg):
            result = orch._handle_destructive_intent("loesche alle Medien")
        assert result["action"] == "delete_media"
        assert result["result"] == {"status": "ok", "deleted": 3}
        assert result["error"] is None


class TestPrecedence:
    def test_vision_would_grab_without_fix(self):
        """Dokumentiert das Routing-Problem: VisionAgent scort 0.45 fuer den Befehl."""
        assert VisionAgent().can_handle("loesche alle Videos") >= 0.3

    def test_process_routes_destructive_before_agents(self):
        """process() ruft den destruktiven Pre-Router VOR dem Agent-Routing."""
        orch = _orch()
        orch._model_manager = None
        sentinel = {"agent": "orchestrator", "action": "delete_media",
                    "result": None, "message": "Sicherheitsabfrage", "error": "gate"}
        with patch.object(orch, "_detect_analyze_all", return_value=False), \
             patch.object(orch, "_detect_multi_step", return_value=False), \
             patch.object(orch, "_detect_compound_actions", return_value=[]), \
             patch.object(orch, "_handle_cross_modal_clip_match", return_value=None), \
             patch.object(orch, "_handle_destructive_intent", return_value=sentinel) as mock_destr, \
             patch.object(orch, "_route_to_agent") as mock_route:
            result = orch.process("loesche alle Videos")
        mock_destr.assert_called_once()
        mock_route.assert_not_called()
        assert result["action"] == "delete_media"
