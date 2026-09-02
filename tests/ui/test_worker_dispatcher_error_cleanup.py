import os
from types import SimpleNamespace

from PySide6.QtCore import QObject, Signal
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

    # B-958: Hier stand bis 2026-09-02 eine QEventLoop, die auf `finished`
    # wartete. Im vollen Testlauf kehrte sie sofort mit rc=-1 zurueck, ohne zu
    # warten — ein frueherer Test hatte irgendwo `exit()` gerufen, was das
    # prozessweite `quitNow`-Flag setzt. Ab da startet KEINE verschachtelte
    # Event-Loop im Hauptthread mehr. Der Test prueste dann einen Zustand, der
    # noch gar nicht eingetreten war, und meldete das als Fehler der
    # Aufraeumkette.
    #
    # `QThread.wait()` ist davon nicht betroffen — gemessen: nach `app.exit(0)`
    # liefert `loop.exec()` rc=-1, waehrend `wait()` weiterhin korrekt 0,21 s
    # wartet und True liefert. Deshalb wartet der Test jetzt so.
    #
    # Wer das Flag setzt, ist weiterhin offen (siehe Vault B-958). Diese
    # Aenderung behebt den Schaden, nicht die Ursache: der Test prueft wieder
    # das, wofuer er geschrieben wurde, unabhaengig davon, was vorher lief.
    # `thread.wait()` allein taugt hier NICHT: es blockiert den Hauptthread,
    # und genau dessen Event-Loop braucht die Aufraeumkette, um `finished` und
    # `deleteLater` zuzustellen. Gemessen am 2026-09-02: mit reinem `wait()`
    # faellt der Test sogar einzeln, weil der Thread nie fertig wird.
    #
    # `processEvents()` stellt die Signale zu und ist — anders als `exec()` —
    # von `quitNow` nicht betroffen. Die Schleife kombiniert beides.
    import time

    frist = time.perf_counter() + 10.0
    while time.perf_counter() < frist:
        app.processEvents()
        if not shiboken6.isValid(thread) or not thread.isRunning():
            break
        thread.wait(20)
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
