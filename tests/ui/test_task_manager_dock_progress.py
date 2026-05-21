import pytest
from PySide6.QtWidgets import QApplication


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


def test_b323_task_dock_ignores_non_numeric_progress(qapp):
    from services.task_manager import GlobalTaskManager
    from ui.widgets.task_manager_dock import TaskManagerDock

    dock = TaskManagerDock()
    tm = GlobalTaskManager.instance()
    task = tm.create_task("bad-progress", "Regression B-323")
    qapp.processEvents()

    task.progress = "Initialisierung..."
    task.total = 100

    dock._on_task_updated(task.task_id)

    row = dock._task_rows[task.task_id]
    progress_bar = row["progress_bar"]
    msg_label = row["msg_label"]
    assert progress_bar.minimum() == 0
    assert progress_bar.maximum() == 0
    assert msg_label.text() == ""


def test_b325_task_dock_handles_float_message(qapp):
    from services.task_manager import GlobalTaskManager
    from ui.widgets.task_manager_dock import TaskManagerDock

    dock = TaskManagerDock()
    tm = GlobalTaskManager.instance()
    task = tm.create_task("float-message", "Regression B-325")
    qapp.processEvents()

    task.message = 13.37

    dock._on_task_updated(task.task_id)

    row = dock._task_rows[task.task_id]
    msg_label = row["msg_label"]
    assert msg_label.text() == "13.37"
    assert msg_label.toolTip() == "13.37"
