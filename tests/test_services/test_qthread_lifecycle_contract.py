from __future__ import annotations

import time

import pytest
import shiboken6
from PySide6.QtCore import QObject, Signal


class _FinishWorker(QObject):
    finished = Signal()

    def run(self) -> None:
        self.finished.emit()


class _ErrorOnlyWorker(QObject):
    finished = Signal()
    error = Signal(str)

    def run(self) -> None:
        self._errored = True
        self.error.emit("boom")


class _CancellableWorker(QObject):
    finished = Signal()
    error = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.started = False
        self.cancel_called = False
        self._cancelled = False

    def cancel(self) -> None:
        self.cancel_called = True
        self._cancelled = True

    def run(self) -> None:
        self.started = True
        deadline = time.monotonic() + 2.0
        while not self._cancelled and time.monotonic() < deadline:
            time.sleep(0.01)
        self.finished.emit()


@pytest.fixture
def task_manager(qapp):
    from services.task_manager import GlobalTaskManager

    GlobalTaskManager._instance = None
    manager = GlobalTaskManager.instance()
    yield manager
    for task in manager.get_all_tasks():
        if task.status == "running":
            manager.cancel_task(task.task_id)
        thread = task.thread
        if thread is not None:
            try:
                if shiboken6.isValid(thread) and thread.isRunning():
                    thread.quit()
                    thread.wait(1000)
            except RuntimeError:
                pass
    manager.clear_finished()
    manager._shutting_down = True
    GlobalTaskManager._instance = None


def _wait_until(qapp, predicate, timeout_ms: int = 1500) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    qapp.processEvents()
    return predicate()


def test_worker_finished_quits_thread_and_cleans_refs(qapp, task_manager):
    worker = _FinishWorker()
    task = task_manager.start_task("finish contract", worker)
    thread = task.thread

    assert thread is not None
    assert _wait_until(qapp, lambda: task.status == "finished")
    assert _wait_until(qapp, lambda: task.thread is None and task.worker is None)
    assert not shiboken6.isValid(thread) or not thread.isRunning()


def test_worker_error_without_finished_quits_thread_and_cleans_refs(qapp, task_manager):
    worker = _ErrorOnlyWorker()
    task = task_manager.start_task("error contract", worker)
    thread = task.thread

    assert thread is not None
    assert _wait_until(qapp, lambda: task.status == "error")
    assert _wait_until(qapp, lambda: task.thread is None and task.worker is None)
    assert not shiboken6.isValid(thread) or not thread.isRunning()


def test_cancel_task_calls_worker_cancel_and_thread_exits(qapp, task_manager):
    worker = _CancellableWorker()
    task = task_manager.start_task("cancel contract", worker)
    thread = task.thread

    assert thread is not None
    assert _wait_until(qapp, lambda: worker.started)

    task_manager.cancel_task(task.task_id)

    assert worker.cancel_called is True
    assert task.status == "cancelled"
    assert _wait_until(qapp, lambda: task.thread is None and task.worker is None)
    assert not shiboken6.isValid(thread) or not thread.isRunning()
