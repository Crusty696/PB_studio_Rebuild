from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


_REPO = Path(__file__).resolve().parents[2]
_OUT = _REPO / "tests" / "qa_artifacts" / "installed_app_gui_readiness.json"


def _run_readiness() -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "scripts/diag/verify_installed_app_gui_readiness.py"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Traceback" not in result.stderr
    assert _OUT.is_file()
    return json.loads(_OUT.read_text(encoding="utf-8"))


def test_installed_app_gui_readiness_reports_private_user_install_ready() -> None:
    payload = _run_readiness()

    assert payload["installed_app_gui_ready"] is True
    assert payload["blockers"] == []
    assert payload["installer"]["exists"] is True
    assert payload["payload"]["exists"] is True
    assert payload["installed_exe"]["is_file"] is True
    assert "installer-not-signed" not in payload["blockers"]
    assert "This preflight does not install PB Studio" in payload["note"]


def test_installed_app_gui_readiness_reports_install_detection_sources() -> None:
    payload = _run_readiness()

    assert isinstance(payload["installed_exe_candidates"], list)
    assert payload["installed_exe_candidates"]
    assert "installed_app_registry_entries" in payload
    assert "checked" in payload["installed_app_registry_entries"]
    if "installed-exe-missing" in payload["blockers"]:
        assert not any(candidate["is_file"] for candidate in payload["installed_exe_candidates"])


def test_installed_app_gui_readiness_reports_user_scope_installer_policy() -> None:
    payload = _run_readiness()
    policy = payload["nsi_install_policy"]

    assert policy["requests_admin"] is False
    assert policy["requests_user"] is True
    assert policy["program_files_default"] is False
    assert policy["local_appdata_default"] is True
    assert policy["writes_hklm_uninstall_key"] is False
    assert policy["writes_hkcu_uninstall_key"] is True
