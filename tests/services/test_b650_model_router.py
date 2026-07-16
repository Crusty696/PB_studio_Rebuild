"""B-650 (Weg B): per-Aufgabe Modellwahl.

Beweist:
- ``resolve_model_for_task`` ruft ``select_best_model`` mit der KORREKTEN
  Capability + prefer je Aufgabe (caption->vision/quality, pacing->chat/quality,
  action->chat/speed).
- ``OllamaClient.select_best_model(prefer=...)`` waehlt bei "quality" das
  groesste, bei "speed" das kleinste passende Modell.
- env-Override (PB_VISION_MODEL etc.) schlaegt die Auto-Wahl, aber nur wenn
  das Modell installiert ist.
"""
from __future__ import annotations

from services import model_router


class _FakeClient:
    def __init__(self, installed=None, best=None):
        self.installed = set(installed or [])
        self.calls: list[tuple[str, str]] = []
        self._best = best or {}

    def model_exists(self, name):
        return name in self.installed

    def select_best_model(self, task="chat", max_size_bytes=None, prefer="quality"):
        self.calls.append((task, prefer))
        return self._best.get((task, prefer))


def test_caption_maps_to_vision_quality():
    c = _FakeClient(best={("vision", "quality"): "qwen3-vl:4b"})
    assert model_router.resolve_model_for_task(c, "caption") == "qwen3-vl:4b"
    assert c.calls == [("vision", "quality")]


def test_pacing_maps_to_chat_quality():
    c = _FakeClient(best={("chat", "quality"): "gemma3:4b"})
    assert model_router.resolve_model_for_task(c, "pacing") == "gemma3:4b"
    assert c.calls == [("chat", "quality")]


def test_action_maps_to_chat_speed():
    c = _FakeClient(best={("chat", "speed"): "phi3:mini"})
    assert model_router.resolve_model_for_task(c, "action") == "phi3:mini"
    assert c.calls == [("chat", "speed")]


def test_env_override_wins_when_installed(monkeypatch):
    monkeypatch.setenv("PB_VISION_MODEL", "moondream:latest")
    c = _FakeClient(installed={"moondream:latest"},
                    best={("vision", "quality"): "qwen3-vl:4b"})
    assert model_router.resolve_model_for_task(c, "caption") == "moondream:latest"
    assert c.calls == []  # Override installiert -> kein Auto-Lookup


def test_env_override_ignored_when_not_installed(monkeypatch):
    monkeypatch.setenv("PB_VISION_MODEL", "does-not-exist")
    c = _FakeClient(installed=set(),
                    best={("vision", "quality"): "qwen3-vl:4b"})
    assert model_router.resolve_model_for_task(c, "caption") == "qwen3-vl:4b"
    assert c.calls == [("vision", "quality")]


def test_select_best_model_prefer_speed_vs_quality(monkeypatch):
    from services.ollama_client import OllamaClient

    c = OllamaClient()
    models = [
        {"name": "big:4b", "size": 3_300_000_000,
         "details": {"parameter_size": "4B"}},
        {"name": "small:1b", "size": 1_600_000_000,
         "details": {"parameter_size": "1B"}},
    ]
    monkeypatch.setattr(c, "_list_models_detailed", lambda: models)
    monkeypatch.setattr(c, "_capabilities", lambda name: ["completion"])

    assert c.select_best_model("chat", prefer="quality") == "big:4b"
    assert c.select_best_model("chat", prefer="speed") == "small:1b"


def test_gemma4_excluded_by_vram_limit(monkeypatch):
    """gemma4:e4b (9.6 GB) darf NIE gewaehlt werden — passt nicht in 6 GB VRAM."""
    from services.ollama_client import OllamaClient

    c = OllamaClient()
    models = [
        {"name": "gemma4:e4b", "size": 9_600_000_000,
         "details": {"parameter_size": "4B"}},
        {"name": "gemma3:4b", "size": 3_300_000_000,
         "details": {"parameter_size": "4B"}},
    ]
    monkeypatch.setattr(c, "_list_models_detailed", lambda: models)
    monkeypatch.setattr(c, "_capabilities", lambda name: ["completion"])

    # Trotz gleicher Param-Zahl faellt gemma4:e4b durch max_size_bytes raus.
    assert c.select_best_model("chat", prefer="quality") == "gemma3:4b"
