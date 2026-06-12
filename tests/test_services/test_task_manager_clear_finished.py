"""B-500 Regression-Tests: clear_finished() darf laufende Threads nicht zerstoeren.

Bug: cancel_task() ist kooperativ — der Task-Status springt sofort auf
"cancelled", obwohl der QThread im Hintergrund weiterlaeuft. clear_finished()
raeumte bisher ALLE Tasks mit status != "running" ab und rief deleteLater()
auf Worker+Thread — bei noch laufendem Thread loest das den Qt-FATAL
"QThread: Destroyed while thread is still running" aus (App-Crash).

Fix: clear_finished() ueberspringt Tasks deren Thread noch laeuft
(isRunning()-Check), markiert sie mit pending_clear=True, und
_on_thread_done() entfernt sie nach echtem Thread-Ende (deferred removal;
deleteLater uebernimmt _safe_cleanup via thread.finished).

Qt-Mocks: KEINE echten QThreads — Mock-Objekte mit isRunning/deleteLater,
shiboken6.isValid wird gemonkeypatcht (Mocks sind keine PySide-Objekte).
"""

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
    """shiboken6.isValid akzeptiert keine MagicMocks → patchen.

    Mocks gelten als 'valide C++-Objekte', damit der Code-Pfad bis zum
    isRunning()-Check bzw. deleteLater() laeuft.
    """
    import services.task_manager as tm_mod
    monkeypatch.setattr(tm_mod.shiboken6, "isValid", lambda obj: True)


def _make_task_with_mock_thread(mgr, name: str, status: str, is_running: bool):
    """Erzeugt einen Task mit gemocktem Thread+Worker und gesetztem Status."""
    task = mgr.create_task(name)
    thread = MagicMock(name=f"thread_{name}")
    thread.isRunning.return_value = is_running
    worker = MagicMock(name=f"worker_{name}")
    task.thread = thread
    task.worker = worker
    task.status = status
    return task, thread, worker


# ---------------------------------------------------------------------------
# (a) Cancelled-Task mit noch laufendem Thread → ueberspringen
# ---------------------------------------------------------------------------

class TestClearFinishedSkipsRunningThreads:
    def test_cancelled_task_with_running_thread_is_kept(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        task, thread, worker = _make_task_with_mock_thread(
            mgr, "Cancelled But Thread Alive", "cancelled", is_running=True
        )

        mgr.clear_finished()

        # Task bleibt erhalten — kein pop, kein deleteLater
        all_ids = {t.task_id for t in mgr.get_all_tasks()}
        assert task.task_id in all_ids, (
            "B-500: Task mit laufendem Thread darf von clear_finished() "
            "NICHT entfernt werden"
        )
        thread.deleteLater.assert_not_called()
        worker.deleteLater.assert_not_called()
        # Markiert fuer spaetere Abraeumung
        assert task.pending_clear is True

    def test_cancelled_task_with_finished_thread_is_removed(self, qapp):
        """(b) Thread laeuft NICHT mehr → regulaer abraeumen + deleteLater."""
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        task, thread, worker = _make_task_with_mock_thread(
            mgr, "Cancelled Thread Done", "cancelled", is_running=False
        )

        mgr.clear_finished()

        assert mgr.get_task(task.task_id) is None
        thread.deleteLater.assert_called_once()
        worker.deleteLater.assert_called_once()

    def test_finished_task_with_finished_thread_is_removed(self, qapp):
        """Normalfall 'finished' bleibt unveraendert funktionsfaehig."""
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        task, thread, worker = _make_task_with_mock_thread(
            mgr, "Finished Normal", "finished", is_running=False
        )

        mgr.clear_finished()

        assert mgr.get_task(task.task_id) is None
        thread.deleteLater.assert_called_once()
        worker.deleteLater.assert_called_once()

    def test_finished_task_without_thread_is_removed(self, qapp):
        """Metadaten-Task (create_task ohne Worker, thread=None) wird
        weiterhin abgeraeumt — Regression gegen zu aggressives Skippen."""
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        task = mgr.create_task("Meta Task")
        mgr.finish_task(task.task_id, "finished")

        mgr.clear_finished()

        assert mgr.get_task(task.task_id) is None

    # -----------------------------------------------------------------
    # (c) Regression: status "running" bleibt unberuehrt
    # -----------------------------------------------------------------

    def test_running_task_is_untouched(self, qapp):
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        task, thread, worker = _make_task_with_mock_thread(
            mgr, "Still Running", "running", is_running=True
        )

        mgr.clear_finished()

        assert mgr.get_task(task.task_id) is task
        thread.deleteLater.assert_not_called()
        worker.deleteLater.assert_not_called()
        assert task.pending_clear is False


# ---------------------------------------------------------------------------
# Deferred removal: _on_thread_done raeumt uebersprungene Tasks spaeter ab
# ---------------------------------------------------------------------------

class TestDeferredRemovalAfterThreadEnd:
    def test_pending_clear_task_removed_on_thread_done(self, qapp):
        """Nach echtem Thread-Ende (thread.finished → _safe_cleanup →
        _on_thread_done) wird der uebersprungene Task aus _tasks entfernt."""
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        task, thread, worker = _make_task_with_mock_thread(
            mgr, "Deferred Clear", "cancelled", is_running=True
        )

        mgr.clear_finished()  # ueberspringt → pending_clear=True
        assert task.pending_clear is True
        assert mgr.get_task(task.task_id) is not None

        finished_signals = []
        mgr.task_finished.connect(lambda tid: finished_signals.append(tid))

        # Thread endet jetzt wirklich → _on_thread_done feuert (im echten
        # Pfad via thread.finished → _safe_cleanup, der vorher deleteLater
        # auf Worker+Thread ausfuehrt)
        mgr._on_thread_done(task.task_id)
        qapp.processEvents()

        assert mgr.get_task(task.task_id) is None, (
            "B-500: pending_clear-Task muss nach Thread-Ende aus _tasks "
            "entfernt werden"
        )
        assert task.task_id in finished_signals

    def test_task_without_pending_clear_stays_after_thread_done(self, qapp):
        """Cancelled-Task OHNE clear-Klick bleibt nach Thread-Ende sichtbar
        (bisheriges Verhalten: erst clear_finished() entfernt ihn)."""
        from services.task_manager import GlobalTaskManager
        mgr = GlobalTaskManager.instance()
        task, thread, worker = _make_task_with_mock_thread(
            mgr, "Cancelled No Clear", "cancelled", is_running=True
        )

        mgr._on_thread_done(task.task_id)

        assert mgr.get_task(task.task_id) is task
        assert task.status == "cancelled"
