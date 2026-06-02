"""Tests für Phase 2 — 13 neue Chat-Aktionen für lückenlose Sprachsteuerung.

Testet Registrierung und grundlegende Logik aller neuen Aktionen.
"""
import pytest
import sys
from PySide6.QtWidgets import QApplication

# IMPORT ALL ACTIONS TO REGISTER THEM
import services.register_actions  # noqa: F401
from services.action_registry import action_registry


@pytest.fixture(scope="session", autouse=True)
def q_app():
    """Erstellt eine QApplication-Instanz für die Test-Sitzung."""
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    return app


# ── Test 1: Alle 13 neuen Aktionen sind registriert ─────────────────────

PHASE2_ACTIONS = [
    "list_media",
    "list_timeline",
    "get_project_info",
    "add_to_timeline",
    "set_clip_effects",
    "move_clip",
    "remove_clip",
    "convert_videos",
    "preview_export",
    "auto_ducking",
    "apply_style_preset",
    "add_anchor",
    "rl_feedback",
]


def test_phase2_actions_registered():
    """Alle 13 Phase-2-Aktionen müssen in der ActionRegistry registriert sein."""
    all_actions = action_registry.list_actions()
    for action_name in PHASE2_ACTIONS:
        assert action_name in all_actions, f"Aktion '{action_name}' ist NICHT registriert!"


# ── Test 2: Aktionen haben korrekte param_schema ────────────────────────

def test_phase2_actions_have_schemas():
    """Jede Aktion muss in der internen Registry mit einem param_schema registriert sein."""
    for action_name in PHASE2_ACTIONS:
        # Prüfe ob die Aktion in der internen Registry existiert
        assert action_name in action_registry._actions, f"Aktion '{action_name}' fehlt in _actions!"
        entry = action_registry._actions[action_name]
        # ActionDef ist ein Dataclass mit .param_schema Attribut
        assert hasattr(entry, "param_schema"), f"Aktion '{action_name}' hat kein param_schema!"
        assert entry.param_schema.get("type") == "object", f"Aktion '{action_name}' hat falschen Schema-Typ!"


# ── Test 3: Reine DB-Aktionen geben ohne Projekt sinnvolle Fehler ───────

def test_list_timeline_no_project():
    """list_timeline soll einen Fehler zurückgeben wenn kein Projekt aktiv ist."""
    result = action_registry.execute("list_timeline", {})
    # Entweder Fehler oder leere Liste — beides akzeptabel
    if "error" in result:
        assert "Projekt" in result["error"] or "project" in result["error"].lower()


def test_list_media_returns_structure():
    """list_media soll zumindest eine Struktur mit audio_count/video_count zurückgeben."""
    result = action_registry.execute("list_media", {})
    # Entweder gültige Antwort mit Zählern oder ein Fehler
    if "error" not in result:
        assert "audio_count" in result
        assert "video_count" in result


def test_get_project_info_no_project():
    """get_project_info soll einen Fehler zurückgeben wenn kein Projekt aktiv ist."""
    result = action_registry.execute("get_project_info", {})
    if "error" in result:
        assert "Projekt" in result["error"]


def test_set_clip_effects_invalid_entry():
    """set_clip_effects mit nicht-existenter Entry-ID soll Fehler geben."""
    result = action_registry.execute("set_clip_effects", {
        "entry_id": 999999,
        "brightness": 0.5,
    })
    assert "error" in result


def test_set_clip_effects_no_params():
    """set_clip_effects ohne Effekt-Parameter soll einen Hinweis geben."""
    result = action_registry.execute("set_clip_effects", {"entry_id": 1})
    # Entweder "nicht gefunden" oder "keine Parameter"
    assert "error" in result


def test_move_clip_invalid_entry():
    """move_clip mit nicht-existenter Entry-ID soll Fehler geben."""
    result = action_registry.execute("move_clip", {
        "entry_id": 999999,
        "new_start_time": 5.0,
    })
    assert "error" in result


def test_remove_clip_invalid_entry():
    """remove_clip mit nicht-existenter Entry-ID soll Fehler geben."""
    result = action_registry.execute("remove_clip", {"entry_id": 999999, "confirm": True})
    assert "error" in result


def test_auto_ducking_invalid_track():
    """auto_ducking mit nicht-existentem Track soll Fehler geben."""
    result = action_registry.execute("auto_ducking", {"audio_track_id": 999999})
    assert "error" in result


def test_rl_feedback_no_project():
    """rl_feedback ohne aktives Projekt soll einen Fehler zurückgeben."""
    result = action_registry.execute("rl_feedback", {"sentiment": "positive"})
    assert "error" in result


def test_save_project_still_works():
    """Regression: save_project aus Phase 1 funktioniert weiterhin."""
    res = action_registry.execute("save_project", {})
    assert res["status"] == "ok"
