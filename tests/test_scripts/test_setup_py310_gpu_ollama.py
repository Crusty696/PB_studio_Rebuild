import subprocess

from scripts import setup_py310_gpu


def test_ensure_ollama_running_noops_when_daemon_alive(monkeypatch) -> None:
    popen_calls = []

    monkeypatch.setattr(setup_py310_gpu, "_ollama_daemon_alive", lambda: True)
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: popen_calls.append((a, kw)))

    assert setup_py310_gpu.ensure_ollama_running("ollama.exe") is True
    assert popen_calls == []


def test_ensure_ollama_running_starts_daemon_until_alive(monkeypatch) -> None:
    states = iter([False, False, True])
    popen_calls = []
    sleeps = []

    monkeypatch.setattr(setup_py310_gpu, "_ollama_daemon_alive", lambda: next(states))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: popen_calls.append((a, kw)))
    monkeypatch.setattr(setup_py310_gpu.time, "sleep", lambda seconds: sleeps.append(seconds))

    assert setup_py310_gpu.ensure_ollama_running("ollama.exe", wait_seconds=2) is True
    assert popen_calls
    args, kwargs = popen_calls[0]
    assert args[0] == ["ollama.exe", "serve"]
    assert kwargs["stdout"] is subprocess.DEVNULL
    assert kwargs["stderr"] is subprocess.DEVNULL
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert sleeps == [0.5]


def test_pull_ollama_model_skips_pull_when_daemon_not_startable(monkeypatch) -> None:
    run_calls = []

    monkeypatch.setattr(setup_py310_gpu, "ensure_ollama_running", lambda _ollama: False)
    monkeypatch.setattr(setup_py310_gpu, "_run", lambda *a, **kw: run_calls.append((a, kw)))

    setup_py310_gpu.pull_ollama_model("ollama.exe")

    assert run_calls == []
