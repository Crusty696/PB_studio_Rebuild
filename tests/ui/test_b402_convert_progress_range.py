from __future__ import annotations

from types import SimpleNamespace


class _FakeSignal:
    def __init__(self):
        self.connected = []

    def connect(self, slot, *args, **kwargs):
        self.connected.append(slot)


class _FakeProgress:
    def __init__(self):
        self.visible = False
        self.range = None
        self.value = None

    def setVisible(self, visible):
        self.visible = visible

    def setRange(self, minimum, maximum):
        self.range = (minimum, maximum)

    def setValue(self, value):
        self.value = value


def test_b402_convert_progress_range_matches_worker_percent(monkeypatch):
    from ui.controllers import convert

    videos = [{"file_path": f"clip_{i}.mp4"} for i in range(3)]
    monkeypatch.setattr("services.ingest_service.get_all_video", lambda: videos)
    monkeypatch.setattr(
        convert,
        "task_manager",
        SimpleNamespace(create_task=lambda *_args, **_kwargs: SimpleNamespace(task_id="t1")),
    )

    class _FakeWorker:
        def __init__(self, *args, **kwargs):
            self.progress = _FakeSignal()
            self.finished = _FakeSignal()
            self.error = _FakeSignal()

    monkeypatch.setattr(convert, "BatchConvertWorker", _FakeWorker)

    progress = _FakeProgress()
    window = SimpleNamespace(
        convert_log=SimpleNamespace(append=lambda _msg: None),
        convert_resolution=SimpleNamespace(currentText=lambda: "1920x1080 HD"),
        convert_fps=SimpleNamespace(currentText=lambda: "30 fps"),
        convert_format=SimpleNamespace(currentText=lambda: "H.264 mp4"),
        convert_progress=progress,
        worker_dispatcher=SimpleNamespace(_start_worker_thread=lambda _worker: None),
    )
    controller = SimpleNamespace(window=window)

    # B-525: Ziel-Format kommt jetzt aus dem modalen Dialog; der Convert-Start
    # (inkl. Progress-Range) wird ueber _run_standardize(res, fps, fmt) getestet.
    convert.ConvertController._run_standardize(
        controller, "1920x1080 HD", "30 fps", "H.264 mp4"
    )

    assert progress.range == (0, 100)
    assert progress.value == 0
