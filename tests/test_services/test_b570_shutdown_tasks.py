"""B-570: Shutdown darf laufende QThreads mit Status ``cancelled`` nicht verlieren."""

from unittest.mock import MagicMock


def test_shutdown_tasks_include_cancelled_task_with_live_thread(qapp, monkeypatch):
    from services.task_manager import GlobalTaskManager
    import services.task_manager as task_manager_module

    GlobalTaskManager._instance = None
    manager = GlobalTaskManager.instance()
    monkeypatch.setattr(task_manager_module.shiboken6, "isValid", lambda obj: True)

    task = manager.create_task("Kooperativ abgebrochen")
    task.status = "cancelled"
    task.thread = MagicMock()
    task.thread.isRunning.return_value = True

    try:
        assert manager.get_shutdown_tasks() == [task]
    finally:
        manager._shutting_down = True
        GlobalTaskManager._instance = None


def test_shutdown_tasks_exclude_finished_task_with_stopped_thread(qapp, monkeypatch):
    from services.task_manager import GlobalTaskManager
    import services.task_manager as task_manager_module

    GlobalTaskManager._instance = None
    manager = GlobalTaskManager.instance()
    monkeypatch.setattr(task_manager_module.shiboken6, "isValid", lambda obj: True)

    task = manager.create_task("Beendet")
    task.status = "finished"
    task.thread = MagicMock()
    task.thread.isRunning.return_value = False

    try:
        assert manager.get_shutdown_tasks() == []
    finally:
        manager._shutting_down = True
        GlobalTaskManager._instance = None
