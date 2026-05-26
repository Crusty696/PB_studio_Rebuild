import os
from types import SimpleNamespace

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class FakeStemWorker(QObject):
    finished = Signal(int, dict)
    error = Signal(int, str)
    progress = Signal(int, str)

    constructed_args = None

    def __init__(self, track_id: int):
        super().__init__()
        type(self).constructed_args = (track_id,)


def test_b354_media_workspace_stem_dispatch_uses_track_id_only(monkeypatch):
    import database
    import services.task_manager as task_manager
    import workers
    from ui.workspaces.media_workspace import MediaWorkspace

    QApplication.instance() or QApplication([])

    class FakeResult:
        def first(self):
            return ("C:/audio.wav", 140.0)

    class FakeSession:
        def execute(self, *args, **kwargs):
            return FakeResult()

    class FakeContext:
        def __enter__(self):
            return FakeSession()

        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeTaskManager:
        def create_task(self, name, description=""):
            return SimpleNamespace(task_id="task-b354")

    started_workers = []
    fake_pb_window = SimpleNamespace(
        _console_append=lambda *_args, **_kwargs: None,
        console_text=SimpleNamespace(append=lambda *_args, **_kwargs: None),
        media_table_controller=SimpleNamespace(
            _refresh_media_table_debounced=lambda: None,
        ),
        worker_dispatcher=SimpleNamespace(
            _start_worker_thread=lambda worker: started_workers.append(worker),
        ),
    )

    monkeypatch.setattr(database, "nullpool_session", lambda: FakeContext())
    monkeypatch.setattr(task_manager, "TaskManagerProxy", lambda: FakeTaskManager())
    monkeypatch.setattr(workers, "StemSeparationWorker", FakeStemWorker)

    workspace = MediaWorkspace()
    try:
        workspace._dispatch_audio_analysis(
            fake_pb_window,
            audio_id=7,
            title="Track",
            step_key="stem_separation",
        )
    finally:
        workspace.deleteLater()

    assert FakeStemWorker.constructed_args == (7,)
    assert len(started_workers) == 1
