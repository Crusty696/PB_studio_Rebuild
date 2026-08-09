"""B-792: Der Chat zeigt die fertige Action-Message statt des Roh-Dicts.

Live 2026-08-09: nach dem B-791-Fix wurde "Wie viele Clips hat dieses
Projekt?" korrekt an ``summarize_project`` geroutet — im Chat landete
aber ``str(<ganzes Ergebnis-Dict>)``, also alle 486 Video-Datensaetze
ueber mehrere Bildschirmseiten. Der fertige Satz lag in
``result["message"]`` bereit und wurde ignoriert
(``ui/chat_dock.py``: ``message`` wurde nur im Zweig ``action == "none"``
ausgewertet).

Vertraege:
1. Dict mit nicht-leerer ``message`` -> genau diese Message.
2. Dict ohne ``message`` -> Bestandsverhalten (``str(dict)``).
3. ``None`` -> ``None`` (kein "None"-Text im Chat).
4. Nicht-Dict-Ergebnisse -> Bestandsverhalten.
5. Leere/whitespace-Message zaehlt nicht als Message (Fallback).
6. Gilt fuer Single- UND Multi-Action-Zweig (dieselbe Helper-Funktion).
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from ui.chat_dock import ChatDock

_readable = ChatDock._readable_action_result

# Verkuerzt nachgebaut aus services/actions/ai_actions.py::summarize_project
_SUMMARIZE_RESULT = {
    "status": "ok",
    "action": "summarize_project",
    "project_id": 1,
    "audio_count": 1,
    "video_count": 486,
    "scene_count": 451,
    "videos": [{"id": i, "fps": 30.0, "resolution": "1920x1080"} for i in range(486)],
    "message": "Projekt #1: 1 Audio-Tracks, 486 Video-Clips, 451 Szenen erkannt.",
}


def test_message_is_preferred_over_raw_dict():
    out = _readable(_SUMMARIZE_RESULT)
    assert out == "Projekt #1: 1 Audio-Tracks, 486 Video-Clips, 451 Szenen erkannt."
    # Der eigentliche Bug: keine Rohdaten mehr im Chat.
    assert "'resolution'" not in out
    assert "1920x1080" not in out
    assert len(out) < 200, "Chat-Ausgabe darf keine Datensatzliste sein"


def test_dict_without_message_keeps_old_behaviour():
    payload = {"status": "ok", "action": "x", "value": 42}
    assert _readable(payload) == str(payload)


def test_none_stays_none():
    assert _readable(None) is None


@pytest.mark.parametrize("payload", ["fertig", 42, ["a", "b"]])
def test_non_dict_results_keep_old_behaviour(payload):
    assert _readable(payload) == str(payload)


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_blank_message_falls_back_to_dict(blank):
    payload = {"status": "ok", "message": blank, "value": 1}
    assert _readable(payload) == str(payload)


def test_non_string_message_falls_back():
    payload = {"status": "ok", "message": {"nested": "dict"}, "value": 1}
    assert _readable(payload) == str(payload)


def test_both_action_branches_use_the_helper():
    """Vertrag 6: Single- und Multi-Action gehen durch dieselbe Regel."""
    import inspect

    src = inspect.getsource(ChatDock._on_agent_finished)
    assert src.count("_readable_action_result(") >= 2, (
        "Single- und Multi-Action-Zweig muessen beide den Helper nutzen"
    )
    assert "str(act_result)" not in src
    assert "str(action_result)" not in src
