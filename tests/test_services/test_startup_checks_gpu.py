"""Unit tests for ``services.startup_checks.check_nvidia_gpu_state``.

P16: Covers the four diagnostic states that the function must surface
(``ok`` / ``held_for_eject`` / ``absent`` / ``other_error``) plus the
failure modes of the underlying PowerShell subprocess (timeout,
CalledProcessError). All PowerShell invocations are mocked — tests must
never shell out to a real Windows PnP query.
"""

from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

from services import startup_checks


class _FakeCompleted:
    """Minimal stand-in for ``subprocess.CompletedProcess``."""

    def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _patch_run(monkeypatch: pytest.MonkeyPatch, behaviour):
    """Helper: replace ``subprocess.run`` with the given callable/return."""
    if callable(behaviour):
        monkeypatch.setattr(startup_checks.subprocess, "run", behaviour)
    else:
        monkeypatch.setattr(startup_checks.subprocess, "run", lambda *a, **k: behaviour)


@pytest.fixture(autouse=True)
def _force_win32(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend we are on Windows so the PnP branch is exercised."""
    monkeypatch.setattr(startup_checks.sys, "platform", "win32")


def test_check_returns_ok_for_normal_gpu(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"Status": "OK", "ConfigManagerErrorCode": 0})
    _patch_run(monkeypatch, _FakeCompleted(stdout=payload))

    state, msg = startup_checks.check_nvidia_gpu_state()

    assert state == "ok"
    assert msg is None


def test_check_returns_held_for_eject_on_code_47(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = json.dumps({"Status": "Error", "ConfigManagerErrorCode": 47})
    _patch_run(monkeypatch, _FakeCompleted(stdout=payload))

    state, msg = startup_checks.check_nvidia_gpu_state()

    assert state == "held_for_eject"
    assert msg is not None
    lowered = msg.lower()
    # Must mention reboot / neu starten so the dialog wording makes sense.
    assert "reboot" in lowered or "neu starten" in lowered


def test_check_returns_held_for_eject_when_list_contains_code_47(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ConvertTo-Json returns a list when multiple devices match."""
    payload = json.dumps(
        [
            {"Status": "OK", "ConfigManagerErrorCode": 0},
            {"Status": "Error", "ConfigManagerErrorCode": 47},
        ]
    )
    _patch_run(monkeypatch, _FakeCompleted(stdout=payload))

    state, _msg = startup_checks.check_nvidia_gpu_state()

    assert state == "held_for_eject"


def test_check_returns_absent_on_empty_output(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_run(monkeypatch, _FakeCompleted(stdout=""))

    state, msg = startup_checks.check_nvidia_gpu_state()

    assert state == "absent"
    assert msg is not None


def test_check_returns_other_error_on_unknown_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = json.dumps({"Status": "Error", "ConfigManagerErrorCode": 22})
    _patch_run(monkeypatch, _FakeCompleted(stdout=payload))

    state, msg = startup_checks.check_nvidia_gpu_state()

    assert state == "other_error"
    assert msg is not None
    assert "22" in msg


def test_check_returns_absent_on_subprocess_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_a, **_k):
        raise subprocess.CalledProcessError(returncode=1, cmd="powershell")

    _patch_run(monkeypatch, _boom)

    state, msg = startup_checks.check_nvidia_gpu_state()

    assert state == "absent"
    assert msg is not None


def test_check_returns_absent_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="powershell", timeout=5)

    _patch_run(monkeypatch, _boom)

    state, msg = startup_checks.check_nvidia_gpu_state()

    assert state == "absent"
    assert msg is not None
    assert "zeitlimit" in msg.lower() or "timeout" in msg.lower()
