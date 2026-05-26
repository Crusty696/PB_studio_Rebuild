from __future__ import annotations

from pathlib import Path


def test_b406_video_analyzer_create_proxy_uses_nvenc_codec(tmp_path, monkeypatch):
    from services.video_service import VideoAnalyzer

    proxy_dir = tmp_path / "proxies"
    captured_cmds: list[list[str]] = []

    class FakeProcess:
        returncode = 0

        def __init__(self, cmd, **_kwargs):
            captured_cmds.append(cmd)
            Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(cmd[-1]).write_bytes(b"proxy")

        def poll(self):
            return self.returncode

        def communicate(self):
            return "", ""

    monkeypatch.setattr("services.video_service._proxy_dir", lambda: proxy_dir)
    monkeypatch.setattr("services.video_service.subprocess.Popen", FakeProcess)

    src = tmp_path / "input.mp4"
    src.write_bytes(b"video")

    result = VideoAnalyzer().create_proxy(str(src), target_height=540)

    assert result == str((proxy_dir / "input_proxy.mp4").resolve())
    assert captured_cmds
    cmd = captured_cmds[0]
    codec_index = cmd.index("-c:v") + 1
    assert cmd[codec_index] == "h264_nvenc"
