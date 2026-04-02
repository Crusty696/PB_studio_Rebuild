"""WorkerDispatcherMixin — extrahiert aus main.py (Sprint 4 / AUD-14).

Kapselt die gesamte Worker/Thread-Lifecycle-Logik:
  - _start_worker_thread()
  - _cancel_worker_for_task()
  - _cleanup_worker()

Alle Mixins und PBWindow rufen self._start_worker_thread() auf —
durch dieses Mixin bleibt die Signatur unveraendert.
"""

import logging

from PySide6.QtCore import Qt, QThread, QObject

from services.task_manager import GlobalTaskManager

# P-017: Legacy Thread-Registry — nur noch fuer GC-Schutz,
# TaskManager haelt die echten Referenzen.
_GLOBAL_ACTIVE_THREADS: list[tuple] = []

logger = logging.getLogger(__name__)


class WorkerDispatcherMixin:
    """Mixin fuer MainWindow: kapselt Worker/Thread-Spawning und -Cleanup."""

    def _start_worker_thread(self, worker: QObject, on_finish=None, on_error=None):
        """Legacy-Bridge: Leitet an GlobalTaskManager.start_task() weiter.

        Alle Threads werden jetzt vom TaskManager gehalten (GC-Schutz).
        Existierende Aufrufe bleiben kompatibel.

        Bug-3 Fix: Nutzt GlobalTaskManager.instance() statt globalem task_manager,
        damit Buttons auch ohne Chat-Dock-Initialisierung funktionieren.
        """
        worker_name = type(worker).__name__.replace("Worker", "")

        # Singleton direkt – unabhaengig vom globalen task_manager
        tm = GlobalTaskManager.instance()

        # Falls der Worker schon eine task_id hat (von manueller create_task()),
        # registrieren wir Thread+Worker im bestehenden Task.
        existing_task_id = getattr(worker, 'task_id', None)

        if existing_task_id and existing_task_id in tm._tasks:
            # Thread im bestehenden Task registrieren
            task = tm._tasks[existing_task_id]
            thread = QThread()
            worker.moveToThread(thread)
            thread.started.connect(worker.run)

            if on_finish:
                def _guarded_finish(*args, _w=worker, _cb=on_finish):
                    if not getattr(_w, '_errored', False):
                        _cb(*args)
                # WICHTIG: QueuedConnection erzwingen — PySide6 nutzt DirectConnection
                # fuer Python-Lambdas, was den Callback im Worker-Thread ausfuehrt.
                # QTimer.singleShot funktioniert nur im Main-Thread.
                worker.finished.connect(_guarded_finish, Qt.ConnectionType.QueuedConnection)
            # Error-Signal: Entweder custom on_error ODER den Default-Handler verbinden
            # (nie beide, da sonst finish_task() doppelt aufgerufen wird).
            if on_error:
                worker.error.connect(on_error, Qt.ConnectionType.QueuedConnection)
            else:
                def _default_error_handler(*args, _tid=existing_task_id, _name=worker_name,
                                           _tm=tm):
                    err_msg = str(args[-1]) if args else "Unbekannter Fehler"
                    logging.error(
                        "[TaskEngine] Worker-Fehler '%s' (task_id=%s): %s",
                        _name, _tid, err_msg,
                    )
                    _tm.finish_task(_tid, status="error", message=err_msg)
                worker.error.connect(_default_error_handler, Qt.ConnectionType.QueuedConnection)

            # B-012 Fix: Fuer existing_task_id-Pfad wird _start_in_main_thread NICHT aufgerufen,
            # daher verbinden wir progress hier genau einmal (nicht doppelt wie der alte Bug).
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
            self._active_threads.append(thread)
            self._active_workers.append(worker)
            thread.finished.connect(
                lambda _t=thread, _w=worker: self._cleanup_worker(_t, _w)
            )
            thread.start()
            return thread
        else:
            # Neuer Task ueber die Engine
            task = tm.start_task(
                name=worker_name,
                worker=worker,
                on_finish=on_finish,
                on_error=on_error,
            )
            # Defensive: start_task() gibt str zurueck bei Cross-Thread-Routing
            if isinstance(task, str):
                self._active_workers.append(worker)
                return None
            if task.thread:
                self._active_threads.append(task.thread)
                task.thread.finished.connect(
                    lambda _t=task.thread, _w=worker: self._cleanup_worker(_t, _w)
                )
            self._active_workers.append(worker)
            return task.thread

    def _cancel_worker_for_task(self, task_id: str):
        """Cancel via TaskEngine (Singleton, nie None)."""
        GlobalTaskManager.instance().cancel_task(task_id)
        if hasattr(self, 'console_text'):
            self.console_text.append(f"[System] Task abgebrochen: {task_id}")

    def _cleanup_worker(self, thread: QThread, worker: QObject):
        """Entfernt Worker/Thread aus lokalen Listen.
        GC-Schutz liegt jetzt beim GlobalTaskManager (TaskInfo haelt Referenzen).
        """
        if worker in self._active_workers:
            self._active_workers.remove(worker)
        if thread in self._active_threads:
            self._active_threads.remove(thread)
        # Legacy-Liste auch aufraeumen (falls noch Eintraege)
        pair = (thread, worker)
        if pair in _GLOBAL_ACTIVE_THREADS:
            _GLOBAL_ACTIVE_THREADS.remove(pair)
