"""B-599: GPU/Ollama guardrails gegen Batch-Starvation und Timeout-Spiralen."""
from __future__ import annotations

import inspect
import logging
from pathlib import Path


def test_b599_gpu_execution_lease_logs_holder_timing(caplog) -> None:
    from services import model_manager

    with caplog.at_level(logging.INFO, logger=model_manager.__name__):
        with model_manager.gpu_execution_lease("b599-test"):
            pass

    text = caplog.text
    assert "B-599 GPU_EXECUTION_LOCK wait" in text
    assert "B-599 GPU_EXECUTION_LOCK acquired" in text
    assert "B-599 GPU_EXECUTION_LOCK released" in text


class _TimeoutOllamaService:
    is_ready = True

    def __init__(self) -> None:
        self.calls = 0

    def vision(self, **kwargs) -> str:
        self.calls += 1
        return "Fehler: timed out"


class _OllamaClient:
    is_paused = False

    def model_exists(self, _model: str) -> bool:
        return True


def _scene(tmp_path: Path, index: int):
    from services.video_analysis_service import SceneInfo

    keyframe = tmp_path / f"scene_{index}.jpg"
    keyframe.write_bytes(b"fake")
    return SceneInfo(index=index, start_time=0.0, end_time=1.0, keyframe_path=str(keyframe))


def test_b599_caption_failures_circuit_break_across_batch(monkeypatch, tmp_path: Path) -> None:
    from services import video_analysis_service as vas

    svc = _TimeoutOllamaService()
    state: dict[str, int] = {}
    monkeypatch.setattr("services.ollama_service.OllamaService.get", lambda: svc)
    monkeypatch.setattr("services.video_analysis_service.get_ollama_client", lambda: _OllamaClient())

    for index in range(4):
        vas.analyze_scene_with_caption(
            [_scene(tmp_path, index)],
            caption_failure_state=state,
        )

    assert svc.calls == 3
    assert state["consecutive_failures"] >= 3


def test_b599_ollama_vision_logs_warm_state() -> None:
    from services.ollama_service import OllamaService

    source = inspect.getsource(OllamaService.vision)
    assert "B-599 OllamaService.vision warm_state before" in source
    assert "B-599 OllamaService.vision warm_state after_ensure" in source
