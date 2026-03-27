"""
Tests fuer agents/orchestrator_agent.py

Getestet: _detect_compound_actions(), _handle_compound_actions(),
          _extract_id_from_text(), _detect_analyze_all(), _detect_multi_step(),
          COMPOUND_ACTION_MAP Eintraege.
"""

import pytest
from unittest.mock import patch, MagicMock, call

from agents.orchestrator_agent import OrchestratorAgent, COMPOUND_ACTION_MAP


# ---------------------------------------------------------------------------
# _extract_id_from_text() Tests
# ---------------------------------------------------------------------------

class TestExtractIdFromText:
    def setup_method(self):
        self.orch = OrchestratorAgent.__new__(OrchestratorAgent)

    @pytest.mark.parametrize("text,expected", [
        ("Analysiere Video 3", 3),
        ("Track ID 42 analysieren", 42),
        ("clip 100", 100),
        ("kein proxy fuer 7 bitte", 7),
    ])
    def test_extracts_first_number(self, text, expected):
        """Erste Zahl im Text wird als ID extrahiert."""
        result = self.orch._extract_id_from_text(text)
        assert result == expected

    def test_returns_none_for_no_number(self):
        """Gibt None zurueck wenn kein Zahlenwert im Text."""
        result = self.orch._extract_id_from_text("analysiere alles")
        assert result is None

    def test_extracts_from_complex_sentence(self):
        """Extrahiert ID aus komplexem Satz."""
        result = self.orch._extract_id_from_text("erstelle proxy fuer video clip nummer 15 bitte")
        assert result == 15


# ---------------------------------------------------------------------------
# _detect_compound_actions() Tests
# ---------------------------------------------------------------------------

class TestDetectCompoundActions:
    def setup_method(self):
        self.orch = OrchestratorAgent.__new__(OrchestratorAgent)

    def test_detects_proxy_keyword(self):
        """'proxy' Keyword wird zu 'create_proxy' gemappt."""
        actions = self.orch._detect_compound_actions("erstelle proxy fuer alle videos")
        assert "create_proxy" in actions

    def test_detects_stems_keyword(self):
        """'stems' Keyword wird zu 'separate_stems' gemappt."""
        actions = self.orch._detect_compound_actions("trenne alle stems bitte")
        assert "separate_stems" in actions

    def test_detects_vocals_keyword(self):
        """'vocals' Keyword triggert separate_stems."""
        actions = self.orch._detect_compound_actions("extrahiere vocals aus dem track")
        assert "separate_stems" in actions

    def test_detects_separation_keyword(self):
        """'separier' Keyword triggert separate_stems."""
        actions = self.orch._detect_compound_actions("separiere bitte die spuren")
        assert "separate_stems" in actions

    def test_detects_multiple_actions_in_one_sentence(self):
        """Zwei Keywords in einem Satz ergeben zwei Actions."""
        actions = self.orch._detect_compound_actions(
            "erstelle proxy und trenne stems fuer alle dateien"
        )
        assert "create_proxy" in actions
        assert "separate_stems" in actions

    def test_returns_empty_for_unrelated_text(self):
        """Kein Keyword -> leere Liste."""
        actions = self.orch._detect_compound_actions("guten morgen wie geht es dir")
        assert actions == []

    def test_no_duplicate_actions(self):
        """Dieselbe Action wird nur einmal zurueckgegeben, auch bei mehreren Keywords."""
        actions = self.orch._detect_compound_actions(
            "trenne stems und vocals und separation bitte"
        )
        stem_count = actions.count("separate_stems")
        assert stem_count == 1

    def test_all_compound_action_map_entries_are_triggerable(self):
        """Jeder Eintrag im COMPOUND_ACTION_MAP hat mindestens ein triggerbares Keyword."""
        for entry in COMPOUND_ACTION_MAP:
            action_name = entry["action"]
            first_keyword = entry["keywords"][0]
            actions = self.orch._detect_compound_actions(
                f"bitte {first_keyword} ausfuehren"
            )
            assert action_name in actions, \
                f"COMPOUND_ACTION_MAP Eintrag '{action_name}' nicht triggerbar mit '{first_keyword}'"


# ---------------------------------------------------------------------------
# _handle_compound_actions() Tests
# WICHTIG: action_registry wird per local import geladen (from services.action_registry
# import action_registry), daher muss der Patch auf das Quell-Modul zeigen!
# ---------------------------------------------------------------------------

