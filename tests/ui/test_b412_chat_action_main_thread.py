from __future__ import annotations

import threading
import time

from PySide6.QtCore import QThread


def _run_action_from_background(qapp, action):
    result_box = {}

    def run_action():
        result_box["result"] = action()

    worker = threading.Thread(target=run_action)
    worker.start()

    deadline = time.monotonic() + 3
    while worker.is_alive() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)

    worker.join(timeout=0)
    assert not worker.is_alive()
    return result_box["result"]


def test_b412_undo_timeline_runs_gui_call_on_qt_main_thread(qapp, monkeypatch):
    from services.actions import edit_actions
    # AUFRAEUM B1: undo/redo_timeline liegen jetzt in timeline_actions und binden
    # _get_main_window aus dem eigenen Namespace -> dort patchen.
    from services.actions.edit import timeline_actions

    class _UndoStack:
        def __init__(self):
            self.undo_thread = None

        def canUndo(self):
            return True

        def undoText(self):
            return "clip move"

        def undo(self):
            self.undo_thread = QThread.currentThread()

    class _TimelineView:
        def __init__(self):
            self.undo_stack = _UndoStack()

    class _MainWindow:
        def __init__(self):
            self.timeline_view = _TimelineView()

    main_window = _MainWindow()
    monkeypatch.setattr(timeline_actions, "_get_main_window", lambda: main_window)

    result = _run_action_from_background(qapp, edit_actions.undo_timeline)

    assert result["status"] == "ok"
    assert main_window.timeline_view.undo_stack.undo_thread is qapp.thread()


def test_b412_redo_timeline_runs_gui_call_on_qt_main_thread(qapp, monkeypatch):
    from services.actions import edit_actions
    # AUFRAEUM B1: undo/redo_timeline liegen jetzt in timeline_actions und binden
    # _get_main_window aus dem eigenen Namespace -> dort patchen.
    from services.actions.edit import timeline_actions

    class _UndoStack:
        def __init__(self):
            self.redo_thread = None

        def canRedo(self):
            return True

        def redoText(self):
            return "clip move"

        def redo(self):
            self.redo_thread = QThread.currentThread()

    class _TimelineView:
        def __init__(self):
            self.undo_stack = _UndoStack()

    class _MainWindow:
        def __init__(self):
            self.timeline_view = _TimelineView()

    main_window = _MainWindow()
    monkeypatch.setattr(timeline_actions, "_get_main_window", lambda: main_window)

    result = _run_action_from_background(qapp, edit_actions.redo_timeline)

    assert result["status"] == "ok"
    assert main_window.timeline_view.undo_stack.redo_thread is qapp.thread()
