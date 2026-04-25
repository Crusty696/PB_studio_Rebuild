"""B-116 + B-121 regression test:

Tests that ``_run_ffmpeg`` (export) and ``_run_ffmpeg_with_progress``
(convert) accept a ``cancel_check`` callable and kill the subprocess
within a bounded time window when the callable returns True.

We don't need real ffmpeg — Python sleeping subprocesses behave the
same way for our cancel-path. The progress-parsing is bypassed since
our fake process emits nothing on stdout.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from unittest.mock import patch

import pytest


def _make_long_running_cmd(seconds: int = 30) -> list[str]:
    """A subprocess that lives for ``seconds`` seconds with no stdout output.
    On Windows + Linux the python interpreter is available."""
    return [sys.executable, "-c", f"import time; time.sleep({seconds})"]


def test_export_run_ffmpeg_accepts_and_honours_cancel_check() -> None:
    """``services.export_service._run_ffmpeg`` must accept a
    ``cancel_check`` callable and kill the subprocess shortly after it
    returns True."""
    from services import export_service

    # The function must accept cancel_check parameter.
    import inspect
    sig = inspect.signature(export_service._run_ffmpeg)
    assert "cancel_check" in sig.parameters, (
        "BUG-116 regression: _run_ffmpeg must accept a cancel_check "
        "kwarg so callers can stop ffmpeg mid-run."
    )

    cancel_event = threading.Event()
    cancel_check = lambda: cancel_event.is_set()

    # Run on a background thread so the test thread can flip the cancel.
    error: list[BaseException] = []
    finished = threading.Event()

    def _runner():
        try:
            export_service._run_ffmpeg(
                _make_long_running_cmd(seconds=30),
                timeout=60,
                cancel_check=cancel_check,
            )
        except BaseException as exc:
            error.append(exc)
        finally:
            finished.set()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    time.sleep(0.5)
    cancel_event.set()
    finished.wait(timeout=5.0)

    assert finished.is_set(), (
        "BUG-116 regression: _run_ffmpeg did not return within 5s after "
        "cancel_check became True. Subprocess was not killed."
    )
    # We expect a RuntimeError ("abgebrochen") or similar — but tolerate
    # any exception that signals the cancel landed.
    assert error, (
        "_run_ffmpeg should raise on cancel (so callers can distinguish "
        "from successful completion)."
    )


def test_convert_run_ffmpeg_accepts_and_honours_cancel_check() -> None:
    """``services.convert_service._run_ffmpeg_with_progress`` must
    likewise accept ``cancel_check``."""
    from services import convert_service

    import inspect
    sig = inspect.signature(convert_service._run_ffmpeg_with_progress)
    assert "cancel_check" in sig.parameters, (
        "BUG-116 regression: _run_ffmpeg_with_progress must accept a "
        "cancel_check kwarg."
    )

    cancel_event = threading.Event()
    cancel_check = lambda: cancel_event.is_set()

    error: list[BaseException] = []
    finished = threading.Event()

    def _runner():
        try:
            convert_service._run_ffmpeg_with_progress(
                _make_long_running_cmd(seconds=30),
                total_duration=30.0,
                progress_cb=None,
                cancel_check=cancel_check,
            )
        except BaseException as exc:
            error.append(exc)
        finally:
            finished.set()

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    time.sleep(0.5)
    cancel_event.set()
    finished.wait(timeout=5.0)

    assert finished.is_set(), (
        "BUG-116 regression: _run_ffmpeg_with_progress did not return "
        "within 5s after cancel_check became True."
    )
    assert error, "_run_ffmpeg_with_progress should raise on cancel."
