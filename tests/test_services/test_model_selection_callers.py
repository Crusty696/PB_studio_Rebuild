def test_pacing_strategist_ignores_stale_settings_model(monkeypatch):
    from services import pacing_strategist
    from ui.dialogs import settings_dialog

    used = {}

    class _Client:
        def is_available(self):
            return True

        def model_exists(self, model):
            return model == "gemma4:e4b"

        def get_best_available_model(self):
            return "gemma4:e4b"

        def chat(self, **kwargs):
            used["model"] = kwargs["model"]
            return '{"sections": [], "global_min_duration": 3.0, "variety_priority": 0.7}'

    monkeypatch.setattr(
        settings_dialog,
        "get_ollama_settings",
        lambda: {"enabled": True, "url": "http://localhost:11434", "model": "gemma3:4b"},
    )
    monkeypatch.setattr(pacing_strategist, "get_ollama_client", lambda _url=None: _Client(), raising=False)
    monkeypatch.setattr(pacing_strategist, "get_strategist_model", lambda: "gemma4:e4b")

    plan = pacing_strategist.PacingStrategist().generate_pacing_plan(
        sections=[],
        bpm=136.0,
        total_duration=60.0,
        clip_count=3,
    )

    assert plan.degraded is False
    assert used["model"] == "gemma4:e4b"


def test_pacing_strategist_offline_fallback_uses_registry_not_stale_constant(monkeypatch):
    from services import pacing_strategist

    class _Service:
        def get_default_model(self):
            return None

    class _OllamaService:
        @staticmethod
        def get():
            return _Service()

    class _Entry:
        def __init__(self, model_id, source="ollama", status="offline"):
            self.model_id = model_id
            self.source = source
            self.status = status

    class _Lifecycle:
        def get_registry_entries(self):
            return [
                _Entry("moondream:latest"),
                _Entry("gemma4:e4b"),
                _Entry("google/siglip-so400m-patch14-384", "huggingface", "installed"),
            ]

    monkeypatch.setattr("services.ollama_service.OllamaService", _OllamaService)
    monkeypatch.setattr("services.model_lifecycle_service.ModelLifecycleService", _Lifecycle)

    assert pacing_strategist.get_strategist_model() == "gemma4:e4b"


def test_ask_ai_ignores_missing_env_model(monkeypatch):
    from services.actions import ai_actions

    used = {}

    class _Client:
        def is_available(self):
            return True

        def model_exists(self, model):
            return model == "gemma4:e4b"

        def get_best_available_model(self):
            return "gemma4:e4b"

        def chat(self, **kwargs):
            used["model"] = kwargs["model"]
            return "ok"

    monkeypatch.setenv("PB_OLLAMA_MODEL", "missing-model:latest")
    monkeypatch.setattr(ai_actions, "_get_ollama_client", lambda: _Client())

    result = ai_actions.ask_ai("test")

    assert result["status"] == "ok"
    assert result["model"] == "gemma4:e4b"
    assert used["model"] == "gemma4:e4b"
