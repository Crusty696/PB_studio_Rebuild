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
            # SCHNITT-FIXPLAN 2026-07-07: die Caption-Validierung
            # (_caption_text_is_plausible) verwirft jetzt zu kurze Nicht-Prosa
            # (<15 Zeichen / <3 Woerter). Ein Ein-Zeichen-"x" faellt korrekt
            # durch → ai_caption bleibt None. Fuer diesen Fallback-Test (Intent:
            # moondream:latest → moondream:1.8b) liefert der Fake daher eine
            # plausible Beschreibung, damit der Caption-Pfad durchlaeuft.
            return (
                '{"description":"a calm static forest scene",'
                '"mood":"calm","motion":"static","tags":["forest"]}'
            )

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
    assert result[0].ai_caption["description"] == "a calm static forest scene"
