"""Cycle 14 / Option B: BaseWorker unified pattern."""
from __future__ import annotations

import pytest

PySide6 = pytest.importorskip("PySide6")
pytestqt = pytest.importorskip("pytestqt")

from workers.base import BaseWorker, CancellableMixin, format_user_error


def test_base_worker_subclass_basic_run(qtbot, qapp):
    """Subklasse mit _do_work() läuft + finished feuert."""
    class _MyWorker(BaseWorker):
        def __init__(self):
            super().__init__()
            self.ran = False

        def _do_work(self):
            self.ran = True
            return {"ok": True}

    w = _MyWorker()
    with qtbot.waitSignal(w.finished, timeout=2000) as blocker:
        w.run()
    assert w.ran is True
    assert blocker.args == [{"ok": True}]


def test_base_worker_exception_emits_error_signal(qtbot, qapp):
    """Exception in _do_work emittiert error()."""
    class _BrokenWorker(BaseWorker):
        def _do_work(self):
            raise ValueError("intentional")

    w = _BrokenWorker()
    received_error = []
    received_finished = []
    w.error.connect(received_error.append)
    w.finished.connect(received_finished.append)
    w.run()  # exception caught internally
    assert any("intentional" in e for e in received_error)
    assert w._errored is True
    # finished feuert auch bei Error (für Cleanup-Hooks)
    assert received_finished == [None]


def test_base_worker_default_run_raises_notimplemented(qtbot, qapp):
    """Subklasse ohne _do_work() crasht via NotImplementedError → error-Signal."""
    class _IncompleteWorker(BaseWorker):
        pass

    w = _IncompleteWorker()
    received_error = []
    w.error.connect(received_error.append)
    w.run()
    assert len(received_error) == 1
    assert "_do_work() not implemented" in received_error[0]


def test_base_worker_task_id_attribute_exists(qtbot, qapp):
    class _W(BaseWorker):
        def _do_work(self):
            return self.task_id

    w = _W()
    assert w.task_id is None  # default
    w.task_id = "my-task-42"
    captured = []
    w.finished.connect(captured.append)
    w.run()
    assert captured == ["my-task-42"]


def test_base_worker_progress_signal_emits(qtbot, qapp):
    class _ProgressWorker(BaseWorker):
        def _do_work(self):
            self.progress.emit(50, "mid")
            return "done"

    w = _ProgressWorker()
    progress_events = []
    w.progress.connect(lambda pct, msg: progress_events.append((pct, msg)))
    w.run()
    assert progress_events == [(50, "mid")]


def test_base_worker_inherits_cancellable_mixin(qtbot, qapp):
    """BaseWorker hat cancel()/should_stop() von CancellableMixin."""
    class _W(BaseWorker):
        def _do_work(self):
            if self.should_stop():
                return "cancelled"
            return "completed"

    w = _W()
    w.cancel()
    captured = []
    w.finished.connect(captured.append)
    w.run()
    assert captured == ["cancelled"]


def test_format_user_error_handles_filenotfound():
    msg = format_user_error(FileNotFoundError("/tmp/nope.mp4"))
    assert "Datei nicht gefunden" in msg


def test_format_user_error_handles_permission():
    msg = format_user_error(PermissionError("/etc/secret"))
    assert "Zugriff verweigert" in msg


def test_format_user_error_generic_fallback():
    msg = format_user_error(RuntimeError("xyz"))
    assert msg == "xyz"
