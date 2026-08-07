"""B-751: Audio-V2 Cancel/Error darf keinen Batch-Erfolg melden."""

from __future__ import annotations

from types import SimpleNamespace


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


def _controller():
    from ui.controllers.audio_analysis import AudioAnalysisController

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
    ctrl = AudioAnalysisController.__new__(AudioAnalysisController)
    ctrl.window = window
    ctrl._v2_queue = [(2, "next.wav", "next")]
    ctrl._v2_total = 2
    ctrl._v2_done = 1
    ctrl._seq_running = True
    return ctrl, console, button, progress


def test_user_cancel_stops_batch_without_success_text(monkeypatch):
    from ui.controllers import audio_analysis as module

    ctrl, console, button, progress = _controller()
    monkeypatch.setattr(
        module,
        "task_manager",
        SimpleNamespace(get_task=lambda _task_id: SimpleNamespace(status="cancelled")),
    )

    ctrl._v2_handle_error("task-1", 1, "AV-Pacing abgebrochen (User-Cancel)")

    assert ctrl._v2_queue == []
    assert ctrl._v2_done == 1
    assert ctrl._seq_running is False
    assert button.enabled is True
    assert progress.visible is False
    assert any("Abgebrochen: 1/2" in line for line in console.messages)
    assert not any("Fertig:" in line for line in console.messages)


def test_product_error_stops_batch_without_success_text(monkeypatch):
    from ui.controllers import audio_analysis as module

    ctrl, console, _button, _progress = _controller()
    monkeypatch.setattr(
        module,
        "task_manager",
        SimpleNamespace(get_task=lambda _task_id: SimpleNamespace(status="running")),
    )

    ctrl._v2_handle_error("task-2", 1, "echter Decoderfehler")

    assert ctrl._v2_queue == []
    assert ctrl._v2_done == 1
    assert ctrl._seq_running is False
    assert any("Fehlgeschlagen: 1/2" in line for line in console.messages)
    assert not any("Fertig:" in line for line in console.messages)
