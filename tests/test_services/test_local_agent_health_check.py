"""B-180: Health-Check liefert klare Diagnostik wenn Ollama nicht läuft.

Schützt davor, dass der User stundenlang rätselt warum der Chat hängt.
"""
from __future__ import annotations

from unittest.mock import patch

from services.local_agent_service import LocalAgentService


def _agent_with_ollama_off() -> LocalAgentService:
    return LocalAgentService(
        ollama_url="http://localhost:11434",
        ollama_model="gemma3:4b",
        use_ollama=False,
    )


def test_health_check_reports_fallback_when_ollama_disabled():
    agent = _agent_with_ollama_off()
    hc = agent.health_check()
    assert hc["backend"] == "fallback"
    assert hc["ollama_reachable"] is False
    assert "Ollama deaktiviert" in hc["message"]


def test_health_check_reports_unreachable_when_server_down(monkeypatch):
    """Ollama enabled aber Server unerreichbar → klare Fehler-Message."""
    agent = LocalAgentService(
        ollama_url="http://localhost:11434",
        ollama_model="gemma3:4b",
        use_ollama=True,
    )

    class _StubClient:
        def is_available(self):
            return False
        def get_best_available_model(self):
            return None
        def get_version(self):
            return None

    monkeypatch.setattr(agent, "_get_ollama_client", lambda: _StubClient())
    hc = agent.health_check()
    assert hc["backend"] == "ollama"
    assert hc["ollama_reachable"] is False
    assert "nicht erreichbar" in hc["message"].lower()


def test_health_check_reports_no_model_installed(monkeypatch):
    agent = LocalAgentService(
        ollama_url="http://localhost:11434",
        ollama_model=None,
        use_ollama=True,
    )

    class _StubClient:
        def is_available(self):
            return True
        def get_best_available_model(self):
            return None
        def get_version(self):
            return "0.5.1"

    monkeypatch.setattr(agent, "_get_ollama_client", lambda: _StubClient())
    hc = agent.health_check()
    assert hc["ollama_reachable"] is True
    assert hc["model"] is None
    assert "kein Modell" in hc["message"].lower() or "ollama pull" in hc["message"].lower()


def test_health_check_reports_ready(monkeypatch):
    agent = LocalAgentService(
        ollama_url="http://localhost:11434",
        ollama_model="gemma3:4b",
        use_ollama=True,
    )

    class _StubClient:
        def is_available(self):
            return True
        def get_best_available_model(self):
            return "gemma3:4b"
        def get_version(self):
            return "0.5.1"

    monkeypatch.setattr(agent, "_get_ollama_client", lambda: _StubClient())
    hc = agent.health_check()
    assert hc["ollama_reachable"] is True
    assert hc["model"] == "gemma3:4b"
    assert "bereit" in hc["message"].lower()


def test_health_check_handles_client_exception(monkeypatch):
    """Wenn der Ollama-Client wirft, soll der Health-Check die Exception
    fangen und in eine Banner-Message ummünzen — nicht crashen."""
    agent = LocalAgentService(
        ollama_url="http://localhost:11434",
        ollama_model="gemma3:4b",
        use_ollama=True,
    )

    class _BrokenClient:
        def is_available(self):
            raise ConnectionError("network unreachable")

    monkeypatch.setattr(agent, "_get_ollama_client", lambda: _BrokenClient())
    hc = agent.health_check()
    assert "fehlgeschlagen" in hc["message"].lower() or "unreachable" in hc["message"].lower()


def test_health_check_auto_detect_does_not_report_disabled(monkeypatch):
    """Auto-Detect darf nicht als manuell deaktiviertes Ollama erscheinen."""
    agent = LocalAgentService(
        ollama_url="http://localhost:11434",
        ollama_model=None,
        use_ollama=None,
    )

    monkeypatch.setattr(agent, "_auto_detect_ollama", lambda: True)
    agent._ollama_model = "gemma3:4b"

    class _StubClient:
        def is_available(self):
            return True
        def get_best_available_model(self):
            return "gemma3:4b"
        def get_version(self):
            return "0.5.1"

    monkeypatch.setattr(agent, "_get_ollama_client", lambda: _StubClient())
    hc = agent.health_check()

    assert hc["backend"] == "ollama"
    assert hc["ollama_reachable"] is True
    assert "deaktiviert" not in hc["message"].lower()


def test_auto_detect_falls_back_from_stale_settings_to_localhost(monkeypatch):
    """Stale Settings-URL/Modell duerfen lokale Ollama-Erkennung nicht blockieren."""
    agent = LocalAgentService(
        ollama_url="http://legacy:8080",
        ollama_model="legacy-model",
        use_ollama=None,
    )

    class _ConfiguredClient:
        def is_available(self):
            return False

    class _LocalClient:
        def is_available(self):
            return True
        def model_exists(self, model):
            return model == "gemma3:4b"
        def get_best_available_model(self):
            return "gemma3:4b"
        def get_version(self):
            return "0.5.1"

    def _make_client(url):
        return _ConfiguredClient() if "legacy" in url else _LocalClient()

    monkeypatch.setattr(agent, "_make_ollama_client", _make_client)

    assert agent._auto_detect_ollama() is True
    assert agent._ollama_url == "http://localhost:11434"
    assert agent._ollama_model == "gemma3:4b"


def test_system_prompt_stays_within_local_gpu_budget(monkeypatch):
    """GTX-1060/Ollama-Chat darf nicht mit mehrkilobyte Prompt starten."""
    agent = LocalAgentService(use_ollama=False)

    monkeypatch.setattr(agent, "_build_media_context", lambda: "")
    monkeypatch.setattr(agent, "_get_positive_few_shots", lambda limit=3: "")

    prompt = agent._build_system_prompt(user_query="Hallo")

    assert len(prompt) <= 1200
    assert "PB Studio" in prompt


def test_chat_watchdog_allows_local_gtx1060_ollama_latency():
    """Lokaler Ollama-Chat auf GTX 1060 kann ueber 60s dauern."""
    from ui.chat_dock import CHAT_AGENT_WATCHDOG_TIMEOUT_MS

    assert CHAT_AGENT_WATCHDOG_TIMEOUT_MS >= 180_000
