"""B-668: Vision-Analyse muss den Basis-``OllamaError`` behandeln.

Der ``except``-Zweig fing nur die drei Subklassen ``OllamaNotAvailableError``,
``OllamaModelNotFoundError`` und ``OllamaPausedError``. Der Basis-Fehler —
den ``chat_vision`` laut eigenem Docstring bei HTTP-/JSON-Fehlern wirft und
der real im Log auftritt ("HTTP-Fehler 500: llama-server process has
terminated") — erbt ueber ``LLMError``/``PBStudioError`` direkt von
``Exception`` und fiel durch beide Zweige. Folge: die Frame-Schleife brach
komplett ab, bereits erzeugte Beschreibungen gingen verloren.

Unterschieden wird bewusst nach Fehlerart:
- ``OllamaTimeoutError`` (B-669) -> Schleife abbrechen. Weiterlaufen wuerde
  pro Frame erneut in die volle Wall-Clock-Grenze laufen.
- sonstiger ``OllamaError`` -> Frame markieren, weitermachen.
"""

import os
import tempfile

import cv2
import numpy as np
import pytest

from services import vision_analysis_service_moondream as vas_mod
from services.vision_analysis_service_moondream import VisionAnalysisService
from services.errors import OllamaError, OllamaTimeoutError


def _make_synthetic_video(path: str, duration_sec: float = 4.0, fps: int = 10) -> None:
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, fps, (64, 48))
    for i in range(int(duration_sec * fps)):
        writer.write(np.full((48, 64, 3), (i * 5) % 255, dtype=np.uint8))
    writer.release()


class _FlakyClient:
    """Client-Stub, der bei bestimmten Frame-Indizes einen Fehler wirft."""

    def __init__(self, fail_on: dict):
        self.fail_on = fail_on  # {call_index: exception}
        self.calls = 0

    def chat_vision(self, model, user_message, images_base64, **kwargs):
        idx = self.calls
        self.calls += 1
        exc = self.fail_on.get(idx)
        if exc is not None:
            raise exc
        return f"Beschreibung Frame {idx}"

    def model_exists(self, model):
        return True


@pytest.fixture
def video_path():
    tmp_dir = tempfile.mkdtemp(prefix="pb_b668_")
    path = os.path.join(tmp_dir, "syn.mp4")
    _make_synthetic_video(path)
    return path


def test_http_error_marks_frame_and_continues(monkeypatch, video_path):
    """HTTP-500 auf einem Frame darf die restlichen Frames nicht kosten."""
    stub = _FlakyClient(fail_on={
        1: OllamaError("HTTP-Fehler 500: llama-server process has terminated",
                       model="moondream:latest", http_code=500),
    })
    monkeypatch.setattr(vas_mod, "get_ollama_client", lambda: stub)

    result = VisionAnalysisService().analyze(
        video_path, interval_sec=1.0, max_frames=3
    )

    assert stub.calls == 3, "Schleife brach vorzeitig ab statt weiterzulaufen"
    assert len(result.descriptions) == 3

    texts = [d["description"] for d in result.descriptions]
    assert texts[0] == "Beschreibung Frame 0"
    assert texts[1].startswith("[Analyse-Fehler:"), \
        "fehlgeschlagener Frame wurde nicht als solcher markiert"
    assert texts[2] == "Beschreibung Frame 2"

    # Die gelungenen Frames landen in der Summary, der kaputte nicht.
    assert "Beschreibung Frame 0" in result.summary
    assert "[Analyse-Fehler" not in result.summary


def test_http_error_on_every_frame_does_not_crash(monkeypatch, video_path):
    stub = _FlakyClient(fail_on={
        i: OllamaError("HTTP-Fehler 500: llama-server crashed", http_code=500)
        for i in range(3)
    })
    monkeypatch.setattr(vas_mod, "get_ollama_client", lambda: stub)

    result = VisionAnalysisService().analyze(
        video_path, interval_sec=1.0, max_frames=3
    )

    assert stub.calls == 3
    assert all(d["description"].startswith("[Analyse-Fehler:")
               for d in result.descriptions)


def test_timeout_stops_the_loop_but_keeps_partial_results(monkeypatch, video_path):
    """B-669-Timeout: abbrechen statt pro Frame erneut ins Limit zu laufen.

    Bei einer Wall-Clock-Grenze von 300 s wuerde Weiterlaufen ueber 10 Frames
    bis zu 50 Minuten kosten — genau der Hang, den B-669 beseitigt hat.
    """
    stub = _FlakyClient(fail_on={
        1: OllamaTimeoutError("Ollama-Timeout nach 300s (chat_vision)",
                              model="moondream:latest", timeout_sec=300.0),
    })
    monkeypatch.setattr(vas_mod, "get_ollama_client", lambda: stub)

    result = VisionAnalysisService().analyze(
        video_path, interval_sec=1.0, max_frames=3
    )

    assert stub.calls == 2, "nach einem Timeout darf kein weiterer Frame folgen"
    # Das Ergebnis von Frame 0 bleibt erhalten.
    assert len(result.descriptions) == 1
    assert result.descriptions[0]["description"] == "Beschreibung Frame 0"


def test_timeout_on_first_frame_reports_reason(monkeypatch, video_path):
    """Ohne jedes Teilergebnis muss die Summary den Timeout ehrlich nennen."""
    stub = _FlakyClient(fail_on={
        0: OllamaTimeoutError("Ollama-Timeout nach 300s (chat_vision)",
                              timeout_sec=300.0),
    })
    monkeypatch.setattr(vas_mod, "get_ollama_client", lambda: stub)

    result = VisionAnalysisService().analyze(
        video_path, interval_sec=1.0, max_frames=3
    )

    assert stub.calls == 1
    assert result.descriptions == []
    assert "timeout" in result.summary.lower(), \
        "Timeout darf nicht als 'nicht verfuegbar' fehletikettiert werden"
