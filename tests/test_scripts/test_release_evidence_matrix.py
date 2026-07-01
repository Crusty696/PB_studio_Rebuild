from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


_REPO = Path(__file__).resolve().parents[2]
_MATRIX = _REPO / "tests" / "qa_artifacts" / "release_evidence_matrix.json"


def _run_matrix() -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "scripts/diag/verify_release_evidence_matrix.py"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Traceback" not in result.stderr
    assert _MATRIX.is_file()
    return json.loads(_MATRIX.read_text(encoding="utf-8"))


def test_release_evidence_matrix_matches_current_gate_blockers() -> None:
    payload = _run_matrix()
    open_ids = {item["id"] for item in payload["open_items"]}

    assert payload["release_ready"] is False
    assert payload["status"] == "blocked"
    assert {"DG-001", "SIGN-001", "VM-001", "GUI-001"}.issubset(open_ids)
    assert payload["release_gate_proofs"] == []


def test_release_evidence_matrix_keeps_required_qa_sources_visible() -> None:
    payload = _run_matrix()
    sources = payload["qa_json_sources"]

    required_sources = {
        "release_artifact_pair_audit",
        "signing_readiness",
        "clean_vm_readiness",
        "installed_app_gui_readiness",
        "installed_app_gui_workflow",
        "frozen_gui_workflow",
    }
    assert required_sources == set(sources)
    assert sources["release_artifact_pair_audit"]["release_ready"] is False
    assert sources["signing_readiness"]["release_signing_ready"] is False
    assert sources["clean_vm_readiness"]["clean_vm_ready"] is False
    assert sources["installed_app_gui_readiness"]["installed_app_gui_ready"] is False
    assert sources["installed_app_gui_workflow"]["proof_written"] is False
    assert sources["frozen_gui_workflow"]["proof_written"] is False
