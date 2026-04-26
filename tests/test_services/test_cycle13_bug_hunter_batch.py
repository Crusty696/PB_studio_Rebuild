"""Cycle 13 / Bug-Hunter Auto-Fix Batch.

BUG-1: project_manager public-API task_id durchreichen.
BUG-4: Studio-Brain source_start Reset-Logik.
BUG-5: ChatDock _on_send stoppt vorhandenen Watchdog.
BUG-6: Graph-Cockpit refresh debounced.
BUG-7: BrainService public session_factory.
BUG-8: GraphCockpitTab closeEvent cleanup.
"""
from __future__ import annotations

import inspect

import pytest


# ── BUG-1: ProjectManager API hat task_id-Parameter ───────────────────────


def test_bug1_create_project_accepts_task_id():
    from services.project_manager import ProjectManager
    sig = inspect.signature(ProjectManager.create_project)
    assert "task_id" in sig.parameters
    assert sig.parameters["task_id"].default is None


def test_bug1_open_project_accepts_task_id():
    from services.project_manager import ProjectManager
    sig = inspect.signature(ProjectManager.open_project)
    assert "task_id" in sig.parameters
    assert sig.parameters["task_id"].default is None


def test_bug1_save_project_as_accepts_task_id():
    from services.project_manager import ProjectManager
    sig = inspect.signature(ProjectManager.save_project_as)
    assert "task_id" in sig.parameters
    assert sig.parameters["task_id"].default is None


def test_bug1_create_project_passes_task_id_through(monkeypatch):
    """Wenn task_id übergeben wird, muss _wait_for_tasks_idle es bekommen."""
    from services.project_manager import ProjectManager
    pm = ProjectManager()

    captured = {}

    def _spy(self_arg, timeout_sec=10.0, exclude_task_id=None, **kwargs):
        captured["exclude_task_id"] = exclude_task_id
        return True  # idle

    # Wir patchen die unbound Methode auf der Klasse, weil _wait_for_tasks_idle
    # ein @staticmethod ist
    def _spy_static(timeout_sec=10.0, poll_interval_sec=0.2, exclude_task_id=None):
        captured["exclude_task_id"] = exclude_task_id
        return True

    monkeypatch.setattr(ProjectManager, "_wait_for_tasks_idle", staticmethod(_spy_static))

    # tatsächliche Projekt-Erstellung muss nicht durchlaufen — wir wollen nur
    # bestätigen dass der task_id-Pfad bis zum _wait_for_tasks_idle kommt.
    # Wir lassen create_project crashen nach _wait_for_tasks_idle (z.B. via
    # nicht-existenten Pfad).
    from pathlib import Path
    bogus = Path("/nonexistent/pb_studio_test_bug1/" + "x" * 200)
    try:
        pm.create_project(bogus, "Test", task_id="my-task-42")
    except Exception:
        pass  # erwartet — wir wollten nur den _wait-Call beobachten
    assert captured.get("exclude_task_id") == "my-task-42"


# ── BUG-4: Studio-Brain source_start Reset ────────────────────────────────


def test_bug4_studio_brain_source_start_reset_in_inner():
    """Source-Inspektion: nach _sb_chosen_vid muss eine Reset-Prüfung
    auf vid_duration - source_start < seg_duration passieren."""
    from services import pacing_service
    src = inspect.getsource(pacing_service._auto_edit_phase3_inner)
    # Nach _sb_chosen_vid muss ein "_vid_dur" oder ähnlicher Reset-Check
    # sichtbar sein.
    assert "_sb_chosen_vid" in src
    assert "_vid_dur" in src or "vid_duration" in src
    assert "source_start = 0.0" in src or "source_start=0" in src


# ── BUG-5: ChatDock _on_send stoppt Watchdog ──────────────────────────────


def test_bug5_on_send_stops_existing_watchdog():
    """Source-Inspektion: _on_send muss _stop_watchdog() VOR Re-Assign rufen."""
    from ui import chat_dock
    src = inspect.getsource(chat_dock.ChatDock._on_send)
    # _stop_watchdog muss vor "_watchdog_timer = QTimer" auftauchen
    stop_idx = src.find("_stop_watchdog()")
    assign_idx = src.find("_watchdog_timer = QTimer")
    assert stop_idx > 0, "_stop_watchdog() not called in _on_send"
    assert assign_idx > 0
    assert stop_idx < assign_idx, (
        "_stop_watchdog() must be called BEFORE _watchdog_timer assignment "
        "to prevent Worker-1 finished from cancelling Worker-2's watchdog"
    )


# ── BUG-6: Graph-Cockpit refresh debounce ─────────────────────────────────


def test_bug6_graph_cockpit_has_refresh_debounce():
    """Source-Inspektion: GraphCockpitTab hat _refresh_debounce QTimer."""
    from ui.widgets import graph_cockpit_tab
    src = inspect.getsource(graph_cockpit_tab.GraphCockpitTab)
    assert "_refresh_debounce" in src
    assert "_do_refresh_html" in src
    assert "setSingleShot" in src or "single_shot" in src.lower()


# ── BUG-7: BrainService public session_factory ────────────────────────────


def test_bug7_brain_service_has_public_session_factory():
    from services.brain_service import BrainService
    # Die Property muss als attribute sichtbar sein
    assert hasattr(BrainService, "session_factory")
    # Property-Type-Check
    prop = BrainService.session_factory
    assert isinstance(prop, property)


def test_bug7_brain_service_session_factory_returns_factory():
    from services.brain_service import BrainService
    sentinel = lambda: "session-stub"
    bs = BrainService(session_factory=sentinel)
    assert bs.session_factory is sentinel


# ── BUG-8: GraphCockpitTab closeEvent ─────────────────────────────────────


def test_bug8_graph_cockpit_tab_has_close_event():
    from ui.widgets import graph_cockpit_tab
    src = inspect.getsource(graph_cockpit_tab.GraphCockpitTab)
    assert "def closeEvent" in src
    assert "deregisterObject" in src or "_bridge" in src
    assert "deleteLater" in src
