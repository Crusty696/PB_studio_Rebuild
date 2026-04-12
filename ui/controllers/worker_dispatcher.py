"""WorkerDispatcherController — Refactored from WorkerDispatcherMixin.

Kapselt die gesamte Worker/Thread-Lifecycle-Logik:
  - _start_worker_thread()
  - _cancel_worker_for_task()
  - _cleanup_worker()
"""

import logging
from PySide6.QtCore import Qt, QThread, QObject
from services.task_manager import GlobalTaskManager
from ui.base_component import PBComponent

# P-017: Legacy Thread-Registry — nur noch fuer GC-Schutz,
# TaskManager haelt die echten Referenzen.
_GLOBAL_ACTIVE_THREADS: list[tuple] = []

logger = logging.getLogger(__name__)

class WorkerDispatcherController(PBComponent):
    """Controller fuer MainWindow: kapselt Worker/Thread-Spawning und -Cleanup."""

    def _start_worker_thread(self, worker: QObject, on_finish=None, on_error=None):
        """Leitet an GlobalTaskManager.start_task() weiter."""
        worker_name = type(worker).__name__.replace("Worker", "")
        tm = GlobalTaskManager.instance()
        existing_task_id = getattr(worker, 'task_id', None)

        if existing_task_id:
            task = tm.get_task(existing_task_id)
        else:
            task = None

        if task:
            thread = QThread()
            worker.moveToThread(thread)
            thread.started.connect(worker.run)

            if on_finish:
                def _guarded_finish(*args, _w=worker, _cb=on_finish):
                    if not getattr(_w, '_errored', False):
                        _cb(*args)
                worker.finished.connect(_guarded_finish)

            if on_error:
                worker.error.connect(on_error)
            else:
                def _default_error_handler(*args, _tid=existing_task_id, _name=worker_name, _tm=tm):
                    err_msg = str(args[-1]) if args else "Unbekannter Fehler"
                    logging.error(
                        "[TaskEngine] Worker-Fehler '%s' (task_id=%s): %s",
                        _name, _tid, err_msg,
                    )
                    _tm.finish_task(_tid, status="error", message=err_msg)
                worker.error.connect(_default_error_handler)

            if hasattr(worker, "progress"):
                worker.progress.connect(
                    lambda pct, msg, _tid=existing_task_id: tm.update_task(_tid, pct, message=msg)
                )

            worker.finished.connect(thread.quit)
            thread.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(
                lambda _tid=existing_task_id: tm._on_thread_done(_tid)
            )

            task.thread = thread
            task.worker = worker
            self.window._active_threads.append(thread)
            self.window._active_workers.append(worker)
            thread.finished.connect(
                lambda _t=thread, _w=worker: self._cleanup_worker(_t, _w)
            )
            thread.start()
            return thread
        else:
            task = tm.start_task(
                name=worker_name,
                worker=worker,
                on_finish=on_finish,
                on_error=on_error,
            )
            if isinstance(task, str):
                self.window._active_workers.append(worker)
                return None
            if task.thread:
                self.window._active_threads.append(task.thread)
                task.thread.finished.connect(
                    lambda _t=task.thread, _w=worker: self._cleanup_worker(_t, _w)
                )
            self.window._active_workers.append(worker)
            return task.thread

    def _cancel_worker_for_task(self, task_id: str):
        """Cancel via TaskEngine."""
        GlobalTaskManager.instance().cancel_task(task_id)
        if hasattr(self.window, 'console_text'):
            self.window.console_text.append(f"[System] Task abgebrochen: {task_id}")

    def _cleanup_worker(self, thread: QThread, worker: QObject):
        """Entfernt Worker/Thread aus lokalen Listen."""
        if worker in self.window._active_workers:
            self.window._active_workers.remove(worker)
        if thread in self.window._active_threads:
            self.window._active_threads.remove(thread)
        pair = (thread, worker)
        if pair in _GLOBAL_ACTIVE_THREADS:
            _GLOBAL_ACTIVE_THREADS.remove(pair)
