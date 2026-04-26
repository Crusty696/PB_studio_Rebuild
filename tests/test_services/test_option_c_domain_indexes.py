"""Cycle 14 / Option C: Domain-Index Re-Exports verfügbar."""
from __future__ import annotations


# ── services.audio ─────────────────────────────────────────────────────────


def test_audio_index_exposes_core_classes():
    from services.audio import (
        AudioAnalyzer,
        BeatAnalysisService,
        OnsetRhythmService,
        StructureDetectionService,
        DEFAULT_SR,
        HOP_LENGTH,
        track_lock,
    )
    assert AudioAnalyzer.__module__ == "services.audio_service"
    assert BeatAnalysisService.__module__ == "services.beat_analysis_service"
    assert isinstance(DEFAULT_SR, int)
    assert isinstance(HOP_LENGTH, int)
    assert callable(track_lock)


def test_audio_index_all_attribute_complete():
    import services.audio as audio_pkg
    expected = {
        "AudioAnalyzer", "BeatAnalysisService", "OnsetRhythmService",
        "StructureDetectionService", "track_lock",
        "PercussiveOnset", "RhythmAnalysis",
        "StructureResult", "StructureSegmentResult",
        "DEFAULT_SR", "HOP_LENGTH",
    }
    assert expected.issubset(set(audio_pkg.__all__))


# ── services.video ─────────────────────────────────────────────────────────


def test_video_index_exposes_core_classes():
    from services.video import (
        VideoAnalyzer,
        SceneInfo,
        VectorDBService,
        detect_scenes,
        text_to_embedding,
    )
    assert VideoAnalyzer.__module__ == "services.video_service"
    assert SceneInfo.__module__ == "services.video_analysis_service"
    assert callable(detect_scenes)
    assert callable(text_to_embedding)


# ── services.agent ─────────────────────────────────────────────────────────


def test_agent_index_exposes_core_classes():
    from services.agent import (
        ActionRegistry,
        action_registry,
        LocalAgentService,
        OllamaClient,
    )
    assert ActionRegistry.__module__ == "services.action_registry"
    assert isinstance(action_registry, ActionRegistry)


# ── Backward-Compat: alte Pfade weiterhin funktional ──────────────────────


def test_legacy_import_paths_still_work():
    """Bestehende Imports brechen NICHT durch die neuen Indexe."""
    from services.audio_service import AudioAnalyzer as A1
    from services.audio import AudioAnalyzer as A2
    assert A1 is A2  # Selbe Klasse, zwei Pfade


def test_video_legacy_imports_still_work():
    from services.video_service import VideoAnalyzer as V1
    from services.video import VideoAnalyzer as V2
    assert V1 is V2


def test_agent_legacy_imports_still_work():
    from services.action_registry import ActionRegistry as AR1
    from services.agent import ActionRegistry as AR2
    assert AR1 is AR2


def test_services_readme_exists():
    """README.md dokumentiert die neue Struktur."""
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    readme = repo_root / "services" / "README.md"
    assert readme.exists()
    content = readme.read_text(encoding="utf-8")
    assert "services.audio" in content
    assert "services.video" in content
    assert "services.agent" in content
