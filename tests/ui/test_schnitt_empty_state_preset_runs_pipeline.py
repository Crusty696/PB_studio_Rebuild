"""B-294: SCHNITT Empty-State Preset-Klick muss Pipeline starten, nicht silent return.
Adapter ruft _ensure_combos_filled_from_project."""
from __future__ import annotations

import inspect

from ui.controllers.edit_workspace import EditWorkspaceController


def test_b294_ensure_combos_filled_helper_exists():
    assert hasattr(EditWorkspaceController, "_ensure_combos_filled_from_project")


def test_b294_auto_edit_adapter_calls_ensure_combos():
    src = inspect.getsource(EditWorkspaceController._on_schnitt_auto_edit_request)
    assert "_ensure_combos_filled_from_project" in src, (
        "B-294: _on_schnitt_auto_edit_request ruft Auto-Fill-Helper nicht."
    )


def test_b294_regenerate_adapter_calls_ensure_combos():
    src = inspect.getsource(EditWorkspaceController._on_schnitt_regenerate_request)
    assert "_ensure_combos_filled_from_project" in src, (
        "B-294: _on_schnitt_regenerate_request ruft Auto-Fill-Helper nicht."
    )


def test_b294_ensure_combos_signature():
    sig = inspect.signature(EditWorkspaceController._ensure_combos_filled_from_project)
    # Method should return bool, no extra args besides self
    assert sig.return_annotation in (bool, "bool"), (
        f"B-294: _ensure_combos_filled_from_project sollte -> bool zurueckgeben (sig={sig})"
    )
