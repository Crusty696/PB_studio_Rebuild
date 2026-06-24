"""B-552/B-567 regression: task errors must surface in the main window status bar.

Worker/task errors were only shown (red) inside the possibly-collapsed TASKS
dock and in the log, so a failed worker (e.g. export crash) gave the user no
visible hint (silent failure). `_on_task_finished` now also shows a red status
bar message on the host window for error states.
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMainWindow


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def reset_task_manager(qapp):
    from services.task_manager import GlobalTaskManager

    GlobalTaskManager._instance = None
    yield
    if GlobalTaskManager._instance is not None:
        GlobalTaskManager._instance._shutting_down = True
        GlobalTaskManager._instance = None


def _host_with_dock():
    from ui.widgets.task_manager_dock import TaskManagerDock

    win = QMainWindow()
    dock = TaskManagerDock()
    win.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    return win, dock


def test_error_task_shows_status_bar_message(qapp):
    from services.task_manager import GlobalTaskManager

    win, dock = _host_with_dock()
    tm = GlobalTaskManager.instance()
    task = tm.create_task("Export", "Finaler Export")
    qapp.processEvents()

    task.status = "error"
    task.message = "ffmpeg crashed at frame 1200"
    dock._on_task_finished(task.task_id)

    msg = win.statusBar().currentMessage()
    assert "Fehler" in msg
    assert "Export" in msg
    assert "ffmpeg" in msg


def test_finished_task_does_not_spam_status_bar(qapp):
    from services.task_manager import GlobalTaskManager

    win, dock = _host_with_dock()
    tm = GlobalTaskManager.instance()
    task = tm.create_task("Analyse", "Audio")
    qapp.processEvents()

    task.status = "finished"
    task.message = "ok"
    dock._on_task_finished(task.task_id)

    # success must not push an error status message
    assert "Fehler" not in win.statusBar().currentMessage()
