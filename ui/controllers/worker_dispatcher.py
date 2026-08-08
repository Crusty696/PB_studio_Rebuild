"""WorkerDispatcherController — Refactored from WorkerDispatcherMixin.

Kapselt die gesamte Worker/Thread-Lifecycle-Logik:
  - _start_worker_thread()
  - _cancel_worker_for_task()
  - _cleanup_worker()
"""

import logging
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QObject
from services.task_manager import GlobalTaskManager
from ui.base_component import PBComponent

# P-017: Legacy Thread-Registry — nur noch fuer GC-Schutz,
# TaskManager haelt die echten Referenzen.
_GLOBAL_ACTIVE_THREADS: list[tuple] = []

logger = logging.getLogger(__name__)

_WORKER_RESOURCE_LOCK = threading.Lock()
_WORKER_RESOURCE_OWNERS: dict[tuple[str, str, int], int] = {}


def _worker_resource_keys(worker: QObject) -> tuple[tuple[str, str, int], ...]:
    """B-750: gemeinsame Schreibressourcen eines Audio-Workers.

    Projektpfad ist Teil des Keys: gleiche Track-ID in zwei Projekten darf
    parallel laufen. Jeder V2-Worker kollidiert mit anderem V2 desselben
    Tracks. Full-/Onset-V2 beanspruchen zusätzlich Stem-Artefakte; reines
    AV-Pacing nicht.
    """
    from database import session as db_session
    from workers import StemSeparationWorker
    from workers.audio_pipeline_v2_worker import AudioPipelineV2Worker

    root = getattr(db_session, "APP_ROOT", None)
    project_key = (
        str(Path(root).resolve()).casefold() if root is not None else "<no-project>"
    )
    if isinstance(worker, AudioPipelineV2Worker):
        track_id = int(worker.audio_track_id)
        keys = [("audio-v2", project_key, track_id)]
        retry_keys = set(getattr(worker, "retry_step_keys", ()))
        if not retry_keys or "onset_detection" in retry_keys:
            keys.append(("audio-stems", project_key, track_id))
        return tuple(keys)
    if isinstance(worker, StemSeparationWorker):
        return (("audio-stems", project_key, int(worker.track_id)),)
    return ()


def _try_claim_worker_resources(worker: QObject) -> bool:
    """Atomarer Single-Flight-Claim vor Workerstart."""
    existing = getattr(worker, "_pb_resource_claims", None)
    if existing:
        return True
    keys = _worker_resource_keys(worker)
    if not keys:
        return True
    owner = id(worker)
    with _WORKER_RESOURCE_LOCK:
        if any(
            key in _WORKER_RESOURCE_OWNERS
            and _WORKER_RESOURCE_OWNERS[key] != owner
            for key in keys
        ):
            return False
        for key in keys:
            _WORKER_RESOURCE_OWNERS[key] = owner
    worker._pb_resource_claims = keys
    # Generischer Hook: TaskManager kennt keine Audio-Keylogik, kann aber bei
    # seinem echten QThread-Cleanup denselben idempotenten Release ausführen.
    worker._pb_resource_release = _release_worker_resources
    return True


def _release_worker_resources(worker: QObject) -> None:
    """Idempotentes Release; Dispatcher ruft dies erst beim Thread-Cleanup."""
    keys = tuple(getattr(worker, "_pb_resource_claims", ()) or ())
    if not keys:
        return
    owner = id(worker)
    with _WORKER_RESOURCE_LOCK:
        for key in keys:
            if _WORKER_RESOURCE_OWNERS.get(key) == owner:
                _WORKER_RESOURCE_OWNERS.pop(key, None)
    worker._pb_resource_claims = ()

