"""B-650 (Weg B): per-Aufgabe Modellwahl.

Beweist mit der REALEN installierten Konstellation (qwen3-vl + gemma3 haben
BEIDE vision+completion; phi3 ist reines Text-Modell), dass:
- Text-Aufgaben (pacing/action/chat) NIE ein Vision-First-Modell (qwen-vl,
  moondream, minicpm-v) bekommen — sondern ein Text-Modell (gemma3/phi3).
- Vision-Aufgaben (caption) das Vision-First-Modell qwen3-vl bekommen (nicht
  gemma3, das zwar vision kann aber ein Text-Modell ist).
- gemma4:e4b (9.6 GB) NIE gewaehlt wird (> 6 GB VRAM).
- env-Override greift (installiert) bzw. ignoriert wird (nicht installiert).
- OllamaClient.select_best_model(prefer=...) gross/klein korrekt sortiert.
"""
from __future__ import annotations

from services import model_router

# (name, size_bytes, capabilities) — reale PB-Studio-Maschine 2026-07-17
_INSTALLED = [
    ("qwen3-vl:4b",      3_300_000_000, ["completion", "vision"]),
    ("gemma3:4b",        3_300_000_000, ["completion", "vision"]),
    ("phi3:mini",        2_200_000_000, ["completion"]),
    ("moondream:latest", 1_700_000_000, ["completion", "vision"]),
    ("minicpm-v4.6:1b",  1_600_000_000, ["completion", "vision"]),
    ("gemma4:e4b",       9_600_000_000, ["completion"]),
]

_VISION_FIRST = {"qwen3-vl:4b", "moondream:latest", "minicpm-v4.6:1b"}


class _FakeClient:
    def __init__(self, models=None):
        self._models = models if models is not None else _INSTALLED
        self.installed = {m[0] for m in self._models}

    def model_exists(self, name):
        return name in self.installed

    def _list_models_detailed(self):
        return [{"name": n, "size": s} for (n, s, _c) in self._models]

    def _capabilities(self, name):
        for (n, _s, c) in self._models:
            if n == name:
                return c
        return None

    def select_best_model(self, task="chat", max_size_bytes=None, prefer="quality"):
        return None  # Fallback darf hier nicht gebraucht werden


def test_caption_picks_vision_first_qwen():
    assert model_router.resolve_model_for_task(_FakeClient(), "caption") == "qwen3-vl:4b"


def test_pacing_picks_text_gemma3_not_qwen():
    got = model_router.resolve_model_for_task(_FakeClient(), "pacing")
    assert got == "gemma3:4b"
    assert got not in _VISION_FIRST


def test_action_picks_fast_text_phi3():
    assert model_router.resolve_model_for_task(_FakeClient(), "action") == "phi3:mini"


def test_chat_picks_text_not_vision_first():
    got = model_router.resolve_model_for_task(_FakeClient(), "chat")
    assert got == "phi3:mini"
    assert got not in _VISION_FIRST


def test_text_task_never_vision_first_even_if_only_big_text_too_large():
    # Nur qwen-vl (vision-first) + gemma4 (zu gross) -> Text-Task findet KEIN
    # gueltiges Text-Modell -> Fallback (select_best_model=None hier).
    only = [
        ("qwen3-vl:4b", 3_300_000_000, ["completion", "vision"]),
        ("gemma4:e4b",  9_600_000_000, ["completion"]),
    ]
    got = model_router.resolve_model_for_task(_FakeClient(only), "pacing")
    assert got not in _VISION_FIRST  # qwen-vl NIE fuer Text
    assert got != "gemma4:e4b"       # zu gross
    assert got is None               # ehrlich: nichts Gueltiges -> None


def test_gemma4_never_chosen_vram():
    for task in ("caption", "pacing", "action", "chat"):
        assert model_router.resolve_model_for_task(_FakeClient(), task) != "gemma4:e4b"


def test_env_override_wins_when_installed(monkeypatch):
    monkeypatch.setenv("PB_STRATEGIST_MODEL", "phi3:mini")
    assert model_router.resolve_model_for_task(_FakeClient(), "pacing") == "phi3:mini"


def test_env_override_ignored_when_not_installed(monkeypatch):
    monkeypatch.setenv("PB_STRATEGIST_MODEL", "does-not-exist")
    # ignoriert -> normale Auswahl gemma3:4b
    assert model_router.resolve_model_for_task(_FakeClient(), "pacing") == "gemma3:4b"


