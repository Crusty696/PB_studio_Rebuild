import subprocess

import pytest


class _NeverEndingProc:
    returncode = None

    def __init__(self, *args, **kwargs):
        self.killed = False
        self.waited = False

    def poll(self):
        return None

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.waited = True
        return 1

    def communicate(self):
        return "", ""


def test_create_proxy_timeout_kills_waits_then_raises_clear_timeout(monkeypatch, tmp_path):
    import services.video_service as video_service
    from services.video_service import VideoAnalyzer

    src = tmp_path / "input.mp4"
    src.write_bytes(b"not a real video")
    proxy_dir = tmp_path / "proxies"
    created = []

    def _factory(*args, **kwargs):
        proc = _NeverEndingProc()
        created.append(proc)
        return proc

    monkeypatch.setattr(video_service, "_proxy_dir", lambda: proxy_dir)
    monkeypatch.setattr(video_service.subprocess, "Popen", _factory)
    monkeypatch.setattr(video_service, "FFMPEG_RENDER_TIMEOUT_SEC", -1)

    analyzer = VideoAnalyzer()

    with pytest.raises(subprocess.TimeoutExpired):
        analyzer.create_proxy(str(src))

    assert created
    assert created[0].killed is True
    assert created[0].waited is True
