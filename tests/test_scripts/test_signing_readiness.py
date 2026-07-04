from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


_REPO = Path(__file__).resolve().parents[2]
_OUT = _REPO / "tests" / "qa_artifacts" / "signing_readiness.json"


def _run_signing_readiness() -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "scripts/diag/verify_signing_readiness.py"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Traceback" not in result.stderr
    assert _OUT.is_file()
    return json.loads(_OUT.read_text(encoding="utf-8"))


def test_signing_readiness_reports_installer_signature_state() -> None:
    payload = _run_signing_readiness()

    assert payload["installer_exists"] is True
    assert payload["authenticode"]["checked"] is True
    if payload["authenticode"]["signed"]:
        assert "installer-not-signed" not in payload["blockers"]
        assert payload["authenticode"]["signer_thumbprint"]
    else:
        assert payload["release_signing_ready"] is True
        assert payload["signing_required_for_private_distribution"] is False
        assert payload["unsigned_installer_allowed_for_private_distribution"] is True
        assert "installer-not-signed" not in payload["blockers"]


def test_signing_readiness_reports_signtool_source() -> None:
    payload = _run_signing_readiness()

    assert "signtool_path_source" in payload
    assert isinstance(payload["signtool_candidates"], list)
    if payload["signtool"]:
        assert payload["signtool_path_source"] in {"PATH", "Windows Kits"}
        assert "signtool-missing" not in payload["blockers"]