class WorkerDispatcherController(PBComponent):
    """Controller fuer MainWindow: kapselt Worker/Thread-Spawning und -Cleanup."""

    def _cleanup_taskmanager_worker(self, worker: QObject) -> None:
        """Entfernt TaskManager-eigenen BG-Worker aus lokaler UI-GC-Liste."""
        worker._pb_terminal_cleanup_done = True
        if worker in self.window._active_workers:
            self.window._active_workers.remove(worker)

    def _start_worker_thread(self, worker: QObject, on_finish=None, on_error=None):
        """Leitet an GlobalTaskManager.start_task() weiter."""
        worker_name = type(worker).__name__.replace("Worker", "")
        tm = GlobalTaskManager.instance()
        existing_task_id = getattr(worker, 'task_id', None)

        if existing_task_id:
            task = tm.get_task(existing_task_id)
        else:
            task = None

        if not _try_claim_worker_resources(worker):
            track_id = getattr(
                worker,
                "audio_track_id",
                getattr(worker, "track_id", "?"),
            )
            message = (
                f"Bereits aktiv: Audioanalyse für Track #{track_id} "
                "im aktuellen Projekt."
            )
            worker._start_conflict = message
            logger.warning("Workerstart blockiert: %s", message)
            if task and existing_task_id:
                tm.finish_task(existing_task_id, "cancelled", message)
            if on_error:
                on_error(track_id, message)
            try:
                worker.error.emit(track_id, message)
            except (AttributeError, TypeError):
                logger.exception("Konfliktsignal für %s fehlgeschlagen", worker_name)
            return None

        if task:
            thread = None
            try:
                thread = QThread()
                worker.moveToThread(thread)
                thread.started.connect(worker.run)

                # B-222 (F2): ALLE worker.<signal>-Connections von einem Lambda
                # oder einer freien Funktion gehen MIT explizitem
                # Qt.QueuedConnection.
                qc = Qt.ConnectionType.QueuedConnection

                if on_finish:
                    def _guarded_finish(*args, _w=worker, _cb=on_finish):
                        if not getattr(_w, '_errored', False):
                            _cb(*args)
                    worker.finished.connect(_guarded_finish, qc)

                if on_error:
                    worker.error.connect(on_error, qc)
                else:
                    def _default_error_handler(*args, _tid=existing_task_id, _name=worker_name, _tm=tm):
                        _tm._handle_worker_error(_tid, _name, args)
                    worker.error.connect(_default_error_handler, qc)

                if hasattr(worker, "progress"):
                    worker.progress.connect(
                        lambda pct, msg, _tid=existing_task_id: tm.update_task(_tid, pct, message=msg),
                        qc,
                    )

                worker.finished.connect(thread.quit)
                worker.error.connect(thread.quit)
                thread.finished.connect(worker.deleteLater)
                thread.finished.connect(thread.deleteLater)
                thread.finished.connect(
                    lambda _tid=existing_task_id: tm._on_thread_done(_tid),
                    qc,
                )

                task.thread = thread
                task.worker = worker
                self.window._active_threads.append(thread)
                self.window._active_workers.append(worker)
                thread.finished.connect(
                    lambda _t=thread, _w=worker: self._cleanup_worker(_t, _w),
                    qc,
                )
                thread.start()
            except Exception as exc:
                try:
                    thread_running = thread is not None and thread.isRunning()
                except RuntimeError:
                    thread_running = False
                if thread_running:
                    raise
                if thread is not None and thread in self.window._active_threads:
                    self.window._active_threads.remove(thread)
                if worker in self.window._active_workers:
                    self.window._active_workers.remove(worker)
                if task.thread is thread:
                    task.thread = None
                if task.worker is worker:
                    task.worker = None
                _release_worker_resources(worker)
                try:
                    tm.finish_task(existing_task_id, "error", str(exc))
                except Exception:
                    logger.exception(
                        "Taskstatus nach Worker-Setupfehler konnte nicht gesetzt werden"
                    )
                raise
            return thread
        else:
            worker._pb_terminal_cleanup_done = False
            worker._pb_terminal_cleanup = self._cleanup_taskmanager_worker
            try:
                task = tm.start_task(
                    name=worker_name,
                    worker=worker,
                    on_finish=on_finish,
                    on_error=on_error,
                )
            except Exception:
                _release_worker_resources(worker)
                raise
            if isinstance(task, str):
                if worker not in self.window._active_workers:
                    self.window._active_workers.append(worker)
                if getattr(worker, "_pb_terminal_cleanup_done", False):
                    self._cleanup_taskmanager_worker(worker)
                    return None
                return None
            thread_ref = task.thread
            if thread_ref is None:
                _release_worker_resources(worker)
                return None
            if worker not in self.window._active_workers:
                self.window._active_workers.append(worker)
            if getattr(worker, "_pb_terminal_cleanup_done", False):
                self._cleanup_worker(thread_ref, worker)
                return None
            try:
                self.window._active_threads.append(thread_ref)
                task.thread.finished.connect(
                    lambda _t=thread_ref, _w=worker: self._cleanup_worker(_t, _w),
                    Qt.ConnectionType.QueuedConnection,
                )
                # B-173: tm.start_task hat den Thread bereits gestartet —
                # wenn er sehr schnell fertig wurde, kann finished schon
                # emitted sein bevor wir connecten. Race-Guard: manueller
                # Cleanup wenn Thread nicht mehr laeuft. _cleanup_worker
                # ist idempotent (worker-in-list Check).
                if (
                    getattr(worker, "_pb_terminal_cleanup_done", False)
                    or not thread_ref.isRunning()
                ):
                    self._cleanup_worker(thread_ref, worker)
                    return None
            except (RuntimeError, AttributeError):
                # TaskManager-Cleanup kann Qt-Wrapper direkt vor Connect/Status
                # löschen. Lokale Listen trotzdem idempotent bereinigen.
                self._cleanup_worker(thread_ref, worker)
                return None
            return thread_ref

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
        _release_worker_resources(worker)
