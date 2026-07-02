from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


_REPO = Path(__file__).resolve().parents[2]
_OUT = _REPO / "tests" / "qa_artifacts" / "release_cutover_manifest.json"


def _run_manifest() -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "scripts/diag/verify_release_cutover_manifest.py"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Traceback" not in result.stderr
    assert _OUT.is_file()
    return json.loads(_OUT.read_text(encoding="utf-8"))


def test_release_cutover_manifest_reports_release_ready_when_gate_is_clear() -> None:
    payload = _run_manifest()

    assert payload["status"] == "pass"
    assert payload["release_ready"] is True
    assert payload["open_blocker_ids"] == []
    assert "tools\\release_gate.py" in payload["final_gate_command"]


def test_release_cutover_manifest_has_no_actions_when_gate_is_clear() -> None:
    payload = _run_manifest()

    assert payload["required_actions"] == []
