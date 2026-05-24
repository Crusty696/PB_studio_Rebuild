import pytest
from services.action_registry import action_registry

# Die 10 neuen Aktionen der Phase 3
PHASE3_ACTIONS = [
    "save_project_as",
    "undo_timeline",
    "redo_timeline",
    "sync_anchors",
    "remove_anchor",
    "learn_anchor",
    "clear_search",
    "refresh_media",
    "list_projects",
    "get_settings",
    "cancel_task"
]

def test_phase3_actions_registered():
    """Prüfe ob alle Phase 3 Aktionen in der ActionRegistry vorhanden sind."""
    # Stellt sicher, dass das Modul geladen wird und die Decorators feuern
    import services.actions.edit_actions  # noqa: F401
    
    registered_names = list(action_registry._actions.keys())
    
    for action_name in PHASE3_ACTIONS:
        assert action_name in registered_names, f"Aktion '{action_name}' ist nicht registriert!"

def test_phase3_actions_have_schemas():
    """Jede Aktion muss in der internen Registry mit einem param_schema registriert sein."""
    for action_name in PHASE3_ACTIONS:
        assert action_name in action_registry._actions, f"Aktion '{action_name}' fehlt in _actions!"
        entry = action_registry._actions[action_name]
        assert hasattr(entry, "param_schema"), f"Aktion '{action_name}' hat kein param_schema!"
        assert entry.param_schema.get("type") == "object", f"Aktion '{action_name}' hat falschen Schema-Typ!"
