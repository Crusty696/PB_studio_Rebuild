from services.ollama_client import OllamaClient
import json
import urllib.error


def test_best_available_model_prefers_installed_gemma4_family(monkeypatch):
    client = OllamaClient()
    monkeypatch.setattr(
        client,
        "list_models",
        lambda: ["moondream:latest", "gemma4:e4b", "gemma4:latest"],
    )
    monkeypatch.setattr(client, "model_supports_completion", lambda model: True)

    assert client.get_best_available_model(probe=False) == "gemma4:e4b"


def test_best_available_model_skips_models_without_completion(monkeypatch):
    client = OllamaClient()
    monkeypatch.setattr(
        client,
        "list_models",
        lambda: ["gemma4:e4b", "ALIENTELLIGENCE/filmandvideoproduction:latest"],
    )
    monkeypatch.setattr(
        client,
        "model_supports_completion",
        lambda model: model == "ALIENTELLIGENCE/filmandvideoproduction:latest",
    )

    assert client.get_best_available_model(probe=False) == "ALIENTELLIGENCE/filmandvideoproduction:latest"


def test_best_available_model_unknown_fallback_is_deterministic(monkeypatch):
    client = OllamaClient()
    monkeypatch.setattr(
        client,
        "list_models",
        lambda: ["z-model:latest", "a-model:latest"],
    )
    monkeypatch.setattr(client, "model_supports_completion", lambda model: True)

    assert client.get_best_available_model(probe=False) == "a-model:latest"


def test_chat_falls_back_to_generate_for_completion_only_model(monkeypatch):
    client = OllamaClient()
    calls = []

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps({"response": "OK"}).encode("utf-8")

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        if req.full_url.endswith("/api/chat"):
            raise urllib.error.HTTPError(
                req.full_url,
                400,
                "Bad Request",
                hdrs=None,
                fp=_Body(b'{"error":"\\"gemma4:e4b\\" does not support chat"}'),
            )
        return _Response()

    class _Body:
        def __init__(self, body):
            self._body = body

        def read(self):
            return self._body

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    assert client.chat("gemma4:e4b", "Antworte OK", max_tokens=8) == "OK"
    assert calls == [
        "http://localhost:11434/api/chat",
        "http://localhost:11434/api/generate",
    ]
