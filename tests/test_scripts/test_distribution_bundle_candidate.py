from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


_REPO = Path(__file__).resolve().parents[2]
_OUT = _REPO / "tests" / "qa_artifacts" / "distribution_bundle_candidate.json"


def _run_verifier() -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "scripts/diag/verify_distribution_bundle_candidate.py"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Traceback" not in result.stderr
    assert _OUT.is_file()
    return json.loads(_OUT.read_text(encoding="utf-8"))


def test_distribution_bundle_candidate_is_ready_when_release_gate_is_clear() -> None:
    payload = _run_verifier()

    assert payload["status"] == "pass"
    assert payload["distribution_candidate_ready"] is True
    assert payload["can_create_distribution_zip"] is True
    assert payload["release_ready"] is True
    assert payload["open_blocker_ids"] == []
    assert payload["distribution_zip"]["exists"] is True
    assert payload["distribution_zip"]["required_entries_present"] is True


def test_distribution_bundle_candidate_records_required_inputs() -> None:
    payload = _run_verifier()

    assert payload["artifact_pair_ready"] is True
    assert payload["installer_exe"]["exists"] is True
    assert payload["installer_payload"]["exists"] is True
    assert payload["installer_payload"]["size_bytes"] > 1024**3
    assert all(doc["exists"] for doc in payload["required_docs"].values())
    assert payload["hard_checks"]["release_gate_ok"] is True
