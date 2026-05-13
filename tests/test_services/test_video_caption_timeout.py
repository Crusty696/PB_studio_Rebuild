from pathlib import Path

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
