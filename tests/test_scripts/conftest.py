from __future__ import annotations

from pathlib import Path
import pytest

_REPO = Path(__file__).resolve().parents[2]

_RELEASE_TEST_FILES = {
    "test_clean_vm_readiness.py",
    "test_distribution_bundle_candidate.py",
    "test_installed_app_gui_readiness.py",
    "test_installed_app_gui_workflow.py",
    "test_release_cutover_manifest.py",
    "test_release_evidence_matrix.py",
    "test_signing_readiness.py",
    "test_prune_pyinstaller_dist.py",
    "test_frozen_gui_workflow.py",
}


def pytest_runtest_setup(item: pytest.Item) -> None:
    # Holt den Dateinamen des Testmoduls (z.B. test_clean_vm_readiness.py)
    module_name = Path(item.fspath).name
    if module_name in _RELEASE_TEST_FILES:
        dist_dir = _REPO / "dist"
        if not dist_dir.is_dir():
            pytest.skip(
                f"Release-Artefakte (dist/) fehlen — {module_name} wird uebersprungen."
            )
