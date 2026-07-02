from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


_REPO = Path(__file__).resolve().parents[2]
_OUT = _REPO / "tests" / "qa_artifacts" / "clean_vm_readiness.json"


def _run_clean_vm_readiness() -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "scripts/diag/verify_clean_vm_readiness.py"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Traceback" not in result.stderr
    assert _OUT.is_file()
    return json.loads(_OUT.read_text(encoding="utf-8"))


def test_clean_vm_readiness_reports_ready_when_sandbox_tooling_and_artifacts_exist() -> None:
    payload = _run_clean_vm_readiness()

    assert payload["clean_vm_ready"] is True
    assert payload["installer"]["exists"] is True
    assert payload["payload"]["exists"] is True
    assert payload["payload"]["size_bytes"] > 1024**3
    assert "This preflight does not run a clean VM install" in payload["note"]


def test_clean_vm_readiness_reports_vm_tool_detection_details() -> None:
    payload = _run_clean_vm_readiness()
    tools = payload["vm_tools"]

    assert {"Get-VM", "vmrun", "VBoxManage"} == set(tools)
    assert "checked" in tools["Get-VM"]
    assert isinstance(tools["vmrun"]["candidates"], list)
    assert isinstance(tools["VBoxManage"]["candidates"], list)
