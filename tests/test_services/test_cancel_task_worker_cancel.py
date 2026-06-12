"""B-507 Regression-Tests: cancel_task() muss worker.cancel() real aufrufen.

Bug (Consulting-Review H-8): cancel_task() setzte zusaetzlich ein
``_gpu_cancel_requested``-Flag auf den Worker (FIX-H-15-Block). Das Flag
hatte repo-weit NULL Leser (toter Code), und der Guard war invertiert
(``if worker and not hasattr(worker, '_gpu_cancel_requested')`` — setzte
das Flag nur, wenn es noch nicht existierte; gelesen wurde es nie).

Fix: Toter Block entfernt. Der einzige reale Cancel-Mechanismus ist
``worker.cancel()`` (CancellableMixin, workers/base.py) — abgesichert mit
try/except RuntimeError fuer bereits via deleteLater zerstoerte Qt-Objekte.

Qt-Mocks: KEINE echten QThreads — Mock-Objekte, shiboken6.isValid wird
gemonkeypatcht (gleiche Mechanik wie test_task_manager_clear_finished.py).
"""

import inspect

import pytest
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication


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
    if GlobalTaskManager._instance is not None:
        inst = GlobalTaskManager._instance
        inst._shutting_down = True
        GlobalTaskManager._instance = None


@pytest.fixture(autouse=True)
def patch_shiboken_isvalid(monkeypatch):
    """shiboken6.isValid akzeptiert keine MagicMocks → patchen."""
    import services.task_manager as tm_mod
    monkeypatch.setattr(tm_mod.shiboken6, "isValid", lambda obj: True)


def _make_running_task(mgr, name: str, worker):
    """Erzeugt einen 'running'-Task mit gemocktem Thread + gegebenem Worker."""
    task = mgr.create_task(name)
    thread = MagicMock(name=f"thread_{name}")
    thread.isRunning.return_value = True
    task.thread = thread
    task.worker = worker
    task.status = "running"
    return task, thread


# ---------------------------------------------------------------------------
# (1) cancel_task ruft worker.cancel() auf
# ---------------------------------------------------------------------------

class TestCancelTaskCallsWorkerCancel:
    def test_cancel_task_calls_worker_cancel(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        worker = MagicMock(name="worker_with_cancel")
        task, thread = _make_running_task(mgr, "Cancelable", worker)

        mgr.cancel_task(task.task_id)

        worker.cancel.assert_called_once_with()
        thread.quit.assert_called_once_with()
        assert task.status == "cancelled"

    def test_cancel_task_without_cancel_method_does_not_crash(self, qapp):
        """Worker ohne cancel()-API (Legacy/Fremd-QObject) → kein AttributeError."""
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        worker = MagicMock(name="worker_no_cancel", spec=["deleteLater"])
        assert not hasattr(worker, "cancel")
        task, thread = _make_running_task(mgr, "NoCancelAPI", worker)

        mgr.cancel_task(task.task_id)  # darf nicht raisen

        thread.quit.assert_called_once_with()
        assert task.status == "cancelled"

    def test_cancel_raising_runtimeerror_is_swallowed(self, qapp):
        """B-507: C++-Objekt kann zwischen isValid() und cancel() von Qt
        zerstoert werden → RuntimeError darf cancel_task nicht crashen,
        der Task muss trotzdem auf 'cancelled' gehen."""
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        worker = MagicMock(name="worker_deleted")
        worker.cancel.side_effect = RuntimeError(
            "Internal C++ object already deleted."
        )
        task, thread = _make_running_task(mgr, "DeletedWorker", worker)

        mgr.cancel_task(task.task_id)  # darf nicht raisen

        worker.cancel.assert_called_once_with()
        assert task.status == "cancelled"

    def test_cancel_task_on_non_running_task_is_noop(self, qapp):
        """Regression: Nur 'running'-Tasks sind abbrechbar."""
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        worker = MagicMock(name="worker_finished")
        task, thread = _make_running_task(mgr, "AlreadyDone", worker)
        task.status = "finished"

        mgr.cancel_task(task.task_id)

        worker.cancel.assert_not_called()
        thread.quit.assert_not_called()
        assert task.status == "finished"


# ---------------------------------------------------------------------------
# (2) Totes Flag ist wirklich weg
# ---------------------------------------------------------------------------

class TestDeadGpuCancelFlagRemoved:
    def test_no_gpu_cancel_requested_in_cancel_task_source(self):
        """Source-Inspection: das tote ``_gpu_cancel_requested``-Konstrukt
        darf in cancel_task() nicht mehr vorkommen (es hatte null Leser)."""
        from services.task_manager import GlobalTaskManager
        src = inspect.getsource(GlobalTaskManager.cancel_task)
        assert "_gpu_cancel_requested" not in src, (
            "B-507: totes _gpu_cancel_requested-Flag ist zurueck in "
            "cancel_task() — es hat repo-weit keine Leser, Cancel laeuft "
            "ausschliesslich ueber worker.cancel()/should_stop()."
        )


# ---------------------------------------------------------------------------
# (3) Beispiel-Worker: cancel() bricht die Arbeitsschleife ab
# ---------------------------------------------------------------------------

class TestCancellableMixinLoopBreak:
    def test_cancelled_worker_breaks_loop(self):
        """End-to-End-Mechanik: cancel() → should_stop() True → Loop-Break.
        Das ist der Pfad, den cancel_task() jetzt real ausloest."""
        from workers.base import CancellableMixin

        class _LoopWorker(CancellableMixin):
            def __init__(self):
                super().__init__()
                self.iterations = 0

            def run_loop(self, max_iter: int = 1000) -> None:
                for _ in range(max_iter):
                    if self.should_stop():
                        break
                    self.iterations += 1

        w = _LoopWorker()
        w.cancel()  # wie von cancel_task() via worker.cancel() ausgeloest
        w.run_loop()

        assert w.should_stop() is True
        assert w.iterations == 0, (
            "B-507: should_stop() muss die Arbeitsschleife sofort beenden"
        )
