"""Regression tests for release-gate CLI and handoff integration."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

_REPO = Path(__file__).resolve().parents[2]


def test_release_gate_survives_strict_cp1252_output():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "cp1252:strict"

    result = subprocess.run(
        [sys.executable, "tools/release_gate.py"],
        cwd=_REPO,
        env=env,
        capture_output=True,
        text=True,
        encoding="cp1252",
        errors="strict",
        check=False,
    )

    assert result.returncode == 2
    assert "RELEASE-GATE BLOCKED" in result.stdout
    assert "DG-001" in result.stdout
    assert "Traceback" not in result.stderr


def test_agent_handoff_distinguishes_gate_failure_from_open_gate():
    script = (_REPO / "tools" / "agent_handoff.ps1").read_text(encoding="utf-8")

    assert "$gateExit -notin @(0, 2)" in script
    assert "Release gate execution failed" in script
