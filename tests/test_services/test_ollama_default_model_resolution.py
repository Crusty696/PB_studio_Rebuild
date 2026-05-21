import os


class _FakeResponse:
    status_code = 200

    def json(self):
        return {
            "models": [
                {
                    "name": "phi3:mini",
                    "details": {"family": "phi3"},
                }
            ]
        }


class _FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, path: str):
        assert path == "/api/tags"
        return _FakeResponse()


def test_resolve_default_model_ignores_missing_env_override(monkeypatch):
    from services import ollama_service

    monkeypatch.setenv("PB_OLLAMA_MODEL", "missing-model:latest")
    monkeypatch.setattr(ollama_service.httpx, "Client", _FakeClient)

    assert ollama_service._resolve_default_model("http://unused") == "phi3:mini"


def test_resolve_default_model_uses_installed_env_override(monkeypatch):
    from services import ollama_service

    monkeypatch.setenv("PB_OLLAMA_MODEL", "phi3:mini")
    monkeypatch.setattr(ollama_service.httpx, "Client", _FakeClient)

    assert ollama_service._resolve_default_model("http://unused") == "phi3:mini"

