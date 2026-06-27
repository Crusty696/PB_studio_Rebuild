"""B-570: real Qt child process must exit with cancelled live QThread."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


def test_cancelled_live_qthread_does_not_keep_app_process_alive():
    repo_root = Path(__file__).resolve().parents[2]
    child = repo_root / "tests" / "repro" / "b570_shutdown_child.py"
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"

    try:
        result = subprocess.run(
            [sys.executable, str(child)],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = f"{exc.stdout or ''}\n{exc.stderr or ''}"
        raise AssertionError(f"B-570 child timeout:\n{output}") from exc

    output = f"{result.stdout}\n{result.stderr}"
    assert result.returncode == 0, output
    assert (
        "B570_CHILD_EXIT_OK" in output
        or "B570_CHILD_WAITING_HARD_EXIT" in output
    ), output
    assert "B570_CHILD_HARD_EXIT_MISSING" not in output
