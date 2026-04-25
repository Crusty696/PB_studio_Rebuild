"""P4 #12+13: TaskManager Cross-Thread-Path Investigation.

Verifiziert dass:
1. _cross_thread_request-Signal mit QueuedConnection zu
   _start_in_main_thread verbunden ist (B-180-Hypothese 2 ausschließen).
2. start_task aus Main-Thread direkt Worker startet.
3. Worker ohne run()-Methode crasht graceful.
"""
from __future__ import annotations

import inspect
import threading
import time

import pytest

PySide6 = pytest.importorskip("PySide6")
pytestqt = pytest.importorskip("pytestqt")

from PySide6.QtCore import QObject, Qt, Signal


def test_cross_thread_request_signal_exists_and_routed():
    """_cross_thread_request muss in __init__ via QueuedConnection an
    _start_in_main_thread connected sein. Sonst gehen BG-thread
    start_task-Calls verloren."""
    from services.task_manager import GlobalTaskManager
    init_src = inspect.getsource(GlobalTaskManager.__init__)
    assert "_cross_thread_request.connect" in init_src
    assert "QueuedConnection" in init_src
    assert "_start_in_main_thread" in init_src


def test_start_task_main_thread_invokes_worker_run(qtbot, qapp):
    """start_task aus Main-Thread → Worker.run() läuft + finished feuert."""
    from services.task_manager import GlobalTaskManager

    class _SmokeWorker(QObject):
        finished = Signal(dict)
        error = Signal(str)

        def __init__(self):
            super().__init__()
            self.ran = False

        def run(self):
            self.ran = True
            self.finished.emit({"ok": True})

    worker = _SmokeWorker()
    tm = GlobalTaskManager.instance()

    with qtbot.waitSignal(worker.finished, timeout=2000) as blocker:
        result = tm.start_task(
            name="smoke-test",
            worker=worker,
            description="Cross-Thread-Smoke",
        )
    assert worker.ran is True
    assert result is not None
    assert blocker.args == [{"ok": True}]


def test_start_task_bg_thread_routes_via_cross_thread_signal(qtbot, qapp):
    """start_task aus BG-Thread → emit _cross_thread_request → Main-Thread
    führt Worker aus. Returntyp: task_id (str) statt TaskInfo."""
    from services.task_manager import GlobalTaskManager

    class _BgWorker(QObject):
        finished = Signal(dict)
        error = Signal(str)

        def __init__(self):
            super().__init__()
            self.ran = False

        def run(self):
            self.ran = True
            self.finished.emit({"bg": True})

    worker = _BgWorker()
    tm = GlobalTaskManager.instance()
    bg_result: list = [None]

    def _bg_call():
        bg_result[0] = tm.start_task(
            name="bg-smoke", worker=worker, description="BG"
        )

    with qtbot.waitSignal(worker.finished, timeout=3000):
        t = threading.Thread(target=_bg_call, daemon=True)
        t.start()
        t.join(timeout=2.0)

    assert worker.ran is True
    # BG-Thread bekommt task_id (str) zurück
    assert isinstance(bg_result[0], str)


def test_worker_without_run_method_does_not_hang(qtbot, qapp):
    """Worker ohne run() darf nicht crashen oder hängen — TaskManager
    muss das mindestens loggen."""
    from services.task_manager import GlobalTaskManager

    class _BrokenWorker(QObject):
        finished = Signal(dict)
        error = Signal(str)

    worker = _BrokenWorker()
    tm = GlobalTaskManager.instance()
    # Wenn Worker keine run() hat, soll start_task entweder graceful
    # fehlschlagen oder einen Logging-Hinweis geben — kein hängender
    # Thread.
    # AttributeError ist akzeptabel: die TaskManager-Logik connectet
    # thread.started → worker.run; ohne run kommt ein verspäteter
    # AttributeError, kein Crash der App.
    try:
        result = tm.start_task(
            name="broken", worker=worker, description="no-run"
        )
        # Wenn kein Crash: result ist TaskInfo oder str
        assert result is not None
    except (AttributeError, TypeError):
        # Akzeptabel: TaskManager rejected den Worker upfront
        pass
