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


def test_release_cutover_manifest_keeps_release_blocked() -> None:
    payload = _run_manifest()

    assert payload["status"] == "blocked"
    assert payload["release_ready"] is False
    assert {"DG-001", "SIGN-001", "VM-001", "GUI-001"}.issubset(payload["open_blocker_ids"])
    assert "tools\\release_gate.py" in payload["final_gate_command"]


def test_release_cutover_manifest_has_action_for_each_current_blocker() -> None:
    payload = _run_manifest()
    action_ids = {action["blocker_id"] for action in payload["required_actions"]}

    assert {"DG-001", "SIGN-001", "VM-001", "GUI-001"}.issubset(action_ids)
    assert any("verify_signing_readiness.py" in str(action) for action in payload["required_actions"])
    assert any("verify_clean_vm_readiness.py" in str(action) for action in payload["required_actions"])
    assert any("verify_installed_app_gui_workflow.py --write-proof" in str(action) for action in payload["required_actions"])
    assert all(action["clears_release_gate"] is False for action in payload["required_actions"])
