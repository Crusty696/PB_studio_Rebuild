from __future__ import annotations

from pathlib import Path

import pytest


def test_open_project_refuses_to_swap_engine_while_tasks_running(monkeypatch, tmp_path: Path):
    from services.project_manager import ProjectManager

    project_path = tmp_path / "busy_project"
    project_path.mkdir()

    manager = ProjectManager()
    set_project_called = False

    def _busy(*args, **kwargs) -> bool:
        return False

    def _forbidden_set_project(_path: Path) -> None:
        nonlocal set_project_called
        set_project_called = True
        raise AssertionError("set_project must not run while tasks are active")

    monkeypatch.setattr(ProjectManager, "_wait_for_tasks_idle", staticmethod(_busy))
    monkeypatch.setattr("database.set_project", _forbidden_set_project)

    with pytest.raises(RuntimeError, match="Hintergrund-Tasks"):
        manager.open_project(project_path)

    assert set_project_called is False
    assert manager.current_project_path is None
