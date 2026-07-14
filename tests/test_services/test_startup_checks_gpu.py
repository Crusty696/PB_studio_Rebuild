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


@pytest.fixture(autouse=True)
def _reset_gpu_cache() -> None:
    """B-630: isolate the module-level session cache between tests."""
    startup_checks._GPU_STATE_CACHE = None
    yield
    startup_checks._GPU_STATE_CACHE = None


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


# ---------------------------------------------------------------------------
# B-630: session cache — the Qt main-thread boot path must not shell out
# ---------------------------------------------------------------------------


def test_cached_read_avoids_subprocess_on_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    """B-630: force_refresh=False reuses the cached state and NEVER launches
    the PowerShell subprocess — this is what keeps the Qt main thread from
    freezing during boot.
    """
    # 1. Prime the cache with a fresh (default) query — this is the pre-CUDA
    #    module-load call in main.py that runs BEFORE Qt loads.
    payload = json.dumps({"Status": "OK", "ConfigManagerErrorCode": 0})
    _patch_run(monkeypatch, _FakeCompleted(stdout=payload))
    state, _ = startup_checks.check_nvidia_gpu_state()
    assert state == "ok"

    # 2. Make ANY subprocess launch fail loudly. The cached boot-path read must
    #    not touch it.
    def _must_not_run(*_a, **_k):
        raise AssertionError("subprocess.run must not be called on the cached path")

    monkeypatch.setattr(startup_checks.subprocess, "run", _must_not_run)

    cached_state, _ = startup_checks.check_nvidia_gpu_state(force_refresh=False)
    assert cached_state == "ok"


def test_cached_read_falls_through_when_cache_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """B-630: force_refresh=False with an empty cache falls back to a fresh
    query instead of returning a bogus/None result.
    """
    payload = json.dumps({"Status": "OK", "ConfigManagerErrorCode": 0})
    _patch_run(monkeypatch, _FakeCompleted(stdout=payload))

    # Cache is reset to None by the autouse fixture -> must query fresh.
    state, _ = startup_checks.check_nvidia_gpu_state(force_refresh=False)
    assert state == "ok"


def test_force_refresh_requeries_and_updates_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """B-630: force_refresh=True (wake-retry / recovery re-check) must query
    fresh even when a cached value exists, and update the cache afterwards.
    """
    # Prime cache = stuck state.
    _patch_run(monkeypatch, _FakeCompleted(stdout=json.dumps({"ConfigManagerErrorCode": 47})))
    state, _ = startup_checks.check_nvidia_gpu_state()
    assert state == "held_for_eject"

    # GPU recovered after user detach/reattach; forced re-check must see it.
    _patch_run(monkeypatch, _FakeCompleted(stdout=json.dumps({"ConfigManagerErrorCode": 0})))
    state2, _ = startup_checks.check_nvidia_gpu_state(force_refresh=True)
    assert state2 == "ok"

    # Cache now reflects the recovered state for later cached reads.
    def _must_not_run(*_a, **_k):
        raise AssertionError("cached read must not shell out")

    monkeypatch.setattr(startup_checks.subprocess, "run", _must_not_run)
    state3, _ = startup_checks.check_nvidia_gpu_state(force_refresh=False)
    assert state3 == "ok"
