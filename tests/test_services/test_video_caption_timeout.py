from pathlib import Path

from services.timeout_constants import HTTP_OLLAMA_VISION_CAPTION_TIMEOUT_SEC
from services.video_analysis_service import SceneInfo, analyze_scene_with_caption


class _FakeOllamaService:
    is_ready = True

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def vision(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return '{"description": "ok", "mood": "calm", "motion": "low", "tags": []}'


class _FakeOllamaClient:
    is_paused = False


def test_video_caption_uses_bounded_ollama_read_timeout(monkeypatch, tmp_path: Path) -> None:
    fake_svc = _FakeOllamaService()
    keyframe = tmp_path / "scene.jpg"
    keyframe.write_bytes(b"not-a-real-image")

    monkeypatch.setattr("services.ollama_service.OllamaService.get", lambda: fake_svc)
    monkeypatch.setattr("services.ollama_client.get_ollama_client", lambda: _FakeOllamaClient())

    scenes = [SceneInfo(index=0, start_time=0.0, end_time=1.0, keyframe_path=str(keyframe))]

    analyze_scene_with_caption(scenes)

    assert fake_svc.calls
    assert all(call["read_timeout_s"] > 0 for call in fake_svc.calls)


def test_video_caption_timeout_uses_documented_worker_budget(monkeypatch, tmp_path: Path) -> None:
    """SCHNITT-FIXPLAN 2026-07-07: der Caption-Read-Timeout wurde bewusst von
    30s auf HTTP_OLLAMA_VISION_CAPTION_TIMEOUT_SEC (240s) angehoben — Ollama-
    Vision-Modelle liefern auf der GTX 1060 real erst nach >30s. Der Aufruf
    laeuft im QThread-Worker (workers/video.py: VideoAnalysisPipelineWorker.run
    -> run_deferred_captioning), NICHT im UI-Thread — friert die GUI also nicht
    ein. Frueher forderte dieser Test ``<= 30`` (UI-Pipeline-Annahme); die
    Annahme ist ueberholt. Kontrakt jetzt: der Timeout ist gebunden und an die
    dokumentierte Konstante gekoppelt (nicht unendlich/hart-codiert daneben).
    """
    fake_svc = _FakeOllamaService()
    keyframe = tmp_path / "scene.jpg"
    keyframe.write_bytes(b"not-a-real-image")

    monkeypatch.setattr("services.ollama_service.OllamaService.get", lambda: fake_svc)
    monkeypatch.setattr("services.ollama_client.get_ollama_client", lambda: _FakeOllamaClient())

    scenes = [SceneInfo(index=0, start_time=0.0, end_time=1.0, keyframe_path=str(keyframe))]

    analyze_scene_with_caption(scenes)

    assert fake_svc.calls
    # gebunden (kein unendlicher Timeout) und exakt die dokumentierte Konstante
    assert all(
        0 < call["read_timeout_s"] <= HTTP_OLLAMA_VISION_CAPTION_TIMEOUT_SEC
        for call in fake_svc.calls
    )
    assert any(
        call["read_timeout_s"] == HTTP_OLLAMA_VISION_CAPTION_TIMEOUT_SEC
        for call in fake_svc.calls
    )
