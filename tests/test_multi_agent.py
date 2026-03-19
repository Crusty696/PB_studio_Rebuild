"""
Tests für das Multi-Agenten-System und Fuzzy-Matching.

SEKTOR 4: Simuliert User-Input mit absichtlichen Tippfehlern.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


# ===========================================================================
# Test 1: Fuzzy-Matching im ActionRegistry
# ===========================================================================

class TestFuzzyMatching:
    """Testet, dass ungenaue Aktionsnamen korrekt aufgelöst werden."""

    def setup_method(self):
        from services.action_registry import ActionRegistry
        self.registry = ActionRegistry()
        # Registriere Test-Aktionen
        self.registry.register_function(
            name="analyze_audio",
            description="Analysiert Audio",
            handler=lambda track_id=1: {"bpm": 120, "track_id": track_id},
            param_schema={"type": "object", "properties": {"track_id": {"type": "integer"}}, "required": ["track_id"]},
        )
        self.registry.register_function(
            name="analyze_video",
            description="Analysiert Video",
            handler=lambda clip_id=1: {"scenes": 5, "clip_id": clip_id},
            param_schema={"type": "object", "properties": {"clip_id": {"type": "integer"}}, "required": ["clip_id"]},
        )
        self.registry.register_function(
            name="separate_stems",
            description="Trennt Stems",
            handler=lambda track_id=1: {"stems": 4, "track_id": track_id},
            param_schema={"type": "object", "properties": {"track_id": {"type": "integer"}}, "required": ["track_id"]},
        )
        self.registry.register_function(
            name="auto_edit",
            description="Auto-Edit",
            handler=lambda audio_track_id=1: {"cuts": 10},
        )
        self.registry.register_function(
            name="export_timeline",
            description="Exportiert Timeline",
            handler=lambda project_id=1: {"exported": True},
        )

    def test_exact_match(self):
        """Exakte Aktion wird direkt gefunden."""
        name, score = self.registry.fuzzy_match("analyze_audio")
        assert name == "analyze_audio"
        assert score == 100

    def test_fuzzy_analyse_files(self):
        """'analyse_files' soll zu 'analyze_audio' oder 'analyze_video' matchen."""
        name, score = self.registry.fuzzy_match("analyse_files")
        assert name is not None
        assert "analyze" in name
        assert score >= 55

    def test_fuzzy_analyz_audio(self):
        """Tippfehler 'analyz_audio' → 'analyze_audio'."""
        name, score = self.registry.fuzzy_match("analyz_audio")
        assert name == "analyze_audio"
        assert score >= 70

    def test_fuzzy_seperate_stems(self):
        """Häufiger Tippfehler 'seperate_stems' → 'separate_stems'."""
        name, score = self.registry.fuzzy_match("seperate_stems")
        assert name == "separate_stems"
        assert score >= 80

    def test_fuzzy_export_timelien(self):
        """Tippfehler 'export_timelien' → 'export_timeline'."""
        name, score = self.registry.fuzzy_match("export_timelien")
        assert name == "export_timeline"
        assert score >= 70

    def test_no_match_for_gibberish(self):
        """Komplett unbekannter Text soll None zurückgeben."""
        name, score = self.registry.fuzzy_match("xyzqwerty_foobar")
        assert name is None

    def test_resolve_fuzzy(self):
        """resolve() soll auch bei ungenauem Namen die ActionDef zurückgeben."""
        action_def = self.registry.resolve("analyse_files")
        assert action_def is not None
        assert "analyze" in action_def.name

    def test_execute_with_fuzzy_name(self):
        """execute() soll auch mit ungenauem Namen funktionieren."""
        result = self.registry.execute("analyz_audio", {"track_id": 42})
        assert result["bpm"] == 120
        assert result["track_id"] == 42

    def test_tolerant_params(self):
        """Unbekannte Parameter sollen still entfernt werden."""
        result = self.registry.execute("analyze_audio", {
            "track_id": 1,
            "unknown_param": "should_be_removed",
            "another_junk": 999,
        })
        assert result["bpm"] == 120


# ===========================================================================
# Test 2: Orchestrator Routing
# ===========================================================================

class TestOrchestratorRouting:
    """Testet, dass der Orchestrator korrekt an Agenten routet."""

    def setup_method(self):
        from agents.orchestrator_agent import OrchestratorAgent
        self.orch = OrchestratorAgent()

    def test_detect_analyze_all_exact(self):
        """Exakter Text wird erkannt."""
        assert self.orch._detect_analyze_all("analysiere alle importierten Dateien")

    def test_detect_analyze_all_with_typos(self):
        """Text mit Tippfehlern wird erkannt (Fuzzy)."""
        assert self.orch._detect_analyze_all("analysiere alle File die improtiert sind")

    def test_detect_analyze_all_english(self):
        """Englische Variante."""
        assert self.orch._detect_analyze_all("analyze all imported files")

    def test_route_audio_agent(self):
        """Audio-Keywords routen zum AudioAgent."""
        agent = self.orch._route_to_agent("Analysiere den Audio-Track")
        assert agent is not None
        assert agent.name == "audio"

    def test_route_vision_agent(self):
        """Video-Keywords routen zum VisionAgent."""
        agent = self.orch._route_to_agent("Analysiere den Video-Clip")
        assert agent is not None
        assert agent.name == "vision"

    def test_route_editor_agent(self):
        """Editor-Keywords routen zum EditorAgent."""
        agent = self.orch._route_to_agent("Exportiere die Timeline")
        assert agent is not None
        assert agent.name == "editor"


# ===========================================================================
# Test 3: Agenten can_handle Scores
# ===========================================================================

class TestAgentScoring:
    """Testet die Konfidenz-Scores der spezialisierten Agenten."""

    def test_audio_agent_high_score(self):
        from agents.audio_agent import AudioAgent
        agent = AudioAgent()
        score = agent.can_handle("Analysiere den Audio Track und zeige BPM")
        assert score > 0.3

    def test_audio_agent_zero_for_unrelated(self):
        from agents.audio_agent import AudioAgent
        agent = AudioAgent()
        score = agent.can_handle("Wie wird das Wetter morgen?")
        assert score == 0.0

    def test_vision_agent_high_score(self):
        from agents.vision_agent import VisionAgent
        agent = VisionAgent()
        score = agent.can_handle("Analysiere die Szenen im Video")
        assert score > 0.3

    def test_editor_agent_high_score(self):
        from agents.editor_agent import EditorAgent
        agent = EditorAgent()
        score = agent.can_handle("Auto-Edit auf der Timeline")
        assert score > 0.3


# ===========================================================================
# Test 4: ModelManager
# ===========================================================================

class TestModelManager:
    """Testet den ModelManager (ohne echtes Modell-Laden)."""

    def test_initial_state(self):
        from services.local_agent_service import ModelManager
        mm = ModelManager(device="cpu")
        assert mm.current_model_id is None
        assert mm.is_loaded is False

    def test_unload_empty(self):
        """Unload auf leeren Manager soll nicht crashen."""
        from services.local_agent_service import ModelManager
        mm = ModelManager(device="cpu")
        mm.unload()  # Sollte ohne Fehler durchlaufen
        assert mm.is_loaded is False


# ===========================================================================
# Test 5: Der kritische Tippfehler-Test (Sektor 4)
# ===========================================================================

class TestTypoSimulation:
    """Simuliert: 'analysiere alle File die improtiert sind'

    Das System muss das Fuzzy-erkennen und an analyze_audio/analyze_video routen.
    """

    def test_typo_input_detected_by_orchestrator(self):
        """Der Orchestrator erkennt den Tippfehler-Input als 'Analysiere alle'."""
        from agents.orchestrator_agent import OrchestratorAgent
        orch = OrchestratorAgent()
        detected = orch._detect_analyze_all("analysiere alle File die improtiert sind")
        assert detected, "Tippfehler-Input wurde nicht als 'Analysiere alle' erkannt!"

    def test_fuzzy_analyse_to_analyze(self):
        """'analyse' matched zu 'analyze_audio' oder 'analyze_video'."""
        from services.action_registry import ActionRegistry
        reg = ActionRegistry()
        reg.register_function("analyze_audio", "Audio", lambda track_id=1: {})
        reg.register_function("analyze_video", "Video", lambda clip_id=1: {})

        name, score = reg.fuzzy_match("analyse")
        assert name is not None
        assert score >= 55


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
