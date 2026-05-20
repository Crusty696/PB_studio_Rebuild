"""Regression: PanelSetup must respect explicit Ollama disabled setting."""

from __future__ import annotations

from types import SimpleNamespace


class _FakeRightPanel:
    def insertTab(self, *_args, **_kwargs) -> None:
        pass

    def setCurrentIndex(self, *_args, **_kwargs) -> None:
        pass


class _FakeChatDock:
    def __init__(self, _parent=None) -> None:
        self.agent = None
        self.messages: list[str] = []

    def widget(self):
        return SimpleNamespace(setParent=lambda *_args, **_kwargs: None)

    def hide(self) -> None:
        pass

    def set_main_window(self, _window) -> None:
        pass

    def set_agent(self, agent) -> None:
        self.agent = agent

    def append_system(self, message: str) -> None:
        self.messages.append(message)

    def append_error(self, message: str) -> None:
        self.messages.append(message)


class _FakeConsole:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def append(self, text: str) -> None:
        self.lines.append(text)


class _FakeOllamaService:
    def __init__(self) -> None:
        self.start_calls = 0

    def start_background(self) -> None:
        self.start_calls += 1

    def ready_cached(self) -> bool:
        return True


class _FakeAgent:
    created: list[dict] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        _FakeAgent.created.append(kwargs)

    def invalidate_system_prompt_cache(self, _scope: str) -> None:
        pass

    def health_check(self) -> dict:
        return {
            "backend": "fallback",
            "message": "Ollama deaktiviert.",
            "ollama_reachable": False,
        }


def test_setup_chat_dock_respects_explicit_ollama_disabled(monkeypatch) -> None:
    """Wenn User Ollama deaktiviert, darf PanelSetup es nicht auto-enablen."""
    from ui.controllers import panel_setup
    from ui.controllers.panel_setup import PanelSetupController
    import services.local_agent_service as local_agent_service
    import services.ollama_service as ollama_service
    import ui.dialogs.settings_dialog as settings_dialog

    fake_svc = _FakeOllamaService()
    _FakeAgent.created.clear()

    monkeypatch.setattr(panel_setup, "ChatDock", _FakeChatDock)
    monkeypatch.setattr(settings_dialog, "get_ollama_settings", lambda: {
        "enabled": False,
        "url": "http://localhost:11434",
        "model": "gemma3:4b",
    })
    monkeypatch.setattr(ollama_service.OllamaService, "get", staticmethod(lambda: fake_svc))
    monkeypatch.setattr(local_agent_service, "LocalAgentService", _FakeAgent)

    window = SimpleNamespace(
        right_panel=_FakeRightPanel(),
        console_text=_FakeConsole(),
        _project_manager=None,
    )

    PanelSetupController(window).setup_chat_dock()

    assert fake_svc.start_calls == 0
    assert _FakeAgent.created[-1]["use_ollama"] is False


def test_setup_chat_dock_does_not_call_agent_health_check_synchronously(monkeypatch) -> None:
    from ui.controllers import panel_setup
    from ui.controllers.panel_setup import PanelSetupController
    import services.local_agent_service as local_agent_service
    import services.ollama_service as ollama_service
    import ui.dialogs.settings_dialog as settings_dialog

    class BlockingHealthAgent(_FakeAgent):
        health_calls = 0

        def health_check(self) -> dict:
            BlockingHealthAgent.health_calls += 1
            raise AssertionError("health_check must not run during setup_chat_dock")

    fake_svc = _FakeOllamaService()
    BlockingHealthAgent.health_calls = 0

    monkeypatch.setattr(panel_setup, "ChatDock", _FakeChatDock)
    monkeypatch.setattr(settings_dialog, "get_ollama_settings", lambda: {
        "enabled": True,
        "url": "http://localhost:11434",
        "model": "gemma3:4b",
    })
    monkeypatch.setattr(ollama_service.OllamaService, "get", staticmethod(lambda: fake_svc))
    monkeypatch.setattr(local_agent_service, "LocalAgentService", BlockingHealthAgent)

    window = SimpleNamespace(
        right_panel=_FakeRightPanel(),
        console_text=_FakeConsole(),
        _project_manager=None,
    )

    PanelSetupController(window).setup_chat_dock()

    assert BlockingHealthAgent.health_calls == 0
