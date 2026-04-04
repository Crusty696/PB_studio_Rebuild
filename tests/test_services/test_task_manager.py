"""
Tests fuer services/task_manager.py

Getestet: TaskInfo, GlobalTaskManager Singleton, create_task(), update_task(),
          finish_task(), cancel_task(), clear_finished(), get_task(), get_all_tasks(),
          register_worker() und Command Pattern.
"""

import time
import pytest
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, QThread


# ---------------------------------------------------------------------------
# QApplication Fixture — noetig fuer alle Qt-basierten Tests
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    """Erstellt eine QApplication fuer die gesamte Test-Session."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def reset_task_manager_singleton(qapp):
    """Setzt den GlobalTaskManager Singleton vor jedem Test zurueck."""
    from services.task_manager import GlobalTaskManager
    GlobalTaskManager._instance = None
    yield
    # Cleanup: Singleton zuruecksetzen
    if GlobalTaskManager._instance is not None:
        inst = GlobalTaskManager._instance
        inst._shutting_down = True
        GlobalTaskManager._instance = None


# ---------------------------------------------------------------------------
# TaskInfo Tests
# ---------------------------------------------------------------------------

class TestTaskInfo:
    """Tests fuer die TaskInfo Datenklasse."""

    def test_creation_defaults(self):
        from services.task_manager import TaskInfo
        task = TaskInfo("task_001", "Test Task", "A description")

        assert task.task_id == "task_001"
        assert task.name == "Test Task"
        assert task.description == "A description"
        assert task.status == "running"
        assert task.progress == 0
        assert task.total == 100
        assert task.message == ""
        assert task.thread is None
        assert task.worker is None

    def test_elapsed_property(self):
        from services.task_manager import TaskInfo
        task = TaskInfo("task_002", "Elapsed Test")
        # elapsed sollte nahe 0 sein direkt nach Erstellung
        assert task.elapsed >= 0.0
        assert task.elapsed < 2.0  # sollte < 2s sein

    def test_creation_without_description(self):
        from services.task_manager import TaskInfo
        task = TaskInfo("task_003", "No Desc")
        assert task.description == ""


# ---------------------------------------------------------------------------
# GlobalTaskManager Singleton Tests
# ---------------------------------------------------------------------------

class TestGlobalTaskManagerSingleton:
    """Tests fuer das Singleton-Pattern des GlobalTaskManager."""

    def test_singleton_instance(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr1 = GlobalTaskManager.instance()
        mgr2 = GlobalTaskManager.instance()
        assert mgr1 is mgr2

    def test_singleton_requires_qapplication(self, qapp):
        """Singleton braucht eine laufende QApplication."""
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        assert mgr is not None


# ---------------------------------------------------------------------------
# create_task() Tests
# ---------------------------------------------------------------------------

class TestCreateTask:
    """Tests fuer die Legacy create_task() Methode."""

    def test_create_task_returns_task_info(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        task = mgr.create_task("Analysis", "Beat detection")

        assert task.name == "Analysis"
        assert task.description == "Beat detection"
        assert task.status == "running"
        assert task.task_id.startswith("task_")

    def test_create_task_increments_counter(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        t1 = mgr.create_task("Task 1")
        t2 = mgr.create_task("Task 2")
        # IDs should be different
        assert t1.task_id != t2.task_id

    def test_create_task_emits_signal(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        emitted = []
        mgr.task_added.connect(lambda tid: emitted.append(tid))

        task = mgr.create_task("Signal Test")
        qapp.processEvents()

        assert len(emitted) == 1
        assert emitted[0] == task.task_id


# ---------------------------------------------------------------------------
# update_task() Tests
# ---------------------------------------------------------------------------

class TestUpdateTask:
    """Tests fuer update_task()."""

    def test_update_task_progress(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        task = mgr.create_task("Update Test")

        mgr.update_task(task.task_id, progress=50, message="Half done")

        updated = mgr.get_task(task.task_id)
        assert updated.progress == 50
        assert updated.message == "Half done"

    def test_update_nonexistent_task(self, qapp):
        """Updating a nonexistent task should not raise."""
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        # Should not raise
        mgr.update_task("nonexistent_123", progress=50)

    def test_update_emits_signal(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        task = mgr.create_task("Signal Update")
        emitted = []
        mgr.task_updated.connect(lambda tid: emitted.append(tid))

        mgr.update_task(task.task_id, progress=75)
        qapp.processEvents()

        assert task.task_id in emitted


# ---------------------------------------------------------------------------
# finish_task() Tests
# ---------------------------------------------------------------------------

class TestFinishTask:
    """Tests fuer finish_task()."""

    def test_finish_task_sets_status(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        task = mgr.create_task("Finish Test")

        mgr.finish_task(task.task_id, status="finished", message="Done")

        finished = mgr.get_task(task.task_id)
        assert finished.status == "finished"
        assert finished.message == "Done"

    def test_finish_task_with_error(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        task = mgr.create_task("Error Test")

        mgr.finish_task(task.task_id, status="error", message="OOM")

        finished = mgr.get_task(task.task_id)
        assert finished.status == "error"

    def test_finish_emits_signal(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        task = mgr.create_task("Signal Finish")
        emitted = []
        mgr.task_finished.connect(lambda tid: emitted.append(tid))

        mgr.finish_task(task.task_id)
        qapp.processEvents()

        assert task.task_id in emitted


# ---------------------------------------------------------------------------
# get_task() / get_all_tasks() Tests
# ---------------------------------------------------------------------------

class TestGetTasks:
    """Tests fuer get_task() und get_all_tasks()."""

    def test_get_task_existing(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        task = mgr.create_task("Get Test")

        result = mgr.get_task(task.task_id)
        assert result is task

    def test_get_task_nonexistent(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        assert mgr.get_task("nonexistent") is None

    def test_get_all_tasks(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        mgr.create_task("Task A")
        mgr.create_task("Task B")

        all_tasks = mgr.get_all_tasks()
        assert len(all_tasks) == 2
        names = {t.name for t in all_tasks}
        assert "Task A" in names
        assert "Task B" in names


# ---------------------------------------------------------------------------
# clear_finished() Tests
# ---------------------------------------------------------------------------

class TestClearFinished:
    """Tests fuer clear_finished()."""

    def test_clear_removes_finished_tasks(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        t1 = mgr.create_task("Running Task")
        t2 = mgr.create_task("Done Task")
        mgr.finish_task(t2.task_id, "finished")

        mgr.clear_finished()

        assert mgr.get_task(t1.task_id) is not None
        assert mgr.get_task(t2.task_id) is None

    def test_clear_keeps_running_tasks(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        t1 = mgr.create_task("Still Running")

        mgr.clear_finished()

        assert mgr.get_task(t1.task_id) is not None
        assert len(mgr.get_all_tasks()) == 1


# ---------------------------------------------------------------------------
# cancel_task() Tests
# ---------------------------------------------------------------------------

class TestCancelTask:
    """Tests fuer cancel_task()."""

    def test_cancel_sets_cancelled_status(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        task = mgr.create_task("Cancel Me")

        mgr.cancel_task(task.task_id)

        cancelled = mgr.get_task(task.task_id)
        assert cancelled.status == "cancelled"

    def test_cancel_nonexistent_task(self, qapp):
        """Cancelling a nonexistent task should not raise."""
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        # Should not raise
        mgr.cancel_task("nonexistent")

    def test_cancel_already_finished_task(self, qapp):
        """Cancelling a finished task should be a no-op."""
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        task = mgr.create_task("Already Done")
        mgr.finish_task(task.task_id, "finished")

        mgr.cancel_task(task.task_id)
        # Status should still be 'finished', not overwritten
        assert mgr.get_task(task.task_id).status == "finished"


# ---------------------------------------------------------------------------
# register_worker() / Command Pattern Tests
# ---------------------------------------------------------------------------

class TestRegisterWorker:
    """Tests fuer das Worker Registry (Command Pattern)."""

    def test_register_worker_adds_to_registry(self, qapp):
        from services.task_manager import GlobalTaskManager

        class DummyWorker(QObject):
            finished = Signal()
            def run(self):
                self.finished.emit()

        GlobalTaskManager.register_worker(
            "test_action",
            DummyWorker,
            "Test Action: {name}",
        )

        assert "test_action" in GlobalTaskManager._WORKER_REGISTRY

        # Cleanup
        del GlobalTaskManager._WORKER_REGISTRY["test_action"]


# ---------------------------------------------------------------------------
# TaskManagerProxy Tests
# ---------------------------------------------------------------------------

class TestTaskManagerProxy:
    """Tests fuer TaskManagerProxy."""

    def test_proxy_delegates_to_singleton(self, qapp):
        from services.task_manager import TaskManagerProxy, GlobalTaskManager
        proxy = TaskManagerProxy()
        # Force singleton creation
        GlobalTaskManager.instance()

        task = proxy.create_task("Proxy Test")
        assert task.name == "Proxy Test"

        # Verify via singleton
        mgr = GlobalTaskManager.instance()
        assert mgr.get_task(task.task_id) is not None


# ---------------------------------------------------------------------------
# Shutdown Guard Tests
# ---------------------------------------------------------------------------

class TestShutdownGuard:
    """Tests fuer B-002 Fix: Kein Thread-Start nach Shutdown."""

    def test_shutting_down_prevents_new_tasks_in_main_thread(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        mgr._shutting_down = True

        class DummyWorker(QObject):
            finished = Signal()
            def run(self):
                self.finished.emit()

        worker = DummyWorker()
        result = mgr._start_in_main_thread(
            "shutdown_test", "Shutdown Test", "", worker, None, None
        )

        # Should return a dummy TaskInfo not added to _tasks
        assert result.name == "Shutdown Test"
        assert mgr.get_task("shutdown_test") is None
