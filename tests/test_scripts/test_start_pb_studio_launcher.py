"""B-711 / B-712: Python-Launcher muss die Laufzeit-Invarianten der .bat
uebernehmen und den Exit-Code der App durchreichen."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import start_pb_studio


def _prepare(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, app_returncode: int):
    """Baut eine Fake-Umgebung und liefert die Liste der subprocess-Aufrufe."""
    main_py = tmp_path / "main.py"
    main_py.write_text("# fake", encoding="utf-8")
    venv_python = tmp_path / "python.exe"
    venv_python.write_text("# fake", encoding="utf-8")

    monkeypatch.setattr(start_pb_studio, "PROJECT_DIR", tmp_path)
    monkeypatch.setattr(start_pb_studio, "MAIN_PY", main_py)
    monkeypatch.setattr(start_pb_studio, "VENV_DIR", tmp_path)
    monkeypatch.setattr(start_pb_studio, "VENV_PYTHON", venv_python)
    monkeypatch.setattr(start_pb_studio, "CRASH_LOG", tmp_path / "logs" / "crash.log")
    monkeypatch.setattr(start_pb_studio, "_cleanup_pycache", lambda: None)

    calls: list[dict] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": [str(c) for c in cmd], "kwargs": kwargs})
        if any("--version" in str(c) for c in cmd):
            return subprocess.CompletedProcess(cmd, 0, stdout="Python 3.10.20", stderr="")
        return subprocess.CompletedProcess(cmd, app_returncode)

    monkeypatch.setattr(start_pb_studio.subprocess, "run", fake_run)
    return calls


def _app_call(calls: list[dict]) -> dict:
    return [c for c in calls if "--version" not in c["cmd"]][-1]


def test_launcher_sets_batch_runtime_env(monkeypatch, tmp_path):
    """B-711: PB_REQUIRE_NVENC / KMP / OMP / MKL wie in start_pb_studio.bat."""
    calls = _prepare(monkeypatch, tmp_path, app_returncode=0)

    start_pb_studio.main()

    env = _app_call(calls)["kwargs"]["env"]
    assert env["CUDA_MODULE_LOADING"] == "LAZY"
    assert env["PB_REQUIRE_NVENC"] == "1"
    assert env["KMP_DUPLICATE_LIB_OK"] == "TRUE"
    assert env["OMP_NUM_THREADS"] == "4"
    assert env["MKL_NUM_THREADS"] == "4"


def test_launcher_env_matches_batch_reference(monkeypatch, tmp_path):
    """Gegenprobe gegen den kanonischen Referenzstand start_pb_studio.bat."""
    bat = (Path(__file__).resolve().parents[2] / "start_pb_studio.bat").read_text(
        encoding="utf-8"
    )
    expected = {}
    for line in bat.splitlines():
        stripped = line.strip()
        if not stripped.lower().startswith("set ") or stripped.startswith("set \""):
            continue
        assignment = stripped[4:]
        if "=" not in assignment:
            continue
        key, value = assignment.split("=", 1)
        expected[key.strip()] = value.strip()

    assert expected, "Keine set-Zuweisungen in start_pb_studio.bat gefunden"

    calls = _prepare(monkeypatch, tmp_path, app_returncode=0)
    start_pb_studio.main()
    env = _app_call(calls)["kwargs"]["env"]

    for key, value in expected.items():
        assert env.get(key) == value, f"{key} fehlt/abweichend im Python-Launcher"


def test_launcher_propagates_app_exit_code(monkeypatch, tmp_path):
    """B-712: Nicht-null Exit-Code der App muss durchgereicht werden."""
    _prepare(monkeypatch, tmp_path, app_returncode=3)

    with pytest.raises(SystemExit) as excinfo:
        start_pb_studio.main()

    assert excinfo.value.code == 3


def test_launcher_writes_stderr_to_file_during_run(monkeypatch, tmp_path):
    """stderr geht live in outputs\\app_run_*_err.log statt in eine PIPE."""
    calls = _prepare(monkeypatch, tmp_path, app_returncode=0)

    start_pb_studio.main()

    kwargs = _app_call(calls)["kwargs"]
    assert kwargs.get("stderr") is not subprocess.PIPE
    assert hasattr(kwargs.get("stderr"), "write")
    logs = list((tmp_path / "outputs").glob("app_run_*_err.log"))
    assert logs, "Kein stderr-Logfile unter outputs/ angelegt"
