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


def test_b403_batch_convert_uses_configured_ffmpeg_binary(tmp_path, monkeypatch):
    _ensure_qapp()

    configured_ffmpeg = str(tmp_path / "configured_ffmpeg.exe")
    monkeypatch.setattr("workers.import_export.get_ffmpeg_bin", lambda: configured_ffmpeg)

    captured_cmds: list[list[str]] = []

    class FakeProcess:
        returncode = 0

        def __init__(self, cmd, **kwargs):
            captured_cmds.append(cmd)

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
        vcodec="libx264",
        ext=".mp4",
    )

    worker.run()

    assert captured_cmds
    # B-402: Vor dem Convert laeuft jetzt ein ffprobe-Dauer-Probe-Call. Der
    # eigentliche Convert-Befehl muss weiterhin die konfigurierte ffmpeg-Binary
    # nutzen — irgendein captured cmd beginnt mit configured_ffmpeg.
    assert any(c[0] == configured_ffmpeg for c in captured_cmds), (
        f"Convert nutzte nicht die konfigurierte ffmpeg-Binary: "
        f"{[c[0] for c in captured_cmds]}"
    )
