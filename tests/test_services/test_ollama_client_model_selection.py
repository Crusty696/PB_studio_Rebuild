from services.ollama_client import OllamaClient


def test_best_available_model_prefers_installed_gemma4_family(monkeypatch):
    client = OllamaClient()
    monkeypatch.setattr(
        client,
        "list_models",
        lambda: ["moondream:latest", "gemma4:e4b", "gemma4:latest"],
    )

    assert client.get_best_available_model(probe=False) == "gemma4:e4b"


def test_best_available_model_unknown_fallback_is_deterministic(monkeypatch):
    client = OllamaClient()
    monkeypatch.setattr(
        client,
        "list_models",
        lambda: ["z-model:latest", "a-model:latest"],
    )

    assert client.get_best_available_model(probe=False) == "a-model:latest"

