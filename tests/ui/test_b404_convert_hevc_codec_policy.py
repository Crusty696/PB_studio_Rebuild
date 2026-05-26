from __future__ import annotations

from types import SimpleNamespace


class _FakeSignal:
    def connect(self, *args, **kwargs):
        pass


class _FakeProgress:
    def setVisible(self, _visible):
        pass

    def setRange(self, _minimum, _maximum):
        pass

    def setValue(self, _value):
        pass


def test_b404_hevc_ui_selects_nvenc_codec(monkeypatch):
    from ui.controllers import convert

    monkeypatch.setattr("services.ingest_service.get_all_video", lambda: [{"file_path": "clip.mp4"}])
    monkeypatch.setattr(
        convert,
        "task_manager",
        SimpleNamespace(create_task=lambda *_args, **_kwargs: SimpleNamespace(task_id="t1")),
    )

    captured: dict[str, str] = {}

    class _FakeWorker:
        def __init__(self, _videos, _resolution, _fps, vcodec, ext):
            captured["vcodec"] = vcodec
            captured["ext"] = ext
            self.progress = _FakeSignal()
            self.finished = _FakeSignal()
            self.error = _FakeSignal()

    monkeypatch.setattr(convert, "BatchConvertWorker", _FakeWorker)

    window = SimpleNamespace(
        convert_log=SimpleNamespace(append=lambda _msg: None),
        convert_resolution=SimpleNamespace(currentText=lambda: "1920x1080 HD"),
        convert_fps=SimpleNamespace(currentText=lambda: "30 fps"),
        convert_format=SimpleNamespace(currentText=lambda: "H.265 / HEVC mp4"),
        convert_progress=_FakeProgress(),
        worker_dispatcher=SimpleNamespace(_start_worker_thread=lambda _worker: None),
    )
    controller = SimpleNamespace(window=window)

    convert.ConvertController._standardize_all_videos(controller)

    assert captured == {"vcodec": "hevc_nvenc", "ext": ".mp4"}
