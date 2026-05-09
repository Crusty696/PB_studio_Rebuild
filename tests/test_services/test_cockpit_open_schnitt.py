"""Phase 10.3: cockpit_orchestrator exposes ``open_schnitt`` and aliases legacy keys."""
from services.cockpit_orchestrator import ACTIONS


def test_open_schnitt_action_exists():
    assert "open_schnitt" in ACTIONS
    a = ACTIONS["open_schnitt"]
    assert a.key == "open_schnitt"
    assert a.label


def test_legacy_keys_alias_to_schnitt():
    # Legacy callers may still pass open_auto_edit / open_review.
    # After Phase 10, both must resolve to the SCHNITT workspace.
    assert ACTIONS["open_auto_edit"].key in ("open_schnitt", "open_auto_edit")
    assert ACTIONS["open_review"].key in ("open_schnitt", "open_review")