def test_chat_fallback_never_returns_vision_first():
    """Transiente Startup-Leere -> Fallback. Fuer Text darf NIE ein
    Vision-First-Modell zurueckkommen (Bug: Probe waehlte minicpm-v fuer chat)."""
    class _Cli:
        def model_exists(self, n):
            return False

        def _list_models_detailed(self):
            return []  # transiente Leere erzwingt Fallback

        def _capabilities(self, n):
            return None

        def select_best_model(self, task="chat", max_size_bytes=None, prefer="quality"):
            return "minicpm-v4.6:1b"  # Vision-First-Modell

    assert model_router.resolve_model_for_task(_Cli(), "chat") is None


def test_select_best_model_prefer_speed_vs_quality(monkeypatch):
    from services.ollama_client import OllamaClient

    c = OllamaClient()
    models = [
        {"name": "big:4b", "size": 3_300_000_000, "details": {"parameter_size": "4B"}},
        {"name": "small:1b", "size": 1_600_000_000, "details": {"parameter_size": "1B"}},
    ]
    monkeypatch.setattr(c, "_list_models_detailed", lambda: models)
    monkeypatch.setattr(c, "_capabilities", lambda name: ["completion"])
    assert c.select_best_model("chat", prefer="quality") == "big:4b"
    assert c.select_best_model("chat", prefer="speed") == "small:1b"


def test_select_best_model_excludes_gemma4_by_vram(monkeypatch):
    from services.ollama_client import OllamaClient

    c = OllamaClient()
    models = [
        {"name": "gemma4:e4b", "size": 9_600_000_000, "details": {"parameter_size": "4B"}},
        {"name": "gemma3:4b", "size": 3_300_000_000, "details": {"parameter_size": "4B"}},
    ]
    monkeypatch.setattr(c, "_list_models_detailed", lambda: models)
    monkeypatch.setattr(c, "_capabilities", lambda name: ["completion"])
    assert c.select_best_model("chat", prefer="quality") == "gemma3:4b"


def test_local_agent_generate_ollama_emits_chat_status(monkeypatch):
    """B-650-Rest: KI-Chat (_generate_ollama) muss Modell + Aufgabe 'chat'
    ans ModelStatusField melden (loading -> ready) statt still zu laufen."""
    from unittest.mock import MagicMock
    from services import local_agent_service as las

    svc = las.LocalAgentService.__new__(las.LocalAgentService)
    svc._ollama_model = "phi3:mini"
    client = MagicMock()
    client.chat.return_value = "antwort"
    monkeypatch.setattr(
        las.LocalAgentService, "_get_ollama_client", lambda self: client
    )
    monkeypatch.setattr(
        las.LocalAgentService, "_build_system_prompt",
        lambda self, **kw: "sys",
    )
    calls = []
    monkeypatch.setattr(
        model_router, "emit_task_status",
        lambda status, model, task: calls.append((status, model, task)),
    )

    out = svc._generate_ollama("hallo")

    assert out == "antwort"
    assert ("loading", "phi3:mini", "chat") in calls
    assert ("ready", "phi3:mini", "chat") in calls


def test_local_agent_auto_select_uses_router(monkeypatch):
    """B-650-Rest: Auto-Select im Chat-Pfad nutzt resolve_model_for_task('chat')
    statt blindem get_best_available_model (Vision-First-Ausschluss)."""
    from unittest.mock import MagicMock
    from services import local_agent_service as las

    svc = las.LocalAgentService.__new__(las.LocalAgentService)
    svc._ollama_model = None
    svc._ollama_url = "http://localhost:11434"
    svc._use_ollama = True
    client = MagicMock()
    client.is_available.return_value = True
    client.get_best_available_model.return_value = "qwen3-vl:4b"  # falsch fuer Text
    monkeypatch.setattr(
        las.LocalAgentService, "_maybe_reprobe_ollama", lambda self: None
    )
    monkeypatch.setattr(
        las.LocalAgentService, "_get_ollama_client", lambda self: client
    )
    monkeypatch.setattr(
        model_router, "resolve_model_for_task",
        lambda c, task: "phi3:mini" if task == "chat" else None,
    )

    result = svc.health_check()

    assert result["model"] == "phi3:mini"
    assert svc._ollama_model == "phi3:mini"
