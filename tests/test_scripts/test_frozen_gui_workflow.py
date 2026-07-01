from __future__ import annotations

from pathlib import Path


_REPO = Path(__file__).resolve().parents[2]


def test_frozen_gui_workflow_wrapper_targets_separate_artifact() -> None:
    script = (_REPO / "scripts" / "diag" / "verify_frozen_gui_workflow.py").read_text(encoding="utf-8")

    assert "frozen_gui_workflow.json" in script
    assert "--output" in script
    assert "--artifact-label" in script
    assert "--write-proof" not in script
