"""Zentrale Task-Engine: Erstellt, verwaltet und besitzt alle Hintergrund-Threads."""

import gc
import logging
import threading
import time
import uuid

logger = logging.getLogger(__name__)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QThread, Signal, QObject


class TaskInfo:
    """Beschreibt einen laufenden Hintergrund-Task."""
    def __init__(self, task_id: str, name: str, description: str = ""):
        self.task_id = task_id
        self.name = name
        self.description = description
        self.status = "running"
        self.progress = 0
        self.total = 100
        self.message = ""
        self.start_time = time.time()
        # Referenzen auf Thread und Worker — GC-Schutz!
        self.thread: QThread | None = None
        self.worker: QObject | None = None

    @property
    def elapsed(self) -> float:
        return round(time.time() - self.start_time, 1)


class TaskManagerProxy:
    """Proxy fuer GlobalTaskManager — erlaubt Modul-Level Zugriff ohne Import-Zyklen.

    Verwendung in Mixins/Services:
        from services.task_manager import TaskManagerProxy
        task_manager = TaskManagerProxy()
        task_manager.create_task(...)
    """

    def __getattr__(self, name):
        return getattr(GlobalTaskManager.instance(), name)


class GlobalTaskManager(QObject):
    """Zentrale Task-Engine: Erstellt, verwaltet und besitzt ALLE
    Hintergrund-Threads und Worker. Singleton.

    Jeder Hintergrund-Job MUSS über start_task() laufen.
    Das TaskManagerDock hört ausschliesslich auf diese Signale.

    CROSS-THREAD SAFE: start_task() kann aus jedem Thread aufgerufen
    werden. Worker-Ownership wird korrekt an den Main-Thread uebergeben,
    bevor QThread-Erstellung und Signal-Verbindungen stattfinden.

    COMMAND PATTERN: Agenten-Tools senden nur noch
    agent_command_signal.emit(action_name, kwargs). Der Main-Thread
    instanziiert Worker und QThread selbst — keine Qt-Objekte im
    Agent-Thread!
    """
    task_added = Signal(str)
    task_updated = Signal(str)
    task_finished = Signal(str)
    show_dock_requested = Signal()  # UI verbindet sich hierauf statt Widget-Traversal
    request_gc_signal = Signal()    # Erlaubt Workern sicheren GC im Main-Thread anzufordern (Fix F-011)

    # Cross-Thread Request: task_id, name, description, worker, on_finish, on_error
    _cross_thread_request = Signal(str, str, str, object, object, object)

    # ── Command Pattern: Agenten emittieren nur noch dieses Signal ──
    agent_command_signal = Signal(str, dict)  # action_name, kwargs

    _instance: "GlobalTaskManager | None" = None
    _instance_lock: threading.Lock = threading.Lock()

    @classmethod
    def instance(cls) -> "GlobalTaskManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:  # Double-checked locking
                    # FIX B-010: Stelle sicher dass QApplication existiert
                    app = QApplication.instance()
                    if app is None:
                        raise RuntimeError(
                            "GlobalTaskManager kann nur nach QApplication.instance() erstellt werden. "
                            "Stelle sicher dass QApplication() VOR dem TaskManager-Import erstellt wird."
                        )
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        # FIX B-010: QApplication ist jetzt garantiert verfügbar von instance()
        super().__init__(QApplication.instance())
        self._tasks: dict[str, TaskInfo] = {}
        self._tasks_lock = threading.Lock()  # FIX B-011: Schützt concurrent dict-Zugriffe
        self._shutting_down = False  # FIX B-002: Verhindert Thread-Erstellung nach closeEvent
        # Cross-Thread-Signal: QueuedConnection erzwingt Ausfuehrung im Main-Thread
        self._cross_thread_request.connect(
            self._start_in_main_thread, Qt.ConnectionType.QueuedConnection
        )
        # Command Pattern: QueuedConnection → Main-Thread instanziiert Worker
        self.agent_command_signal.connect(
            self._build_and_execute_task, Qt.ConnectionType.QueuedConnection
        )
        # GC-Request: Sicherer Speicher-Cleanup im Main-Thread (Fix F-011)
        self.request_gc_signal.connect(
            self._do_safe_gc, Qt.ConnectionType.QueuedConnection
        )

    def _do_safe_gc(self):
        """Führt GC sicher im Main-Thread aus (Fix F-011)."""
        try:
            import gc
            gc.collect()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Command Pattern: Worker-Registry + Main-Thread Factory
    # ------------------------------------------------------------------

    # Registry: action_name → (WorkerClass, task_display_name_template, kwargs→worker_kwargs mapper)
    _WORKER_REGISTRY: dict[str, tuple] = {}

    @classmethod
    def register_worker(cls, action_name: str, worker_class, display_name: str,
                        mapper=None):
        """Registriert eine Worker-Klasse fuer das Command Pattern.

        Args:
            action_name: Eindeutiger Name (z.B. 'separate_stems').
            worker_class: QObject mit run() und finished-Signal.
            display_name: Template fuer Task-Anzeige, darf {kwargs} nutzen.
            mapper: Optional. Funktion(kwargs) → dict mit Worker-Konstruktor-Kwargs.
                    Default: kwargs werden 1:1 weitergereicht.
        """
        cls._WORKER_REGISTRY[action_name] = (worker_class, display_name, mapper)

    def _build_and_execute_task(self, action_name: str, kwargs: dict):
        """Laeuft IMMER im Main-Thread (via QueuedConnection).

        Holt die Worker-Klasse aus der Registry, instanziiert Worker + QThread,
        fuehrt moveToThread aus, verbindet Signale und startet den Thread.
        """
        entry = self._WORKER_REGISTRY.get(action_name)
        if entry is None:
            logging.error(
                "[CommandPattern] Unbekannte Action '%s' — kein Worker registriert. "
                "kwargs=%s", action_name, kwargs
            )
            return

        worker_class, display_template, mapper = entry

        # Worker-kwargs vorbereiten
        worker_kwargs = mapper(kwargs) if mapper else kwargs

        # Display-Name
        try:
            display_name = display_template.format(**kwargs)
        except (KeyError, IndexError):
            display_name = f"{action_name} ({kwargs})"

        logging.info(
            "[CommandPattern] Main-Thread baut Worker: %s → %s",
            action_name, display_name,
        )

        # 1. Worker im Main-Thread instanziieren
        worker = worker_class(**worker_kwargs)

        # 2. start_task kuemmert sich um QThread, moveToThread, Signale, Start
        self.start_task(
            name=display_name,
            worker=worker,
            description=f"Command Pattern: {action_name}",
        )

        # 3. TaskManagerDock erzwingen (via Signal statt Widget-Traversal)
        self.show_dock_requested.emit()

    # ------------------------------------------------------------------
    # Neues API: Worker + Thread in einem Aufruf starten
    # THREAD-SAFE: Kann aus Main-Thread UND Background-Threads aufgerufen werden
    # ------------------------------------------------------------------

    def start_task(
        self,
        name: str,
        worker: QObject,
        description: str = "",
        on_finish=None,
        on_error=None,
    ) -> "TaskInfo | str":
        """Erstellt Task, Thread, moveToThread, startet alles.

        Der Worker MUSS eine run()-Methode und ein finished-Signal haben.
        Optional: progress(int, str), error-Signal.

        Returns:
            - TaskInfo wenn aus Main-Thread aufgerufen (sofortige Ausfuehrung)
            - task_id (str) wenn aus Background-Thread (asynchrone Ausfuehrung)
        """
        task_id = f"task_{uuid.uuid4().hex[:12]}"

        app = QApplication.instance()
        is_bg_thread = app is not None and QThread.currentThread() != app.thread()

        if is_bg_thread:
            # ============================================================
            # CRITICAL FIX: Cross-Thread Task Routing
            # Worker wurde im BG-Thread erstellt → Ownership an Main-Thread
            # uebergeben BEVOR wir das Signal senden.
            # ============================================================
            logging.info(
                "[TaskEngine] Cross-Thread-Request: %s (task_id=%s) — "
                "routing to main thread", name, task_id
            )
            worker.moveToThread(app.thread())
            # Verify moveToThread succeeded — if it failed (e.g. worker has
            # parent in another thread), proceeding would cause the main thread
            # to call moveToThread on a worker it doesn't own -> ACCESS_VIOLATION.
            if worker.thread() != app.thread():
                logging.error(
                    "[TaskEngine] moveToThread FAILED for '%s' (task_id=%s) — "
                    "worker still in thread %s, expected %s. Skipping.",
                    name, task_id, worker.thread(), app.thread(),
                )
                try:
                    worker.deleteLater()
                except RuntimeError:
                    pass
                return task_id
            self._cross_thread_request.emit(
                task_id, name, description, worker, on_finish, on_error
            )
            return task_id
        else:
            # Main-Thread: direkt ausfuehren
            return self._start_in_main_thread(
                task_id, name, description, worker, on_finish, on_error
            )

    def _start_in_main_thread(
        self,
        task_id: str,
        name: str,
        description: str,
        worker: QObject,
        on_finish=None,
        on_error=None,
    ) -> TaskInfo:
        """Tatsaechliche Thread-Erstellung — laeuft IMMER im Main-Thread.

        Wird direkt aufgerufen (Main-Thread) oder via QueuedConnection
        (Cross-Thread-Signal).
        """
        # FIX B-002: Falls App gerade schliesst, keinen neuen Thread mehr starten.
        # Die QueuedConnection kann diesen Slot NACH closeEvent() liefern.
        if self._shutting_down:
            logging.warning(
                "[TaskEngine] _start_in_main_thread nach Shutdown ignoriert: %s", name
            )
            try:
                worker.deleteLater()
            except RuntimeError as exc:
                logger.warning("worker.deleteLater() failed in _start_in_main_thread: %s", exc)
            return TaskInfo(task_id, name, description)  # Dummy, nie zu _tasks hinzugefügt

        task = TaskInfo(task_id, name, description)

        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        # Task-ID am Worker speichern fuer Cancel-Lookup
        worker.task_id = task_id

        # Progress-Signal → update_task (falls Worker eins hat)
        if hasattr(worker, "progress"):
            worker.progress.connect(
                lambda pct, msg, _tid=task_id: self.update_task(_tid, pct, message=msg)
            )

        # Finish-Guard: skip on_finish wenn Worker im Error-Pfad ist
        # Qt erkennt QueuedConnection automatisch bei Cross-Thread-Signals.
        if on_finish:
            def _guarded_finish(*args, _w=worker, _cb=on_finish):
                if not getattr(_w, '_errored', False):
                    _cb(*args)
            worker.finished.connect(_guarded_finish)

        # Error-Signal: IMMER Task als Error markieren + optional custom callback.
        if hasattr(worker, "error"):
            def _task_error_handler(*args, _tid=task_id, _name=name, _tm=self):
                err_msg = str(args[-1]) if args else "Unbekannter Fehler"
                logging.error(
                    "[TaskEngine] Worker-Fehler '%s' (task_id=%s): %s",
                    _name, _tid, err_msg,
                )
                _tm.finish_task(_tid, status="error", message=err_msg)
            worker.error.connect(_task_error_handler)

            if on_error:
                worker.error.connect(on_error)

        # Thread-Lifecycle: finished → quit → cleanup (deleteLater nur einmal!)
        worker.finished.connect(thread.quit)
        # KRITISCH: Error muss Thread ebenfalls beenden — sonst bleibt der Thread
        # am Leben, haelt DB-Connections und verursacht "database is locked" Fehler.
        if hasattr(worker, "error"):
            worker.error.connect(thread.quit)
        def _safe_cleanup(_tid=task_id):
            """Guard: Sicherer Cleanup von Worker und Thread (Fix A-02)."""
            app_thread = QApplication.instance().thread()
            with self._tasks_lock:
                task = self._tasks.get(_tid)
            
            if task:
                if task.worker:
                    try:
                        # KRITISCH: Falls der Thread tot ist, wuerde deleteLater() nie feuern.
                        # Wir holen den Worker zurueck in den Main-Thread fuer sicheren Cleanup.
                        task.worker.moveToThread(app_thread)
                        task.worker.deleteLater()
                    except (RuntimeError, AttributeError):
                        pass
                    task.worker = None
                
                if task.thread:
                    try:
                        task.thread.deleteLater()
                    except (RuntimeError, AttributeError):
                        pass
                    task.thread = None

            # Aggressiver Speicher-Cleanup im Main-Thread (Fix F-011)
            # Jetzt sicher, da der Worker-Thread beendet ist.
            try:
                import gc
                gc.collect()
                gc.collect()
            except Exception:
                pass
            
            self._on_thread_done(_tid)
        thread.finished.connect(_safe_cleanup)

        # Referenzen halten (GC-Schutz)
        task.thread = thread
        task.worker = worker
        # FIX B-011: Schütze dict-Modifikation mit Lock gegen concurrent clear_finished()
        with self._tasks_lock:
            self._tasks[task_id] = task

        self.task_added.emit(task_id)

        # TaskManagerDock sichtbar machen (via Signal)
        self.show_dock_requested.emit()

        thread.start()
        logging.info("[TaskEngine] Gestartet: %s (task_id=%s)", name, task_id)
        return task

    # ------------------------------------------------------------------
    # Legacy-kompatibles API (fuer register_actions.py etc.)
    # ------------------------------------------------------------------

    def create_task(self, name: str, description: str = "") -> TaskInfo:
        """Erstellt nur Metadaten-Task (ohne Thread).
        Fuer Aktionen die keinen Worker haben (z.B. synchrone Calls).
        """
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        task = TaskInfo(task_id, name, description)
        # FIX B-011: Schütze dict-Modifikation mit Lock
        with self._tasks_lock:
            self._tasks[task_id] = task
        self.task_added.emit(task_id)
        return task

    def update_task(self, task_id: str, progress: int = 0, total: int = 100,
                    message: str = ""):
        # FIX B-011: Schütze dict-Zugriff mit Lock
        with self._tasks_lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                t.progress = progress
                t.total = total
                t.message = message
        self.task_updated.emit(task_id)

    def finish_task(self, task_id: str, status: str = "finished", message: str = ""):
        # FIX B-011: Schütze dict-Zugriff mit Lock
        with self._tasks_lock:
            if task_id in self._tasks:
                t = self._tasks[task_id]
                t.status = status
                t.message = message
        self.task_finished.emit(task_id)

    def unload_in_background(self):
        """Führt ModelManager.unload() in einem Hintergrund-Thread aus (Fix A-03)."""
        class UnloadWorker(QObject):
            finished = Signal()
            def run(self):
                try:
                    from services.model_manager import ModelManager
                    ModelManager().unload()
                except Exception as e:
                    logging.warning("[TaskEngine] Background unload failed: %s", e)
                finally:
                    self.finished.emit()

        worker = UnloadWorker()
        self.start_task(
            name="VRAM aufräumen",
            worker=worker,
            description="Entlädt KI-Modelle im Hintergrund"
        )

    def cancel_task(self, task_id: str):
        """Bricht einen laufenden Task kooperativ ab (Fix F-002).
        
        Vermeidet terminate() um Access Violations zu verhindern.
        Der Thread wird via worker.cancel() benachrichtigt und laeuft
        im Hintergrund aus (Orphaned-Status).
        """
        with self._tasks_lock:
            task = self._tasks.get(task_id)
        if not task or task.status != "running":
            return
        
        worker = task.worker
        if worker and hasattr(worker, "cancel"):
            worker.cancel()
            
        thread = task.thread
        if thread and thread.isRunning():
            thread.quit()
            # Wir warten NICHT blockierend im Main-Thread, um Freezes zu vermeiden.
            # Der Thread wird via _safe_cleanup bereinigt, sobald er stoppt.
            if not thread.wait(2000):
                logging.warning("[TaskEngine] Thread '%s' reagiert nicht sofort auf quit() — orphaned.", task_id)

        # MEDIUM-8 FIX: Only release locks if the current thread actually holds them.
        # The previous brute-force loop could release locks owned by other threads,
        # corrupting lock state.
        try:
            from services.model_manager import GPU_LOAD_LOCK, GPU_EXECUTION_LOCK
            if GPU_LOAD_LOCK._is_owned():
                GPU_LOAD_LOCK.release()
            if GPU_EXECUTION_LOCK._is_owned():
                GPU_EXECUTION_LOCK.release()
        except Exception:
            pass
        
        self.finish_task(task_id, "cancelled", "Abbruch angefordert")
        logging.info("[TaskEngine] Kooperativer Abbruch: %s", task_id)

    def get_task(self, task_id: str) -> TaskInfo | None:
        # FIX B-011: Schütze dict-Zugriff mit Lock
        with self._tasks_lock:
            return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[TaskInfo]:
        # FIX B-011: Schütze dict-Zugriff mit Lock
        with self._tasks_lock:
            return list(self._tasks.values())

    def clear_finished(self):
        # FIX B-011: Schütze dict-Iteration und Modifikation mit Lock
        to_remove = []
        with self._tasks_lock:
            for k, v in self._tasks.items():
                if v.status != "running":
                    to_remove.append(k)
            for k in to_remove:
                task = self._tasks.pop(k)
                # Guard: nur deleteLater wenn noch nicht vom thread.finished-Handler erledigt
                if task.worker:
                    try:
                        task.worker.deleteLater()
                    except RuntimeError as exc:
                        logger.warning("task.worker.deleteLater() failed in cleanup: %s", exc)
                if task.thread:
                    try:
                        task.thread.deleteLater()
                    except RuntimeError as exc:
                        logger.warning("task.thread.deleteLater() failed in cleanup: %s", exc)

    # ------------------------------------------------------------------
    # Interner Cleanup
    # ------------------------------------------------------------------

    def _on_thread_done(self, task_id: str):
        """Wird aufgerufen wenn ein Thread fertig ist."""
        # FIX AUD-33: Schütze dict-Zugriff mit Lock (Race Condition)
        with self._tasks_lock:
            task = self._tasks.get(task_id)
        if task and task.status == "running":
            self.finish_task(task_id, "finished", "Fertig")


# Singleton-Instanz: Wird in main() an QApplication verankert.
# Zugriff ausschliesslich ueber QApplication.instance().task_manager
task_manager = None  # Lazy — wird in main() gesetzt
