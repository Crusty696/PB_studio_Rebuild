from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import QObject, Signal
import pytest

class _FakeSignal:
    def __init__(self):
        self.disconnected: list[object] = []
        self._slots: list[object] = []

    def connect(self, slot):
        self._slots.append(slot)

    def disconnect(self, slot):
        self.disconnected.append(slot)
        if slot in self._slots:
            self._slots.remove(slot)

    def emit(self, *args, **kwargs):
        for slot in list(self._slots):
            slot(*args, **kwargs)


class _FakeProjectManager:
    def __init__(self, path: Path | None):
        self.current_project_path = path


class _FakeMediaTableController:
    def __init__(self):
        self.refreshed = False

    def _refresh_media_table(self):
        self.refreshed = True


class _FakeTimelineView:
    def __init__(self):
        self.loaded = False

    def load_from_db(self):
        self.loaded = True


class _FakeMainWindow:
    def __init__(self, project_path: Path | None):
        self._project_manager = _FakeProjectManager(project_path)
        self.media_table_controller = _FakeMediaTableController()
        self.timeline_view = _FakeTimelineView()


def test_b417_stale_worker_result_ignored_on_project_change(monkeypatch):
    from ui.chat_dock import ChatDock, AIAgentWorker

    # Setup MainWindow with Project A
    path_a = Path("C:/projects/A")
    mw = _FakeMainWindow(path_a)

    dock = ChatDock.__new__(ChatDock)
    dock._main_window = mw
    dock._worker = None
    dock._thread = None
    dock._watchdog_timer = None
    dock._current_request_id = 0
    dock._active_request_id = None
    
    # Mock UI functions that we don't want to fail on
    dock.input_field = _FakeSignal() # placeholder for setEnabled
    dock.btn_send = _FakeSignal()
    dock.input_field.setEnabled = lambda x: None
    dock.btn_send.setEnabled = lambda x: None
    dock.input_field.setFocus = lambda: None
    
    dock._stop_watchdog = lambda: None
    dock._remove_status_line = lambda: None
    dock.append_action = lambda a, r: None
    dock.append_divider = lambda: None

    # We start a real AIAgentWorker for Project A (we pass None as agent)
    worker = AIAgentWorker(None, "test")
    
    # Apply our properties (which will be implemented in the fix)
    worker.request_id = 1
    worker.project_path = path_a
    
    # Configure dock active request
    dock._active_request_id = 1
    dock._worker = worker

    # Simuliere Projektwechsel im MainWindow zu Projekt B
    path_b = Path("C:/projects/B")
    mw._project_manager.current_project_path = path_b

    # Der alte Worker liefert nun sein Ergebnis (z.B. delete_media)
    result = {"action": "delete_media", "result": "ok"}
    
    # Da wir in Python/Qt testen, rufen wir _on_agent_finished manuell auf
    # Wir mocken die sender() Methode von QObject so, dass sie unseren Worker zurückliefert
    monkeypatch.setattr(dock, "sender", lambda: worker)

    # Ausführen
    dock._on_agent_finished(result)

    # Erwartung: Da das Projekt gewechselt wurde, darf die Medien-Tabelle
    # des neuen Projekts B NICHT aktualisiert worden sein!
    assert mw.media_table_controller.refreshed is False, "UI refreshed in wrong project context!"


def test_b417_stale_worker_result_ignored_on_watchdog_timeout(monkeypatch):
    from ui.chat_dock import ChatDock, AIAgentWorker

    path_a = Path("C:/projects/A")
    mw = _FakeMainWindow(path_a)

    dock = ChatDock.__new__(ChatDock)
    dock._main_window = mw
    dock._worker = None
    dock._thread = None
    dock._watchdog_timer = None
    dock._current_request_id = 0
    dock._active_request_id = None
    
    dock.input_field = _FakeSignal()
    dock.btn_send = _FakeSignal()
    dock.input_field.setEnabled = lambda x: None
    dock.btn_send.setEnabled = lambda x: None
    dock.input_field.setFocus = lambda: None
    
    dock._stop_watchdog = lambda: None
    dock._remove_status_line = lambda: None
    dock.append_action = lambda a, r: None
    dock.append_divider = lambda: None

    # Worker erstellen
    worker = AIAgentWorker(None, "test")
    worker.request_id = 1
    worker.project_path = path_a
    
    dock._active_request_id = 1
    dock._worker = worker

    # Watchdog schlägt an: nullt active_request_id
    dock._active_request_id = None

    # Simuliere verspätetes finished-Signal
    result = {"action": "delete_media", "result": "ok"}
    monkeypatch.setattr(dock, "sender", lambda: worker)

    dock._on_agent_finished(result)

    # Erwartung: Da der Watchdog gefeuert hat (active_request_id entwertet),
    # darf kein UI-Refresh stattfinden.
    assert mw.media_table_controller.refreshed is False, "UI refreshed after watchdog timeout!"