class TestHandleCompoundActions:
    def setup_method(self):
        self.orch = OrchestratorAgent.__new__(OrchestratorAgent)
        self.orch.name = "orchestrator"

    def test_handle_compound_returns_multi_action_result(self):
        """_handle_compound_actions() gibt Multi-Action-Dict zurueck."""
        mock_registry = MagicMock()
        mock_registry.execute.return_value = {"status": "ok"}

        # Patch auf das Quell-Modul, da action_registry lokal importiert wird
        with patch("services.action_registry.action_registry", mock_registry):
            result = self.orch._handle_compound_actions(
                ["create_proxy", "separate_stems"],
            )

        assert result["action"] == "multi"
        assert "actions" in result
        assert len(result["actions"]) == 2

    def test_handle_compound_counts_successes(self):
        """Anzahl der erfolgreichen Actions steht in der Nachricht (X/Y)."""
        mock_registry = MagicMock()
        mock_registry.execute.return_value = {"status": "queued"}

        with patch("services.action_registry.action_registry", mock_registry):
            result = self.orch._handle_compound_actions(
                ["create_proxy"],
            )

        assert result["agent"] == "orchestrator"
        assert "1/1" in result["message"]

    def test_handle_compound_records_errors_in_result(self):
        """Fehler im Handler werden im 'error'-Feld und actions[].error festgehalten."""
        mock_registry = MagicMock()
        mock_registry.execute.side_effect = RuntimeError("Action fehlgeschlagen")

        with patch("services.action_registry.action_registry", mock_registry):
            result = self.orch._handle_compound_actions(
                ["create_proxy"],
            )

        assert result["error"] is not None
        assert "create_proxy" in result["error"]
        assert result["actions"][0]["error"] is not None

    def test_handle_compound_partial_failure(self):
        """Bei gemischtem Ergebnis zeigt message X/Y an."""
        mock_registry = MagicMock()
        mock_registry.execute.side_effect = [
            {"status": "ok"},             # create_proxy erfolgreich
            RuntimeError("stems failed"), # separate_stems fehlgeschlagen
        ]

        with patch("services.action_registry.action_registry", mock_registry):
            result = self.orch._handle_compound_actions(
                ["create_proxy", "separate_stems"],
            )

        assert "1/2" in result["message"]
        assert result["error"] is not None


# ---------------------------------------------------------------------------
# _detect_analyze_all() Tests
# ---------------------------------------------------------------------------

class TestDetectAnalyzeAll:
    def setup_method(self):
        self.orch = OrchestratorAgent.__new__(OrchestratorAgent)

    @pytest.mark.parametrize("text", [
        "analysiere alle importierten files",
        "analyze all imported files",
        "alle files analysieren",
        "alles analysieren",
        "alle files",
    ])
    def test_detects_analyze_all_keywords(self, text):
        assert self.orch._detect_analyze_all(text) is True

    def test_does_not_detect_unrelated_text(self):
        assert self.orch._detect_analyze_all("erstelle proxy fuer clip 3") is False


# ---------------------------------------------------------------------------
# _detect_multi_step() Tests
# ---------------------------------------------------------------------------

class TestDetectMultiStep:
    def setup_method(self):
        self.orch = OrchestratorAgent.__new__(OrchestratorAgent)

    @pytest.mark.parametrize("text", [
        "was passiert im bild und was wird gesagt",
        "zeig mir bild und ton gleichzeitig",
        "analysiere bild und ton von clip 5",
        "bild und ton analyse",
    ])
    def test_detects_multi_step_patterns(self, text):
        assert self.orch._detect_multi_step(text) is True

    def test_does_not_detect_single_domain(self):
        assert self.orch._detect_multi_step("analysiere das bild") is False
        assert self.orch._detect_multi_step("transkribiere den ton") is False


# ---------------------------------------------------------------------------
# process() Routing Tests
# ---------------------------------------------------------------------------

class TestOrchestratorProcess:
    def _make_orchestrator(self):
        """Erstellt OrchestratorAgent mit gemockten Sub-Agenten."""
        orch = OrchestratorAgent.__new__(OrchestratorAgent)
        orch._agents = []
        orch._model_manager = None
        return orch

    def test_process_returns_dict_with_required_keys(self):
        """process() gibt immer einen Dict mit 'agent', 'action', 'result' zurueck.
        Fallback-Pfad: kein Agent, kein Registry-Match -> 'action': 'none'.
        """
        orch = self._make_orchestrator()

        # Sub-Agenten-Liste ist leer -> _route_to_agent gibt None zurueck.
        # _route_to_registry mocken, damit kein echter Registry-Zugriff stattfindet.
        with patch.object(orch, "_route_to_registry", return_value=None):
            result = orch.process("hallo wie geht es dir heute")

        assert "agent" in result
        assert "action" in result
        assert "result" in result

    def test_process_detect_analyze_all_triggers_handle_all(self):
        """'analysiere alle' triggert _handle_analyze_all."""
        orch = self._make_orchestrator()

        expected = {
            "agent": "orchestrator", "action": "multi",
            "result": None, "message": "ok", "error": None,
            "actions": [], "params": {},
        }
        with patch.object(orch, "_handle_analyze_all", return_value=expected) as mock_all:
            result = orch.process("analysiere alle importierten files")

        mock_all.assert_called_once()

    def test_process_compound_actions_triggers_handle_compound(self):
        """Compound-Keywords triggern _handle_compound_actions."""
        orch = self._make_orchestrator()

        expected = {
            "agent": "orchestrator", "action": "multi",
            "result": None, "message": "ok", "error": None,
            "actions": [], "params": {},
        }
        with patch.object(orch, "_handle_compound_actions", return_value=expected) as mock_comp:
            orch.process("erstelle proxy und trenne stems fuer alle clips")

        mock_comp.assert_called_once()

    def test_can_handle_returns_1(self):
        """can_handle() gibt immer 1.0 zurueck (Orchestrator ist fuer alles zustaendig)."""
        orch = self._make_orchestrator()
        assert orch.can_handle("irgendwas") == 1.0
