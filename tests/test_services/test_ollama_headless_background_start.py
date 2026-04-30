"""Regression tests for headless Ollama startup with the app."""

from __future__ import annotations

import inspect
import threading
import time

import main
from services import startup_checks
from services.ollama_service import OllamaService
from ui.controllers import panel_setup


def test_ollama_service_background_start_is_non_blocking_and_idempotent(monkeypatch) -> None:
    svc = OllamaService()
    called = threading.Event()
    release = threading.Event()

    def fake_start() -> None:
        called.set()
        release.wait(timeout=2.0)

    monkeypatch.setattr(svc, "start", fake_start)

    t0 = time.monotonic()
    thread = svc.start_background()
    elapsed = time.monotonic() - t0

    assert elapsed < 0.2
    assert thread.daemon
    assert called.wait(timeout=0.5)
    assert svc.start_background() is thread

    release.set()
    thread.join(timeout=1.0)
    assert not thread.is_alive()


def test_startup_check_uses_background_ollama_start() -> None:
    src = inspect.getsource(startup_checks._check_ollama)

    assert "start_background(" in src
    assert "svc.start()" not in src


def test_ui_startup_paths_do_not_probe_ollama_readiness_on_gui_thread() -> None:
    main_src = inspect.getsource(main.main)
    panel_src = inspect.getsource(panel_setup.PanelSetupController.setup_chat_dock)

    for src in (main_src, panel_src):
        assert "start_background(" in src
        assert ".is_ready" not in src
