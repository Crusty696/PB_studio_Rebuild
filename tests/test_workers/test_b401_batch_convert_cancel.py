from __future__ import annotations

import os
import subprocess
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from workers.import_export import BatchConvertWorker


def _ensure_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_b401_batch_convert_cancel_stops_running_ffmpeg(tmp_path, monkeypatch):
    _ensure_qapp()

    fake_video_path = tmp_path / "input.mp4"
    fake_video_path.write_bytes(b"fake")
    worker = BatchConvertWorker(
        [{"file_path": str(fake_video_path)}],
        resolution="1920x1080",
        fps="30",
        vcodec="libx264",
        ext=".mp4",
    )

    started = threading.Event()
    release = threading.Event()

    def fake_run(cmd, **kwargs):
        started.set()
        release.wait(timeout=5.0)
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    class FakeProcess:
        returncode = None

        def __init__(self, cmd, **kwargs):
            self.cmd = cmd
            started.set()

        def poll(self):
            if release.is_set():
                self.returncode = 0
            return self.returncode

        def terminate(self):
            self.returncode = -15
            release.set()

        def kill(self):
            self.returncode = -9
            release.set()

        def wait(self, timeout=None):
            release.wait(timeout=timeout)
            if self.returncode is None:
                self.returncode = 0
            return self.returncode

        def communicate(self, timeout=None):
            release.wait(timeout=timeout)
            if self.returncode is None:
                self.returncode = 0
            return b"", b""

    monkeypatch.setattr("workers.import_export.subprocess.run", fake_run)
    monkeypatch.setattr("workers.import_export.subprocess.Popen", FakeProcess)

    thread = threading.Thread(target=worker.run)
    thread.start()
    assert started.wait(timeout=1.0)

    try:
        worker.cancel()
        thread.join(timeout=0.5)
        assert not thread.is_alive(), "BatchConvertWorker did not stop running FFmpeg after cancel"
    finally:
        release.set()
        thread.join(timeout=2.0)
