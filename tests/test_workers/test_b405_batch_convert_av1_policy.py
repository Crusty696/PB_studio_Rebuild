from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from workers.import_export import BatchConvertWorker


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_b405_batch_convert_rejects_av1_on_gtx1060_target(tmp_path, monkeypatch):
    _ensure_qapp()

    ffmpeg_calls: list[list[str]] = []

    class FakeProcess:
        returncode = 0

        def __init__(self, cmd, **_kwargs):
            ffmpeg_calls.append(cmd)

        def poll(self):
            return self.returncode

        def communicate(self, timeout=None):
            return b"", b""

    monkeypatch.setattr("workers.import_export.subprocess.Popen", FakeProcess)

    fake_video_path = tmp_path / "input.mp4"
    fake_video_path.write_bytes(b"fake")
    worker = BatchConvertWorker(
        [{"file_path": str(fake_video_path)}],
        resolution="1920x1080",
        fps="30",
        vcodec="libaom-av1",
        ext=".mkv",
    )

    errors: list[str] = []
    finished: list[tuple[int, int]] = []
    worker.error.connect(errors.append)
    worker.finished.connect(lambda converted, total: finished.append((converted, total)))

    worker.run()

    assert ffmpeg_calls == []
    assert len(errors) == 1
    assert "libaom-av1" in errors[0]
    assert finished == []
