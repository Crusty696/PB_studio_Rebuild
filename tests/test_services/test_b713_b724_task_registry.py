"""B-713 + B-724: Regressionstests fuer services/task_manager.py.

B-713: Beide Abbruchpfade von ``start_task`` gaben eine ID bzw. TaskInfo
zurueck, die nie in ``_tasks`` registriert wurde. Der Aufrufer hielt eine
tote ID — ``get_task``/``update_task``/``finish_task`` waren stille No-Ops.

B-724: Ein spaet eintreffender Worker-``error`` ueberschrieb den Status
eines bereits abgebrochenen Tasks ("Fehler" statt "Abgebrochen").
"""

from __future__ import annotations

import inspect
import threading

import pytest

pytest.importorskip("PySide6")


class _FakeWorker:
    """Minimaler Stand-in — beide getesteten Pfade brechen ab, bevor echte
    Qt-Worker-APIs gebraucht werden."""

    def __init__(self, thread_obj=None):
        self._thread_obj = thread_obj
        self.deleted = False

    def moveToThread(self, target):  # noqa: N802 (Qt-API-Name)
        # Simuliert einen fehlgeschlagenen Ownership-Wechsel: der Worker
        # bleibt in seinem alten Thread.
        return None

    def thread(self):
        return self._thread_obj

    def deleteLater(self):  # noqa: N802 (Qt-API-Name)
        self.deleted = True


# ---------------------------------------------------------------------------
# B-713
# ---------------------------------------------------------------------------

def test_b713_failed_move_to_thread_registers_task(qapp):
    """start_task aus BG-Thread: moveToThread schlaegt fehl -> die
    zurueckgegebene task_id MUSS trotzdem auffindbar sein."""
    from services.task_manager import GlobalTaskManager

    tm = GlobalTaskManager.instance()
    tm._shutting_down = False
    worker = _FakeWorker(thread_obj=None)  # thread() != app.thread()

    result: list = [None]

    def _bg_call():
        result[0] = tm.start_task(
            name="b713-move-fail", worker=worker, description="movefail"
        )

    t = threading.Thread(target=_bg_call, daemon=True)
    t.start()
    t.join(timeout=5.0)

    task_id = result[0]
    assert isinstance(task_id, str)
    assert worker.deleted is True, "Worker muss aufgeraeumt werden"

    task = tm.get_task(task_id)
    assert task is not None, (
        "B-713: start_task gab eine task_id zurueck, die nicht in _tasks "
        "registriert wurde -> tote ID"
    )
    assert task.status == "error"
    assert task.thread is None and task.worker is None

    # Folge-Aufrufe des Aufrufers duerfen keine stillen No-Ops mehr sein.
    tm.update_task(task_id, progress=42, message="x")
    assert tm.get_task(task_id).progress == 42


def test_b713_shutdown_path_registers_task(qapp):
    """_start_in_main_thread waehrend Shutdown: die zurueckgegebene TaskInfo
    MUSS registriert sein (vorher: Dummy, nie in _tasks)."""
    from services.task_manager import GlobalTaskManager

    tm = GlobalTaskManager.instance()
    worker = _FakeWorker()
    prev = tm._shutting_down
    tm._shutting_down = True
    try:
        task = tm._start_in_main_thread(
            "b713_shutdown_id", "B713 Shutdown", "", worker, None, None
        )
    finally:
        tm._shutting_down = prev

    assert worker.deleted is True
    assert task.name == "B713 Shutdown"
    # B-002 bleibt gewahrt: kein Thread gestartet.
    assert task.thread is None and task.worker is None

    assert tm.get_task("b713_shutdown_id") is not None, (
        "B-713: Shutdown-Pfad gab eine Dummy-TaskInfo zurueck, die nie in "
        "_tasks landete -> tote ID"
    )
    assert tm.get_task("b713_shutdown_id").status == "cancelled"

    tm.finish_task("b713_shutdown_id", "error", "spaeter Fehler")
    assert tm.get_task("b713_shutdown_id").status == "error"

    tm.clear_finished()


# ---------------------------------------------------------------------------
# B-724
# ---------------------------------------------------------------------------

def test_b724_late_worker_error_does_not_overwrite_cancelled(qapp):
    """Worker-error nach cancel_task darf 'cancelled' nicht ueberschreiben."""
    from services.task_manager import GlobalTaskManager

    tm = GlobalTaskManager.instance()
    task = tm.create_task("b724 cancel then worker-error")
    tm.cancel_task(task.task_id)
    assert tm.get_task(task.task_id).status == "cancelled"

    # Exakt der Pfad, den das Worker-error-Signal ausloest.
    tm._handle_worker_error(task.task_id, "b724 worker", ("Abgebrochen",))

    t = tm.get_task(task.task_id)
    assert t.status == "cancelled", (
        f"B-724: spaeter Worker-Fehler hat 'cancelled' ueberschrieben -> {t.status}"
    )


def test_b724_worker_error_on_running_task_still_sets_error(qapp):
    """Gegenprobe: bei laufendem Task setzt der Worker-Fehler weiterhin
    'error' (keine Ueber-Blockade)."""
    from services.task_manager import GlobalTaskManager

    tm = GlobalTaskManager.instance()
    task = tm.create_task("b724 normal error")

    tm._handle_worker_error(task.task_id, "b724 worker", (7, "OOM"))

    t = tm.get_task(task.task_id)
    assert t.status == "error"
    assert t.message == "OOM"


def test_b724_error_handler_is_wired_into_start_path():
    """Der Worker-error-Slot muss ueber _handle_worker_error laufen, sonst
    greift der B-724-Vorrang im echten Signalpfad nicht."""
    from services.task_manager import GlobalTaskManager

    src = inspect.getsource(GlobalTaskManager._start_in_main_thread)
    assert "_handle_worker_error" in src
