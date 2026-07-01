from __future__ import annotations

from pathlib import Path


_REPO = Path(__file__).resolve().parents[2]


def test_frozen_gui_workflow_wrapper_targets_separate_artifact() -> None:
    script = (_REPO / "scripts" / "diag" / "verify_frozen_gui_workflow.py").read_text(encoding="utf-8")

    assert "frozen_gui_workflow.json" in script
    assert "--output" in script
    assert "--artifact-label" in script
    assert "--write-proof" not in script


def test_frozen_gui_workflow_wrapper_selects_verifier_python_with_gui_deps() -> None:
    script = (_REPO / "scripts" / "diag" / "verify_frozen_gui_workflow.py").read_text(encoding="utf-8")

    assert "PB_GUI_VERIFIER_PYTHON" in script
    assert "REQUIRED_VERIFIER_MODULES" in script
    assert "pygetwindow" in script
    assert "pywinauto" in script
    assert "pyautogui" in script
    assert "_verifier_python()" in script


def test_main_faulthandler_does_not_require_stderr_in_windowed_frozen_app() -> None:
    main = (_REPO / "main.py").read_text(encoding="utf-8")

    assert "if _fault_handler_target is None:" in main
    assert "freeze_stacks.log" in main
    assert "_faulthandler.enable(file=_fault_handler_target)" in main
    assert "diagnostics must not kill GUI startup" in main
