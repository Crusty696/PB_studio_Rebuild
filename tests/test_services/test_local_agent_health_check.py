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
