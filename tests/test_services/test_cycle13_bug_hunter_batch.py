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
from pathlib import Path

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


def test_bug1_save_project_as_passes_task_id_to_internal_open(monkeypatch, tmp_path):
    from services.project_manager import ProjectManager
    import database.session as db_session

    source = tmp_path / "source_project"
    source.mkdir()
    (source / "pb_studio.db").write_bytes(b"sqlite-placeholder")
    target = tmp_path / "target_project"

    captured = {}
    pm = ProjectManager()

    monkeypatch.setattr(db_session, "APP_ROOT", source)
    monkeypatch.setattr(
        ProjectManager,
        "_wait_for_tasks_idle",
        staticmethod(lambda timeout_sec=10.0, poll_interval_sec=0.2, exclude_task_id=None: True),
    )
    monkeypatch.setattr(
        ProjectManager,
        "_copy_sqlite_db",
        staticmethod(lambda src_db, dst_db: dst_db.write_bytes(b"copied-db")),
    )

    def _open_project(path, task_id=None):
        captured["path"] = path
        captured["task_id"] = task_id
        return {"name": path.name, "resolution": "1920x1080", "fps": 30.0}

    monkeypatch.setattr(pm, "open_project", _open_project)

    assert pm.save_project_as(target, task_id="save-as-task-42") == target
    assert captured == {"path": target, "task_id": "save-as-task-42"}


def test_bug1_save_project_as_does_not_block_on_own_running_task(tmp_path):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from services.project_manager import ProjectManager
    from services.task_manager import GlobalTaskManager
    import database

    app = QApplication.instance() or QApplication([])
    tm = GlobalTaskManager.instance()
    for existing in tm.get_all_tasks():
        if existing.status == "running":
            tm.finish_task(existing.task_id, "finished", "test cleanup")
    tm.clear_finished()

    pm = ProjectManager()
    source = tmp_path / "source_project"
    target = tmp_path / "target_project"
    own_task = None

    try:
        pm.create_project(source, name="SelfTaskSource")
        own_task = tm.create_task("Projekt kopieren", "self-block regression")

        assert pm.save_project_as(target, task_id=own_task.task_id) == target
        assert (target / "pb_studio.db").exists()
    finally:
        if own_task is not None:
            tm.finish_task(own_task.task_id, "finished", "test cleanup")
        tm.clear_finished()
        database.set_project(Path.cwd())
        try:
            database.init_db()
        except Exception:
            pass


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
    from services.brain import BrainService
    # Die Property muss als attribute sichtbar sein
    assert hasattr(BrainService, "session_factory")
    # Property-Type-Check
    prop = BrainService.session_factory
    assert isinstance(prop, property)


def test_bug7_brain_service_session_factory_returns_factory():
    from services.brain import BrainService
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
