"""B-463 Option A — VisionAnalysisService auf Ollama chat_vision.

Pinnt den Contract von ``VisionAnalysisService.analyze()`` nach dem Umbau
weg von HF-moondream2 hin zum existierenden Ollama-Vision-Pfad
(``OllamaClient.chat_vision``):

- fehlende Datei -> FileNotFoundError
- gueltiges Video + Stub-Client -> descriptions je Frame, summary, frame_count
- Ollama nicht erreichbar -> graceful VisionAnalysisResult (kein Crash)
"""

import os
import tempfile

import cv2
import numpy as np
import pytest

from services import vision_analysis_service_moondream as vas_mod
from services.vision_analysis_service_moondream import (
    VisionAnalysisService,
    VisionAnalysisResult,
)
from services.errors import OllamaNotAvailableError


def _make_synthetic_video(path: str, duration_sec: float = 2.0, fps: int = 10) -> None:
    """Schreibt ein kleines echtes mp4 mit wechselnden Farbflaechen."""
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (64, 48))
    total = int(duration_sec * fps)
    for i in range(total):
        frame = np.full((48, 64, 3), (i * 5) % 255, dtype=np.uint8)
        writer.write(frame)
    writer.release()


class _StubClient:
    """Minimaler Ollama-Client-Stub fuer chat_vision."""

    def __init__(self, answer="A calm forest scene.", raise_exc=None):
        self.answer = answer
        self.raise_exc = raise_exc
        self.calls = []

    def chat_vision(self, model, user_message, images_base64, **kwargs):
        self.calls.append((model, user_message, len(images_base64)))
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.answer

    def model_exists(self, model):
        return True


def test_vision_agent_has_no_hf_preload_model_id():
    """B-463: VisionAgent darf kein HF-model_id mehr tragen, sonst preloaded
    der Orchestrator das crashende moondream2 via ensure_loaded(...,'vision')."""
    from agents.vision_agent import VisionAgent
    assert VisionAgent().model_id is None


def test_analyze_missing_file_raises():
    svc = VisionAnalysisService()
    with pytest.raises(FileNotFoundError):
        svc.analyze("/nonexistent_video_b463.mp4")


def test_analyze_uses_ollama_chat_vision(monkeypatch):
    stub = _StubClient(answer="A lone dancer under red strobes.")
    monkeypatch.setattr(vas_mod, "get_ollama_client", lambda: stub)

    tmp_dir = tempfile.mkdtemp(prefix="pb_b463_")
    video_path = os.path.join(tmp_dir, "syn.mp4")
    _make_synthetic_video(video_path, duration_sec=2.0, fps=10)

    result = VisionAnalysisService().analyze(
        video_path, interval_sec=1.0, max_frames=2
    )

    assert isinstance(result, VisionAnalysisResult)
    assert result.frame_count >= 1
    assert len(result.descriptions) == result.frame_count
    assert all("time" in d and "description" in d for d in result.descriptions)
    assert "dancer" in result.summary.lower()
    # chat_vision wurde je Frame mit genau einem Bild aufgerufen
    assert len(stub.calls) == result.frame_count
    assert all(n_imgs == 1 for (_m, _u, n_imgs) in stub.calls)


def test_analyze_ollama_unavailable_is_graceful(monkeypatch):
    stub = _StubClient(raise_exc=OllamaNotAvailableError("Ollama nicht erreichbar"))
    monkeypatch.setattr(vas_mod, "get_ollama_client", lambda: stub)

    tmp_dir = tempfile.mkdtemp(prefix="pb_b463_")
    video_path = os.path.join(tmp_dir, "syn.mp4")
    _make_synthetic_video(video_path, duration_sec=2.0, fps=10)

    result = VisionAnalysisService().analyze(
        video_path, interval_sec=1.0, max_frames=2
    )

    assert isinstance(result, VisionAnalysisResult)
    # kein Crash; graceful summary, keine echten descriptions
    assert result.summary
    assert result.descriptions == []
