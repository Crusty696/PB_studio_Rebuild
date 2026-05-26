from __future__ import annotations

class _FakeSignal:
    def __init__(self):
        self.disconnected: list[object] = []

    def disconnect(self, slot):
        self.disconnected.append(slot)


class _FakeWorker:
    def __init__(self):
        self.cancelled = False
        self.finished = _FakeSignal()
        self.error = _FakeSignal()
        self.status_changed = _FakeSignal()

    def request_cancel(self):
        self.cancelled = True


class _FakeThread:
    def __init__(self):
        self.interrupted = False
        self.quit_called = False

    def isRunning(self):
        return True

    def requestInterruption(self):
        self.interrupted = True

    def quit(self):
        self.quit_called = True

def test_b409_chat_watchdog_cancels_worker_and_thread(monkeypatch):
    from ui.chat_dock import ChatDock

    dock = ChatDock.__new__(ChatDock)
    worker = _FakeWorker()
    thread = _FakeThread()
    errors: list[str] = []

    dock._worker = worker
    dock._thread = thread
    dock._watchdog_timer = None
    dock.tr = lambda text: text
    monkeypatch.setattr(dock, "_on_agent_error", errors.append)

    dock._on_agent_watchdog()

    assert worker.cancelled is True
    assert dock._on_agent_finished in worker.finished.disconnected
    assert dock._on_agent_error in worker.error.disconnected
    assert dock._on_agent_status in worker.status_changed.disconnected
    assert thread.interrupted is True
    assert thread.quit_called is True
    assert errors and "Timeout" in errors[0]
