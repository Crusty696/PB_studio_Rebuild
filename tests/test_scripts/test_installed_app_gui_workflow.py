from __future__ import annotations

import importlib.util
from pathlib import Path


_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts" / "diag" / "verify_installed_app_gui_workflow.py"


def _module():
    spec = importlib.util.spec_from_file_location("verify_installed_app_gui_workflow", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_installed_app_gui_workflow_accepts_current_nav_labels() -> None:
    module = _module()

    observed = module._observed_label_groups(["PROJEKT", "MATERIAL ANALYSE", "SCHNITT", "EXPORT"])

    assert set(observed) == {"project", "material", "schnitt", "export"}


def test_installed_app_gui_workflow_rejects_not_responding_window() -> None:
    module = _module()

    assert module._window_responsive({"title": "PB_studio v0.5.0"}) is True
    assert module._window_responsive({"title": "PB_studio v0.5.0 (Keine Rückmeldung)"}) is False
    assert module._window_responsive({"title": "PB_studio v0.5.0 (Not Responding)"}) is False


def test_installed_app_gui_workflow_handles_missing_window_pid() -> None:
    module = _module()

    assert module._window_process_id(None) is None
    assert module._window_process_id({}) is None


def test_installed_app_gui_workflow_can_write_to_custom_output(tmp_path) -> None:
    module = _module()
    target = tmp_path / "custom.json"

    module._write_json_to(target, {"ok": True})

    assert target.read_text(encoding="utf-8").strip() == '{\n  "ok": true\n}'
