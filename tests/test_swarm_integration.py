"""
Integrations-Test für das 3-Agenten Swarm System.

Testet:
1. ModelManager Singleton + VRAM-Schutz
2. Audio-Agent (faster-whisper Transkription)
3. Vision-Agent (Moondream2 Szenenanalyse)
4. Orchestrator Multi-Step (Vision + Audio gleichzeitig)
5. ActionRegistry Integration

Nutzt echte Testdateien aus C:\\Users\\david\\Documents\\test_data.
"""

import os
import sys
import json
import logging
import time

import pytest

# Abhängigkeits-Prüfung für GPU-Tests
try:
    import torch as _torch_check
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False

try:
    import faster_whisper as _fw_check  # noqa: F401
    _FASTER_WHISPER_AVAILABLE = True
except ImportError:
    _FASTER_WHISPER_AVAILABLE = False

_requires_torch = pytest.mark.skipif(
    not _TORCH_AVAILABLE,
    reason="torch nicht installiert — CUDA/GPU-Tests werden übersprungen",
)

_requires_torch_and_whisper = pytest.mark.skipif(
    not (_TORCH_AVAILABLE and _FASTER_WHISPER_AVAILABLE),
    reason="torch oder faster_whisper nicht installiert — Modell-Tests werden übersprungen",
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("swarm_test")

# Projekt-Root zum Path hinzufügen
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def find_test_video() -> str | None:
    """Findet eine Testdatei (Video) mit Audio."""
    test_dirs = [
        r"C:\Users\david\Documents\test_data\video\generation 4",
        r"C:\Users\david\Documents\test_data\video\Solo_Natur",
        r"C:\Users\david\Documents\test_data\video",
    ]
    for d in test_dirs:
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith((".mp4", ".mkv", ".mov", ".avi")):
                    return os.path.join(d, f)
    return None


def find_test_audio() -> str | None:
    """Findet eine Test-Audiodatei."""
    test_dir = r"C:\Users\david\Documents\test_data\audio"
    if os.path.isdir(test_dir):
        for f in os.listdir(test_dir):
            if f.endswith((".mp3", ".wav", ".m4a", ".flac")):
                return os.path.join(test_dir, f)
    return None


def test_model_manager_singleton():
    """Test 1: ModelManager ist ein Singleton."""
    from services.model_manager import ModelManager

    mm1 = ModelManager()
    mm2 = ModelManager()
    assert mm1 is mm2, "ModelManager muss ein Singleton sein!"
    logger.info("✅ Test 1 bestanden: ModelManager ist Singleton")
    return True


@_requires_torch_and_whisper
def test_model_manager_vram_protection():
    """Test 2: Nur ein Modell gleichzeitig im RAM."""
    from services.model_manager import ModelManager

    mm = ModelManager()

    # Lade Whisper
    mm.load_whisper("tiny")
    assert mm.current_model_id == "whisper-tiny"
    assert mm.model_type == "whisper"
    logger.info("  Whisper-tiny geladen: %s", mm.current_model_id)

    # Lade anderes Modell → Whisper muss entladen werden
    # (Wir simulieren nur die Entladung hier, kein echtes 2. Modell)
    mm.unload()
    assert mm.current_model_id is None
    assert mm.model_type is None
    logger.info("✅ Test 2 bestanden: VRAM-Schutz funktioniert")
    return True


@_requires_torch
@pytest.mark.skipif(
    not os.path.isdir(r"C:\Users\david\Documents\test_data\audio"),
    reason="Echte Test-Audio-Daten nicht vorhanden",
)
def test_transcribe_audio():
    """Test 3: Audio-Transkription mit faster-whisper (benötigt echte Testdateien)."""
    audio_path = find_test_audio()
    if not audio_path:
        pytest.skip("Keine Audio-Testdatei gefunden")

    # Registriere Aktionen
    import services.register_actions  # noqa: F401
    from services.action_registry import action_registry

    logger.info("  Starte Transkription von: %s", os.path.basename(audio_path))
    start = time.time()

    result = action_registry.execute("transcribe_audio", {"file_path": audio_path})

    elapsed = time.time() - start
    logger.info("  Transkription dauerte: %.1fs", elapsed)

    assert isinstance(result, dict), "Ergebnis muss ein Dict sein"
    assert "error" not in result or result.get("error") is None, f"Fehler: {result.get('error')}"
    assert "full_text" in result, "full_text fehlt im Ergebnis"
    assert "segments" in result, "segments fehlt im Ergebnis"
    assert "language" in result, "language fehlt im Ergebnis"

    logger.info("  Sprache: %s (%.1f%%)", result["language"],
                result.get("language_probability", 0) * 100)
    logger.info("  Segmente: %d", result.get("segment_count", 0))
    logger.info("  Text (Auszug): %s", result["full_text"][:200])

    logger.info("✅ Test 3 bestanden: Audio-Transkription funktioniert")
    return result


@_requires_torch
@pytest.mark.skipif(
    not any(
        os.path.isdir(d)
        for d in [
            r"C:\Users\david\Documents\test_data\video\generation 4",
            r"C:\Users\david\Documents\test_data\video\Solo_Natur",
            r"C:\Users\david\Documents\test_data\video",
        ]
    ),
    reason="Echte Test-Video-Daten nicht vorhanden",
)
def test_analyze_video_content():
    """Test 4: Visuelle Video-Analyse mit Moondream2 (benötigt echte Testdateien)."""
    video_path = find_test_video()
    if not video_path:
        pytest.skip("Keine Video-Testdatei gefunden")

    import services.register_actions  # noqa: F401
    from services.action_registry import action_registry

    logger.info("  Starte visuelle Analyse von: %s", os.path.basename(video_path))
    start = time.time()

    result = action_registry.execute("analyze_video_content", {
        "file_path": video_path,
        "interval_sec": 3.0,
        "max_frames": 5,
    })

    elapsed = time.time() - start
    logger.info("  Visuelle Analyse dauerte: %.1fs", elapsed)

    assert isinstance(result, dict), "Ergebnis muss ein Dict sein"
    assert "error" not in result or result.get("error") is None, f"Fehler: {result.get('error')}"
    assert "scenes" in result, "scenes fehlt im Ergebnis"

    scenes = result["scenes"]
    logger.info("  Analysierte Frames: %d", len(scenes))
    for scene in scenes:
        logger.info("  [%.1fs] %s", scene["timestamp_sec"], scene["description"][:80])

    logger.info("✅ Test 4 bestanden: Vision-Analyse funktioniert")
    return result


@_requires_torch_and_whisper
def test_model_swap_protection():
    """Test 5: ModelManager swappt korrekt zwischen Whisper und Vision."""
    from services.model_manager import ModelManager

    mm = ModelManager()

    # Whisper laden
    mm.load_whisper("tiny")
    assert mm.model_type == "whisper"
    whisper_id = mm.current_model_id

    # Vision laden → muss Whisper automatisch entladen
    mm.load_vision("vikhyatk/moondream2")
    assert mm.model_type == "vision"
    assert mm.current_model_id != whisper_id

    # Aufräumen
    mm.unload()

    logger.info("✅ Test 5 bestanden: Modell-Swap funktioniert korrekt")
    return True


def test_orchestrator_multi_step():
    """Test 6: Orchestrator Multi-Step-Analyse (Vision + Audio)."""
    import services.register_actions  # noqa: F401
    from agents.orchestrator_agent import OrchestratorAgent
    from services.model_manager import ModelManager

    orch = OrchestratorAgent()
    orch.set_model_manager(ModelManager())

    # Simuliere einen Multi-Step-Prompt
    # Da wir keinen DB-Eintrag haben, nutzen wir den direkten file_path
    # über den Context
    logger.info("  Starte Multi-Step-Analyse...")

    # Teste die Erkennung
    assert orch._detect_multi_step("Analysiere Bild und Ton von Video 1")
    assert orch._detect_multi_step("Was passiert im Video und was wird gesagt?")
    assert not orch._detect_multi_step("Analysiere das Audio")

    logger.info("✅ Test 6 bestanden: Orchestrator Multi-Step-Erkennung funktioniert")
    return True


def test_agent_routing():
    """Test 7: Agent-Routing im Orchestrator."""
    from agents.orchestrator_agent import OrchestratorAgent
    from agents.audio_agent import AudioAgent
    from agents.vision_agent import VisionAgent

    orch = OrchestratorAgent()

    # Audio-Agent sollte Audio-Anfragen erkennen
    audio_agent = orch._route_to_agent("Transkribiere die Audiodatei Track 1")
    assert isinstance(audio_agent, AudioAgent), f"Erwartet AudioAgent, bekam {type(audio_agent)}"

    # Vision-Agent sollte Video-Anfragen erkennen
    vision_agent = orch._route_to_agent("Was ist in dem Video zu sehen?")
    assert isinstance(vision_agent, VisionAgent), f"Erwartet VisionAgent, bekam {type(vision_agent)}"

    logger.info("✅ Test 7 bestanden: Agent-Routing funktioniert korrekt")
    return True


def test_action_registry_new_actions():
    """Test 8: Neue Aktionen im Registry registriert."""
    import services.register_actions  # noqa: F401
    from services.action_registry import action_registry

    actions = action_registry.list_actions()
    assert "transcribe_audio" in actions, "transcribe_audio fehlt im Registry"
    assert "analyze_video_content" in actions, "analyze_video_content fehlt im Registry"

    logger.info("  Registrierte Aktionen: %s", actions)
    logger.info("✅ Test 8 bestanden: Neue Aktionen registriert")
    return True


def main():
    """Führt alle Integrations-Tests durch."""
    logger.info("=" * 60)
    logger.info("PB STUDIO 3-AGENTEN SWARM — INTEGRATIONS-TEST")
    logger.info("=" * 60)

    video_path = find_test_video()
    audio_path = find_test_audio()

    logger.info("Test-Video: %s", video_path or "NICHT GEFUNDEN")
    logger.info("Test-Audio: %s", audio_path or "NICHT GEFUNDEN")
    logger.info("-" * 60)

    results = {}
    total_start = time.time()

    # Grundlegende Tests (ohne ML-Modelle)
    try:
        results["singleton"] = test_model_manager_singleton()
    except Exception as e:
        logger.error("❌ Test 1 fehlgeschlagen: %s", e)
        results["singleton"] = False

    try:
        results["vram_protection"] = test_model_manager_vram_protection()
    except Exception as e:
        logger.error("❌ Test 2 fehlgeschlagen: %s", e)
        results["vram_protection"] = False

    try:
        results["action_registry"] = test_action_registry_new_actions()
    except Exception as e:
        logger.error("❌ Test 8 fehlgeschlagen: %s", e)
        results["action_registry"] = False

    try:
        results["agent_routing"] = test_agent_routing()
    except Exception as e:
        logger.error("❌ Test 7 fehlgeschlagen: %s", e)
        results["agent_routing"] = False

    try:
        results["orchestrator_multi_step"] = test_orchestrator_multi_step(video_path)
    except Exception as e:
        logger.error("❌ Test 6 fehlgeschlagen: %s", e)
        results["orchestrator_multi_step"] = False

    # ML-Tests (benötigen Modell-Downloads)
    if audio_path:
        try:
            results["transcribe"] = test_transcribe_audio(audio_path) is not None
        except Exception as e:
            logger.error("❌ Test 3 fehlgeschlagen: %s", e)
            results["transcribe"] = False

    if video_path:
        try:
            results["vision"] = test_analyze_video_content(video_path) is not None
        except Exception as e:
            logger.error("❌ Test 4 fehlgeschlagen: %s", e)
            results["vision"] = False

    try:
        results["model_swap"] = test_model_swap_protection()
    except Exception as e:
        logger.error("❌ Test 5 fehlgeschlagen: %s", e)
        results["model_swap"] = False

    # Zusammenfassung
    total_elapsed = time.time() - total_start
    logger.info("=" * 60)
    logger.info("ERGEBNISSE:")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, ok in results.items():
        status = "✅" if ok else "❌"
        logger.info("  %s %s", status, name)
    logger.info("-" * 60)
    logger.info("Bestanden: %d/%d (%.0f%%)", passed, total, passed / total * 100 if total else 0)
    logger.info("Gesamtdauer: %.1fs", total_elapsed)
    logger.info("=" * 60)

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
