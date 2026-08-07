"""B-753: Pre-Start-Cancel muss Worker und Batch terminalisieren."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QThread, Qt


class _Recorder:
    def __init__(self):
        self.messages: list[str] = []

    def append(self, message: str) -> None:
        self.messages.append(message)


class _Widget:
    def __init__(self):
        self.enabled = None
        self.text = None
        self.visible = None

    def setEnabled(self, value):  # noqa: N802
        self.enabled = value

    def setText(self, value):  # noqa: N802
        self.text = value

    def setVisible(self, value):  # noqa: N802
        self.visible = value


def test_prestart_cancel_signal_finalizes_audio_v2_batch(monkeypatch, qapp):
    from ui.controllers import audio_analysis as module
    from ui.controllers.audio_analysis import AudioAnalysisController
    from workers.audio_pipeline_v2_worker import AudioPipelineV2Worker

    console = _Recorder()
    button = _Widget()
    progress = _Widget()
    window = SimpleNamespace(
        console_text=console,
        _console_append=console.append,
        progress_bar=progress,
        _media_ws=SimpleNamespace(btn_analyze_all=button),
        media_table_controller=SimpleNamespace(
            _refresh_media_table_debounced=lambda: None,
        ),
    )
    controller = AudioAnalysisController.__new__(AudioAnalysisController)
    controller.window = window
    controller._v2_queue = [(8, "next.wav", "next")]
    controller._v2_total = 2
    controller._v2_done = 1
    controller._seq_running = True
    monkeypatch.setattr(
        module,
        "task_manager",
        SimpleNamespace(get_task=lambda _task_id: SimpleNamespace(status="cancelled")),
    )

    worker = AudioPipelineV2Worker(audio_track_id=7, file_path="/x.wav")
    worker.error.connect(
        lambda track_id, message: controller._v2_handle_error(
            "task-prestart", track_id, message
        )
    )
    worker.cancel()
    worker.run()

    assert controller._v2_queue == []
    assert controller._v2_done == 1
    assert controller._seq_running is False
    assert button.enabled is True
    assert progress.visible is False
    assert any("Abgebrochen: 1/2" in line for line in console.messages)
    assert not any("Fertig:" in line for line in console.messages)


def test_prestart_cancel_terminates_real_qthread(qapp):
    from workers.audio_pipeline_v2_worker import AudioPipelineV2Worker

    thread = QThread()
    worker = AudioPipelineV2Worker(audio_track_id=7, file_path="/x.wav")
    terminal: list[tuple[int, str]] = []
    worker.moveToThread(thread)
    worker.cancel()
    worker.error.connect(
        lambda track_id, message: terminal.append((track_id, message)),
        Qt.ConnectionType.DirectConnection,
    )
    worker.error.connect(thread.quit, Qt.ConnectionType.DirectConnection)
    thread.started.connect(worker.run)

    thread.start()
    assert thread.wait(2_000)
    assert thread.isRunning() is False
    assert terminal == [
        (7, "Audio-V2 Pipeline abgebrochen (User-Cancel vor Start)")
    ]
