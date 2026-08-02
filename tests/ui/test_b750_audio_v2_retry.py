"""B-750: sichtbare optionale Audio-V2-Retries müssen Worker starten."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest


class _Signal:
    def connect(self, *_args, **_kwargs):
        return None


class _RetryWorker:
    created: list[tuple[int, str, tuple[str, ...]]] = []

    def __init__(self, audio_id, file_path, *, retry_step_keys):
        self.created.append((audio_id, file_path, tuple(retry_step_keys)))
        self.progress = _Signal()
        self.finished = _Signal()
        self.error = _Signal()
        self.task_id = None


@pytest.mark.parametrize("step_key", ["onset_detection", "av_pacing_curves"])
def test_optional_audio_retry_dispatches_targeted_v2_worker(monkeypatch, step_key):
    import database
    import services.task_manager as task_manager_module
    import workers.audio_pipeline_v2_worker as worker_module
    from ui.workspaces.media_workspace import MediaWorkspace

    @contextmanager
    def _session():
        row = SimpleNamespace(first=lambda: ("C:/isolated/audio.wav", 128.0))
        yield SimpleNamespace(execute=lambda *_args, **_kwargs: row)

    task = SimpleNamespace(task_id="retry-task")
    manager = SimpleNamespace(create_task=lambda *_args: task)
    monkeypatch.setattr(database, "nullpool_session", _session)
    monkeypatch.setattr(task_manager_module, "TaskManagerProxy", lambda: manager)
    monkeypatch.setattr(worker_module, "AudioPipelineV2Worker", _RetryWorker)
    _RetryWorker.created.clear()
    started = []
    workspace = MediaWorkspace.__new__(MediaWorkspace)
    workspace.audio_analysis_panel = SimpleNamespace(refresh=lambda: None)
    window = SimpleNamespace(
        _console_append=lambda _message: None,
        console_text=SimpleNamespace(append=lambda _message: None),
        media_table_controller=SimpleNamespace(
            _refresh_media_table_debounced=lambda: None,
        ),
        worker_dispatcher=SimpleNamespace(
            _start_worker_thread=lambda worker: started.append(worker),
        ),
    )

    workspace._dispatch_audio_analysis(window, 7, "Track", step_key)

    assert _RetryWorker.created == [
        (7, "C:/isolated/audio.wav", (step_key,)),
    ]
    assert len(started) == 1
    assert started[0].task_id == "retry-task"
