import os
from types import SimpleNamespace

from PySide6.QtCore import QObject, QEventLoop, QTimer, Signal
from PySide6.QtWidgets import QApplication
import shiboken6


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class ErrorOnlyWorker(QObject):
    finished = Signal()
    error = Signal(str)

    def run(self):
        self._errored = True
        self.error.emit("boom")


def test_b353_existing_task_error_without_finished_stops_thread():
    from services.task_manager import GlobalTaskManager
    from ui.controllers.worker_dispatcher import WorkerDispatcherController

    app = QApplication.instance() or QApplication([])
    tm = GlobalTaskManager.instance()
    for existing in tm.get_all_tasks():
        if existing.status == "running":
            tm.finish_task(existing.task_id, "finished", "test cleanup")
    tm.clear_finished()

    window = SimpleNamespace(
        _active_threads=[],
        _active_workers=[],
        logger=None,
    )
    controller = WorkerDispatcherController(window)
    task = tm.create_task("B-353", "error cleanup regression")
    worker = ErrorOnlyWorker()
    worker.task_id = task.task_id

    thread = controller._start_worker_thread(worker)

    loop = QEventLoop()
    thread.finished.connect(loop.quit)
    QTimer.singleShot(1000, loop.quit)
    loop.exec()
    app.processEvents()

    try:
        assert not shiboken6.isValid(thread) or not thread.isRunning()
        assert worker not in window._active_workers
        assert thread not in window._active_threads
        assert tm.get_task(task.task_id).status == "error"
    finally:
        if shiboken6.isValid(thread) and thread.isRunning():
            thread.quit()
            thread.wait(1000)
        tm.finish_task(task.task_id, "finished", "test cleanup")
        tm.clear_finished()
