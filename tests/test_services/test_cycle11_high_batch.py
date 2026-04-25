"""Cycle 11 / P5 HIGH-Batch: B-047 + B-048."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── B-047: _has_running_tasks zählt eigenen Worker mit ─────────────────────


def test_b047_has_running_tasks_excludes_own_task_id(monkeypatch):
    """Wenn der aufrufende Worker seine task_id durchreicht, soll er
    sich nicht selbst zählen."""
    from services.project_manager import ProjectManager

    # Mock GlobalTaskManager.get_all_tasks gibt zwei Tasks zurück:
    # - "self_task_id" (= der Worker der gerade _has_running_tasks aufruft)
    # - "other_task_id" (= ein anderer)
    fake_tasks = [
        type("T", (), {"task_id": "self_task_id", "status": "running"})(),
        type("T", (), {"task_id": "other_task_id", "status": "completed"})(),
    ]

    class _FakeTM:
        @staticmethod
        def instance():
            tm = MagicMock()
            tm.get_all_tasks.return_value = fake_tasks
            return tm

    with patch("services.task_manager.GlobalTaskManager", _FakeTM):
        # Ohne exclude → True (der eigene Task ist running)
        assert ProjectManager._has_running_tasks() is True
        # Mit exclude → False (eigenen Task ignoriert, keine anderen running)
        assert ProjectManager._has_running_tasks(exclude_task_id="self_task_id") is False


def test_b047_wait_for_tasks_idle_excludes_own_task_id(monkeypatch):
    """_wait_for_tasks_idle soll auch exclude_task_id durchreichen."""
    from services.project_manager import ProjectManager

    fake_tasks = [
        type("T", (), {"task_id": "self_id", "status": "running"})(),
    ]

    class _FakeTM:
        @staticmethod
        def instance():
            tm = MagicMock()
            tm.get_all_tasks.return_value = fake_tasks
            return tm

    with patch("services.task_manager.GlobalTaskManager", _FakeTM):
        # Ohne exclude: Timeout (Task running) → False
        assert ProjectManager._wait_for_tasks_idle(
            timeout_sec=0.5, poll_interval_sec=0.1,
        ) is False
        # Mit exclude: idle sofort → True
        assert ProjectManager._wait_for_tasks_idle(
            timeout_sec=0.5, poll_interval_sec=0.1,
            exclude_task_id="self_id",
        ) is True


# ── B-048: open_project Schema-Validierung ─────────────────────────────────


def test_b048_open_project_rejects_empty_db_file(tmp_path):
    """Eine leere `pb_studio.db`-Datei darf NICHT gesetzt werden — sonst
    überschreibt init_db() die fremde Datei."""
    from services.project_manager import ProjectManager

    project_dir = tmp_path / "fake_project"
    project_dir.mkdir()
    # Leere Datei
    (project_dir / "pb_studio.db").touch()

    pm = ProjectManager()
    with pytest.raises((FileNotFoundError, ValueError, RuntimeError)) as excinfo:
        pm.open_project(project_dir)
    msg = str(excinfo.value).lower()
    assert "kein gueltiges" in msg or "kein gültiges" in msg or "no valid" in msg or "schema" in msg


def test_b048_open_project_rejects_foreign_sqlite(tmp_path):
    """Eine fremde SQLite-DB ohne `projects`-Tabelle muss abgelehnt werden."""
    from services.project_manager import ProjectManager

    project_dir = tmp_path / "foreign_project"
    project_dir.mkdir()
    db_path = project_dir / "pb_studio.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE other_table (id INTEGER)")
    con.commit()
    con.close()

    pm = ProjectManager()
    with pytest.raises((FileNotFoundError, ValueError, RuntimeError)):
        pm.open_project(project_dir)


def test_b048_open_project_accepts_valid_pb_studio_db(tmp_path, monkeypatch):
    """Eine valide PB-Studio-DB mit `projects`-Tabelle wird durchgewunken."""
    from services.project_manager import ProjectManager

    project_dir = tmp_path / "valid_project"
    project_dir.mkdir()
    db_path = project_dir / "pb_studio.db"
    con = sqlite3.connect(db_path)
    con.execute(
        "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT, "
        "resolution TEXT, fps REAL)"
    )
    con.execute(
        "INSERT INTO projects (name, resolution, fps) VALUES "
        "('TestProj', '1920x1080', 30.0)"
    )
    con.commit()
    con.close()

    # Mock set_project + init_db damit der Test nicht die echte DB swappt
    import database
    monkeypatch.setattr(database, "set_project", lambda p: None)
    monkeypatch.setattr(database, "init_db", lambda: None)
    monkeypatch.setattr(ProjectManager, "_wait_for_tasks_idle", lambda *a, **k: True)

    pm = ProjectManager()
    meta = pm.open_project(project_dir)
    assert meta["name"] == "TestProj"
