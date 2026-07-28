"""Regression tests for headless Ollama startup with the app."""

from __future__ import annotations

import inspect
import threading
import time

import main
from services import startup_checks
from services import ollama_service as ollama_service_module
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


def test_stop_during_start_prevents_late_process_spawn(monkeypatch) -> None:
    svc = OllamaService()
    lookup_entered = threading.Event()
    release_lookup = threading.Event()
    popen_calls: list[tuple[object, ...]] = []

    def blocking_find():
        lookup_entered.set()
        assert release_lookup.wait(timeout=3.0)
        return "ollama.exe"

    def fake_popen(*args, **kwargs):
        popen_calls.append(args)
        raise AssertionError("stop() completed before this late process spawn")

    monkeypatch.setattr(svc, "_is_api_ready", lambda: False)
    monkeypatch.setattr(svc, "_is_port_open", lambda port=11434: False)
    monkeypatch.setattr(ollama_service_module, "_find_ollama_bin", blocking_find)
    monkeypatch.setattr(ollama_service_module.subprocess, "Popen", fake_popen)

    start_thread = svc.start_background()
    assert lookup_entered.wait(timeout=1.0)

    svc.stop()
    release_lookup.set()
    start_thread.join(timeout=2.0)

    assert not start_thread.is_alive()
    assert popen_calls == []


def test_stop_terminates_only_self_owned_windows_process_tree(monkeypatch) -> None:
    svc = OllamaService()
    taskkill_calls: list[list[str]] = []

    class FakeProcess:
        pid = 4242

        @staticmethod
        def poll():
            return None

        @staticmethod
        def terminate():
            raise AssertionError("Windows owned process must be stopped as a tree")

    def fake_run(command, **kwargs):
        taskkill_calls.append(command)

        class Result:
            returncode = 0

        return Result()

    svc._process = FakeProcess()
    monkeypatch.setattr(ollama_service_module.subprocess, "run", fake_run)

    svc.stop()

    assert taskkill_calls == [["taskkill", "/PID", "4242", "/T", "/F"]]
    assert svc._process is None


def test_stop_never_kills_external_ollama_process_tree(monkeypatch) -> None:
    svc = OllamaService()
    taskkill_calls: list[list[str]] = []
    monkeypatch.setattr(
        ollama_service_module.subprocess,
        "run",
        lambda command, **kwargs: taskkill_calls.append(command),
    )

    svc.stop()

    assert taskkill_calls == []


def test_stop_falls_back_when_windows_tree_kill_errors(monkeypatch) -> None:
    svc = OllamaService()

    class FakeProcess:
        pid = 4343
        terminated = False

        @staticmethod
        def poll():
            return None

        @classmethod
        def terminate(cls):
            cls.terminated = True

        @staticmethod
        def wait(timeout):
            return 0

    svc._process = FakeProcess()
    monkeypatch.setattr(
        ollama_service_module.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            ollama_service_module.subprocess.TimeoutExpired("taskkill", 5)
        ),
    )

    svc.stop()

    assert FakeProcess.terminated
    assert svc._process is None


def test_immediate_background_restart_waits_for_cancelled_start(monkeypatch) -> None:
    svc = OllamaService()
    first_lookup_entered = threading.Event()
    release_first_lookup = threading.Event()
    lookup_count = 0
    popen_calls: list[list[str]] = []

    class FakeProcess:
        pid = 4444

    def controlled_find():
        nonlocal lookup_count
        lookup_count += 1
        if lookup_count == 1:
            first_lookup_entered.set()
            assert release_first_lookup.wait(timeout=3.0)
        return "ollama.exe"

    def fake_popen(command, **kwargs):
        popen_calls.append(command)
        return FakeProcess()

    monkeypatch.setattr(svc, "_is_api_ready", lambda: False)
    monkeypatch.setattr(svc, "_is_port_open", lambda port=11434: False)
    monkeypatch.setattr(svc, "_wait_for_api_ready", lambda **kwargs: False)
    monkeypatch.setattr(ollama_service_module, "_find_ollama_bin", controlled_find)
    monkeypatch.setattr(ollama_service_module.subprocess, "Popen", fake_popen)

    cancelled_thread = svc.start_background()
    assert first_lookup_entered.wait(timeout=1.0)
    svc.stop()

    restart_thread = svc.start_background()
    assert restart_thread is not cancelled_thread
    release_first_lookup.set()
    restart_thread.join(timeout=3.0)

    assert not restart_thread.is_alive()
    assert popen_calls == [["ollama.exe", "serve"]]


def test_direct_start_after_completed_stop_restarts_service(monkeypatch) -> None:
    svc = OllamaService()
    popen_calls: list[list[str]] = []

    class FakeProcess:
        pid = 4545

    monkeypatch.setattr(svc, "_is_api_ready", lambda: False)
    monkeypatch.setattr(svc, "_is_port_open", lambda port=11434: False)
    monkeypatch.setattr(svc, "_wait_for_api_ready", lambda **kwargs: False)
    monkeypatch.setattr(ollama_service_module, "_find_ollama_bin", lambda: "ollama.exe")
    monkeypatch.setattr(
        ollama_service_module.subprocess,
        "Popen",
        lambda command, **kwargs: popen_calls.append(command) or FakeProcess(),
    )

    svc.stop()
    svc.start()

    assert popen_calls == [["ollama.exe", "serve"]]


def test_restart_cannot_lose_process_ownership_while_stop_is_cleaning(monkeypatch) -> None:
    svc = OllamaService()
    taskkill_entered = threading.Event()
    release_taskkill = threading.Event()
    restart_done = threading.Event()

    class OldProcess:
        pid = 4646

        @staticmethod
        def poll():
            return None

    class NewProcess:
        pid = 4747

        @staticmethod
        def poll():
            return None

    def blocking_taskkill(command, **kwargs):
        taskkill_entered.set()
        assert release_taskkill.wait(timeout=3.0)

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(svc, "_is_api_ready", lambda: False)
    monkeypatch.setattr(svc, "_is_port_open", lambda port=11434: False)
    monkeypatch.setattr(svc, "_wait_for_api_ready", lambda **kwargs: False)
    monkeypatch.setattr(ollama_service_module, "_find_ollama_bin", lambda: "ollama.exe")
    monkeypatch.setattr(ollama_service_module.subprocess, "run", blocking_taskkill)
    monkeypatch.setattr(
        ollama_service_module.subprocess,
        "Popen",
        lambda *args, **kwargs: NewProcess(),
    )
    svc._process = OldProcess()

    stop_thread = threading.Thread(target=svc.stop)
    stop_thread.start()
    assert taskkill_entered.wait(timeout=1.0)

    def restart():
        svc.start_background().join(timeout=2.0)
        restart_done.set()

    restart_thread = threading.Thread(target=restart)
    restart_thread.start()
    restart_was_blocked = not restart_done.wait(timeout=0.2)

    release_taskkill.set()
    stop_thread.join(timeout=2.0)
    restart_thread.join(timeout=3.0)

    assert restart_was_blocked
    assert not stop_thread.is_alive()
    assert not restart_thread.is_alive()
    assert restart_done.is_set()
    assert isinstance(svc._process, NewProcess)
