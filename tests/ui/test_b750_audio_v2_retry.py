"""B-750: sichtbare optionale Audio-V2-Retries müssen Worker starten."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest


class _Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback, *_args, **_kwargs):
        self.callbacks.append(callback)
        return None

    def emit(self, *args):
        for callback in list(self.callbacks):
            callback(*args)


class _RetryWorker:
    created: list[tuple[int, str, tuple[str, ...]]] = []

    def __init__(self, audio_id, file_path, *, retry_step_keys=()):
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


def test_audio_retry_cancel_is_reported_as_cancel_not_error(monkeypatch):
    workspace, window, started, messages = _dispatch_fixture(monkeypatch)

    workspace._dispatch_audio_analysis(
        window, 7, "Track", "av_pacing_curves"
    )
    started[0].error.emit(7, "AV-Pacing abgebrochen (User-Cancel)")

    assert any("Abgebrochen" in message for message in messages)
    assert not any("Error:" in message for message in messages)


def test_duplicate_audio_v2_retry_is_single_flight(monkeypatch):
    workspace, window, started, messages = _dispatch_fixture(monkeypatch)

    workspace._dispatch_audio_analysis(window, 7, "Track", "onset_detection")
    workspace._dispatch_audio_analysis(window, 7, "Track", "onset_detection")

    assert len(started) == 1
    assert any("Bereits aktiv" in message for message in messages)


def test_retry_all_audio_dispatches_one_resumable_v2_worker(monkeypatch, qapp):
    from ui.widgets.analysis_status_panel import AnalysisStatusPanel

    panel = AnalysisStatusPanel()
    panel._refresh_generation = 3
    panel._media_type = "audio"
    panel._media_id = 7
    emitted = []
    panel.analysis_requested.connect(emitted.append)

    panel._emit_retry_steps(
        ["stem_separation", "onset_detection", "av_pacing_curves"],
        3,
        "audio",
        7,
    )

    assert emitted == ["audio_v2_retry_errors"]


def test_retry_all_key_dispatches_full_resumable_v2_worker(monkeypatch):
    workspace, window, started, _messages = _dispatch_fixture(monkeypatch)

    workspace._dispatch_audio_analysis(
        window, 7, "Track", "audio_v2_retry_errors"
    )

    assert _RetryWorker.created == [(7, "C:/isolated/audio.wav", ())]
    assert len(started) == 1


def test_cross_path_conflict_is_not_reported_as_new_start_or_error(monkeypatch):
    workspace, window, _started, messages = _dispatch_fixture(monkeypatch)

    def _reject(worker):
        worker._start_conflict = "Bereits aktiv: Audioanalyse für Track #7."
        worker.error.emit(7, worker._start_conflict)
        return None

    window.worker_dispatcher._start_worker_thread = _reject

    workspace._dispatch_audio_analysis(
        window, 7, "Track", "onset_detection"
    )

    assert any("Bereits aktiv" in message for message in messages)
    assert not any("Fehler:" in message for message in messages)
    assert not any("Starting analysis" in message for message in messages)


def test_single_v2_conflict_does_not_log_false_start(monkeypatch):
    import ui.controllers.audio_analysis as controller_module
    import workers.audio_pipeline_v2_worker as worker_module
    from ui.controllers.audio_analysis import AudioAnalysisController

    monkeypatch.setattr(worker_module, "AudioPipelineV2Worker", _RetryWorker)
    monkeypatch.setattr(
        controller_module,
        "task_manager",
        SimpleNamespace(
            create_task=lambda *_args: SimpleNamespace(task_id="v2-task")
        ),
    )
    messages = []

    def _reject(worker):
        worker._start_conflict = "Bereits aktiv: Audioanalyse für Track #7."
        worker.error.emit(7, worker._start_conflict)
        return None

    controller = AudioAnalysisController.__new__(AudioAnalysisController)
    controller.window = SimpleNamespace(
        progress_bar=SimpleNamespace(
            setVisible=lambda *_args: None,
            setRange=lambda *_args: None,
            setValue=lambda *_args: None,
            setFormat=lambda *_args: None,
        ),
        _console_append=messages.append,
        console_text=SimpleNamespace(append=messages.append),
        media_table_controller=SimpleNamespace(
            _refresh_media_table_debounced=lambda: None,
        ),
        worker_dispatcher=SimpleNamespace(_start_worker_thread=_reject),
    )
    monkeypatch.setattr(
        controller,
        "_get_selected_audio_track",
        lambda: (7, "C:/isolated/audio.wav", "Track", 128.0),
    )

    controller._analyze_audio_v2()

    assert any("Bereits aktiv" in message for message in messages)
    assert not any("Starte Pipeline" in message for message in messages)


def test_stem_conflict_does_not_log_false_start(monkeypatch):
    import ui.controllers.stems as stems_module
    from ui.controllers.stems import StemsController

    class _StemWorker:
        def __init__(self, track_id):
            self.track_id = track_id
            self.task_id = None
            self.progress = _Signal()
            self.finished = _Signal()
            self.error = _Signal()

    finished_tasks = []
    monkeypatch.setattr(stems_module, "StemSeparationWorker", _StemWorker)
    monkeypatch.setattr(
        stems_module,
        "_task_manager",
        SimpleNamespace(
            create_task=lambda *_args: SimpleNamespace(task_id="stem-task"),
            finish_task=lambda *args: finished_tasks.append(args),
        ),
    )
    messages = []

    def _reject(worker, **_kwargs):
        worker._start_conflict = "Bereits aktiv: Audioanalyse für Track #7."
        worker.error.emit(7, worker._start_conflict)
        return None

    controller = StemsController.__new__(StemsController)
    controller.window = SimpleNamespace(
        audio_analysis=SimpleNamespace(
            _get_selected_audio_track=lambda: (
                7,
                "C:/isolated/audio.wav",
                "Track",
                128.0,
            )
        ),
        btn_stem_separate=SimpleNamespace(
            setEnabled=lambda *_args: None,
            setText=lambda *_args: None,
        ),
        progress_bar=SimpleNamespace(
            setRange=lambda *_args: None,
            setValue=lambda *_args: None,
            setVisible=lambda *_args: None,
            setFormat=lambda *_args: None,
        ),
        console_text=SimpleNamespace(append=messages.append),
        worker_dispatcher=SimpleNamespace(_start_worker_thread=_reject),
    )

    controller._start_stem_separation()

    assert any("Bereits aktiv" in message for message in messages)
    assert not any("Starte KI-Stem-Separation" in message for message in messages)
    assert finished_tasks


def test_cross_path_claim_blocks_v2_and_stem_for_same_project_track(
    tmp_path, monkeypatch
):
    from database import session as db_session
    from ui.controllers.worker_dispatcher import (
        _release_worker_resources,
        _try_claim_worker_resources,
    )
    from workers import StemSeparationWorker
    from workers.audio_pipeline_v2_worker import AudioPipelineV2Worker

    project_a = tmp_path / "project-a"
    project_b = tmp_path / "project-b"
    monkeypatch.setattr(db_session, "APP_ROOT", project_a)
    full = AudioPipelineV2Worker(7, "C:/isolated/audio.wav")
    onset = AudioPipelineV2Worker(
        7, "C:/isolated/audio.wav", retry_step_keys=("onset_detection",)
    )
    av = AudioPipelineV2Worker(
        7, "C:/isolated/audio.wav", retry_step_keys=("av_pacing_curves",)
    )
    stem = StemSeparationWorker(7)
    other_track = AudioPipelineV2Worker(8, "C:/isolated/other.wav")

    try:
        assert _try_claim_worker_resources(full) is True
        assert _try_claim_worker_resources(onset) is False
        assert _try_claim_worker_resources(av) is False
        assert _try_claim_worker_resources(stem) is False
        assert _try_claim_worker_resources(other_track) is True

        monkeypatch.setattr(db_session, "APP_ROOT", project_b)
        same_id_other_project = AudioPipelineV2Worker(
            7, "C:/isolated/project-b.wav"
        )
        assert _try_claim_worker_resources(same_id_other_project) is True
    finally:
        for worker in (full, onset, av, stem, other_track):
            _release_worker_resources(worker)
        if "same_id_other_project" in locals():
            _release_worker_resources(same_id_other_project)


def test_av_retry_allows_independent_stem_resource(tmp_path, monkeypatch):
    from database import session as db_session
    from ui.controllers.worker_dispatcher import (
        _release_worker_resources,
        _try_claim_worker_resources,
    )
    from workers import StemSeparationWorker
    from workers.audio_pipeline_v2_worker import AudioPipelineV2Worker

    monkeypatch.setattr(db_session, "APP_ROOT", tmp_path / "project")
    av = AudioPipelineV2Worker(
        7, "C:/isolated/audio.wav", retry_step_keys=("av_pacing_curves",)
    )
    stem = StemSeparationWorker(7)
    full = AudioPipelineV2Worker(7, "C:/isolated/audio.wav")

    try:
        assert _try_claim_worker_resources(av) is True
        assert _try_claim_worker_resources(stem) is True
        assert _try_claim_worker_resources(full) is False
    finally:
        for worker in (av, stem, full):
            _release_worker_resources(worker)


def test_dispatcher_cleanup_releases_claim(tmp_path, monkeypatch):
    from database import session as db_session
    from ui.controllers.worker_dispatcher import (
        WorkerDispatcherController,
        _release_worker_resources,
        _try_claim_worker_resources,
    )
    from workers.audio_pipeline_v2_worker import AudioPipelineV2Worker

    monkeypatch.setattr(db_session, "APP_ROOT", tmp_path / "project")
    first = AudioPipelineV2Worker(7, "C:/isolated/audio.wav")
    second = AudioPipelineV2Worker(7, "C:/isolated/audio.wav")
    thread = object()
    controller = WorkerDispatcherController.__new__(WorkerDispatcherController)
    controller.window = SimpleNamespace(
        _active_workers=[first],
        _active_threads=[thread],
    )

    try:
        assert _try_claim_worker_resources(first) is True
        assert _try_claim_worker_resources(second) is False

        controller._cleanup_worker(thread, first)

        assert _try_claim_worker_resources(second) is True
    finally:
        _release_worker_resources(first)
        _release_worker_resources(second)


def test_dispatcher_rejects_conflict_before_thread_start(
    tmp_path, monkeypatch, qapp
):
    from database import session as db_session
    import ui.controllers.worker_dispatcher as dispatcher_module
    from ui.controllers.worker_dispatcher import (
        WorkerDispatcherController,
        _release_worker_resources,
        _try_claim_worker_resources,
    )
    from workers.audio_pipeline_v2_worker import AudioPipelineV2Worker

    monkeypatch.setattr(db_session, "APP_ROOT", tmp_path / "project")
    first = AudioPipelineV2Worker(7, "C:/isolated/audio.wav")
    second = AudioPipelineV2Worker(7, "C:/isolated/audio.wav")
    second.task_id = "conflicting-task"
    finished_tasks = []
    manager = SimpleNamespace(
        get_task=lambda task_id: SimpleNamespace(task_id=task_id),
        finish_task=lambda *args: finished_tasks.append(args),
    )
    monkeypatch.setattr(
        dispatcher_module.GlobalTaskManager,
        "instance",
        staticmethod(lambda: manager),
    )
    controller = WorkerDispatcherController.__new__(WorkerDispatcherController)
    controller.window = SimpleNamespace(_active_workers=[], _active_threads=[])
    errors = []
    second.error.connect(lambda track_id, message: errors.append((track_id, message)))

    try:
        assert _try_claim_worker_resources(first) is True

        result = controller._start_worker_thread(second)

        assert result is None
        assert "Bereits aktiv" in second._start_conflict
        assert errors == [(7, second._start_conflict)]
        assert finished_tasks == [
            ("conflicting-task", "error", second._start_conflict)
        ]
        assert controller.window._active_workers == []
        assert controller.window._active_threads == []
    finally:
        _release_worker_resources(first)
        _release_worker_resources(second)


def _dispatch_fixture(monkeypatch):
    import database
    import services.task_manager as task_manager_module
    import workers.audio_pipeline_v2_worker as worker_module
    from ui.workspaces.media_workspace import MediaWorkspace

    @contextmanager
    def _session():
        row = SimpleNamespace(first=lambda: ("C:/isolated/audio.wav", 128.0))
        yield SimpleNamespace(execute=lambda *_args, **_kwargs: row)

    manager = SimpleNamespace(
        create_task=lambda *_args: SimpleNamespace(task_id="retry-task")
    )
    monkeypatch.setattr(database, "nullpool_session", _session)
    monkeypatch.setattr(task_manager_module, "TaskManagerProxy", lambda: manager)
    monkeypatch.setattr(worker_module, "AudioPipelineV2Worker", _RetryWorker)
    _RetryWorker.created.clear()
    started = []
    messages = []
    workspace = MediaWorkspace.__new__(MediaWorkspace)
    workspace.audio_analysis_panel = SimpleNamespace(refresh=lambda: None)
    window = SimpleNamespace(
        _console_append=messages.append,
        console_text=SimpleNamespace(append=messages.append),
        media_table_controller=SimpleNamespace(
            _refresh_media_table_debounced=lambda: None,
        ),
        worker_dispatcher=SimpleNamespace(
            _start_worker_thread=lambda worker: started.append(worker),
        ),
    )
    return workspace, window, started, messages
