from pathlib import Path


def test_video_caption_falls_back_to_installed_vision_model(monkeypatch, tmp_path: Path):
    from services import video_analysis_service as vas

    keyframe = tmp_path / "frame.jpg"
    keyframe.write_bytes(b"fake")
    scene = vas.SceneInfo(index=1, start_time=0.0, end_time=1.0, keyframe_path=str(keyframe))
    used = {}

    class _Svc:
        is_ready = True

        def vision(self, **kwargs):
            used["model"] = kwargs["model"]
            return '{"description":"x","mood":"calm","motion":"static","tags":["x"]}'

    class _Client:
        is_paused = False

        def model_exists(self, model):
            return model == "moondream:1.8b"

        def list_models(self):
            return ["moondream:1.8b"]

    monkeypatch.setattr("services.ollama_service.OllamaService.get", lambda: _Svc())
    monkeypatch.setattr(vas, "get_ollama_client", lambda: _Client(), raising=False)

    result = vas.analyze_scene_with_caption([scene], vision_model="moondream:latest")

    assert used["model"] == "moondream:1.8b"
    assert result[0].ai_caption["description"] == "x"
