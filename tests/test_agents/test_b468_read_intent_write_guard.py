"""B-468: Read-Intent darf keine Write-Action ausloesen.

"zeige Projektstatus" fuzzy-matchte im _route_to_registry-Loose-Pfad
"save_project" mit 64% und fuehrte einen Write aus. Fix (kombiniert):
1. Write-Guard: Write-Actions brauchen im Loose-Pfad >= 90% (sonst skip).
2. Read-Intent-Routing: Projektstatus-Lese-Anfragen gehen zu summarize_project.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from agents.orchestrator_agent import (
    OrchestratorAgent,
    WRITE_ACTIONS,
    WRITE_ACTION_FUZZY_THRESHOLD,
)


def _orch():
    return OrchestratorAgent.__new__(OrchestratorAgent)


# ---------------------------------------------------------------------------
# Write-Guard im _route_to_registry-Loose-Pfad
# ---------------------------------------------------------------------------

class TestWriteGuard:
    def test_loose_write_match_is_refused(self):
        """'projektstatus' -> 'save_project' 64% < 90% wird NICHT ausgefuehrt."""
        orch = _orch()
        reg = MagicMock()
        reg.fuzzy_match.side_effect = lambda w: (
            ("save_project", 64) if w == "projektstatus" else (None, 0)
        )
        reg.get.return_value = None
        with patch("services.action_registry.action_registry", reg):
            result = orch._route_to_registry("zeige projektstatus")
        assert result is None, "B-468: schwacher Write-Match haette None liefern muessen"
        reg.execute.assert_not_called()

    def test_exact_write_match_still_executes(self):
        """Quasi-exakter Write-Match (>= 90%) laeuft weiter durch."""
        orch = _orch()
        reg = MagicMock()
        reg.fuzzy_match.side_effect = lambda w: (
            ("save_project", 96) if w == "save_project" else (None, 0)
        )
        reg.get.return_value = None
        reg.execute.return_value = {"status": "ok"}
        with patch("services.action_registry.action_registry", reg):
            result = orch._route_to_registry("save_project bitte")
        assert result is not None
        assert result["action"] == "save_project"
        reg.execute.assert_called_once()

    def test_non_write_loose_match_still_executes(self):
        """Nicht-Write Loose-Match (analyze_audio 60%) bleibt erlaubt."""
        orch = _orch()
        assert "analyze_audio" not in WRITE_ACTIONS
        reg = MagicMock()
        reg.fuzzy_match.side_effect = lambda w: (
            ("analyze_audio", 60) if w == "analyse" else (None, 0)
        )
        reg.get.return_value = None
        reg.execute.return_value = {"status": "ok"}
        with patch("services.action_registry.action_registry", reg):
            result = orch._route_to_registry("analyse starten")
        assert result is not None
        assert result["action"] == "analyze_audio"
        reg.execute.assert_called_once()

    def test_threshold_constant(self):
        assert WRITE_ACTION_FUZZY_THRESHOLD == 90
        assert "save_project" in WRITE_ACTIONS


# ---------------------------------------------------------------------------
# Read-Intent-Routing zu summarize_project
# ---------------------------------------------------------------------------

class TestReadIntentRouting:
    def test_zeige_projektstatus_routes_to_summarize(self):
        orch = _orch()
        reg = MagicMock()
        reg.execute.return_value = {"summary": "..."}
        with patch("services.action_registry.action_registry", reg):
            result = orch._handle_project_status_read("zeige Projektstatus")
        assert result is not None
        assert result["action"] == "summarize_project"
        assert result["error"] is None
        reg.execute.assert_called_once_with("summarize_project", {})

    def test_projekt_ueberblick_routes_to_summarize(self):
        orch = _orch()
        reg = MagicMock()
        reg.execute.return_value = {"summary": "..."}
        with patch("services.action_registry.action_registry", reg):
            result = orch._handle_project_status_read("zeig mir den Projekt Ueberblick")
        assert result is not None
        assert result["action"] == "summarize_project"

    def test_non_read_intent_returns_none(self):
        """Befehle ohne Read+Projekt-Bezug werden NICHT abgefangen."""
        orch = _orch()
        reg = MagicMock()
        with patch("services.action_registry.action_registry", reg):
            assert orch._handle_project_status_read("analysiere video 3") is None
            assert orch._handle_project_status_read("speichere das projekt") is None
            assert orch._handle_project_status_read("zeige timeline") is None
        reg.execute.assert_not_called()

    def test_execute_error_is_captured(self):
        orch = _orch()
        reg = MagicMock()
        reg.execute.side_effect = RuntimeError("kein Projekt offen")
        with patch("services.action_registry.action_registry", reg):
            result = orch._handle_project_status_read("zeige Projektstatus")
        assert result is not None
        assert result["action"] == "summarize_project"
        assert "kein Projekt offen" in result["error"]
