"""B-037: Verify Bandit-Security-Scanner Setup.

- ``bandit.yaml`` Repo-Config existiert mit relevanten exclude_dirs.
- ``requirements-py310-cu113.txt`` hat ``bandit`` als Dev-Dep.
- ``.github/workflows/ci.yml`` laeuft Bandit auf master + branches.
- ``services/graph/sigma_renderer.py:_stable_position`` markiert
  SHA1-Layout-Hash mit ``usedforsecurity=False`` (B324-Mitigation).
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_b037_bandit_yaml_config_exists() -> None:
    cfg = REPO_ROOT / "bandit.yaml"
    assert cfg.exists(), "B-037: bandit.yaml fehlt im Repo-Root"
    text = cfg.read_text(encoding="utf-8")
    assert "exclude_dirs" in text
    assert "tests" in text  # exclude_dirs muss tests enthalten
    assert "vendor" in text  # exclude_dirs muss vendor enthalten


def test_b037_bandit_in_dev_requirements() -> None:
    req = REPO_ROOT / "requirements-py310-cu113.txt"
    text = req.read_text(encoding="utf-8")
    assert "bandit" in text, (
        "B-037: bandit fehlt in requirements-py310-cu113.txt"
    )


def test_b037_ci_workflow_uses_bandit_on_master() -> None:
    ci = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    text = ci.read_text(encoding="utf-8")
    # Branches haben jetzt master drin (vorher nur main + feature/fix)
    assert '"master"' in text, (
        "B-037: CI-Trigger hat master nicht — Master-Pushes werden ignoriert"
    )
    # Bandit-Step nutzt die Config-Datei
    assert "bandit -r . -c bandit.yaml" in text, (
        "B-037: CI laed bandit.yaml-Config nicht"
    )


def test_b037_sigma_renderer_marks_sha1_non_security() -> None:
    """``_stable_position`` nutzt SHA1 fuer Layout-Hashing — KEINE
    Sicherheits-Verwendung. ``usedforsecurity=False`` muss explizit
    gesetzt sein, sonst flagged Bandit B324 als HIGH-Severity."""
    from services.graph import sigma_renderer

    src = inspect.getsource(sigma_renderer._stable_position)
    assert "usedforsecurity=False" in src, (
        "B-037: sigma_renderer SHA1-Hash markiert nicht "
        "usedforsecurity=False — Bandit B324 schlaegt fehl"
    )
