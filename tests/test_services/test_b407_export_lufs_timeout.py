from __future__ import annotations

import subprocess

import pytest


def test_b407_lufs_subprocess_timeout_is_raised(monkeypatch):
    from services import export_service

    class FakeProcess:
        returncode = -9
        stdout = None
        stderr = None

        def __init__(self, *_args, **_kwargs):
            self.killed = False

        def poll(self):
            return self.returncode if self.killed else None

        def kill(self):
            self.killed = True

        def communicate(self, timeout=None):
            if not self.killed:
                raise subprocess.TimeoutExpired(["ffmpeg"], timeout)
            return "", "timed out"

    monkeypatch.setattr("services.export_service.subprocess.Popen", FakeProcess)

    with pytest.raises(subprocess.TimeoutExpired):
        export_service._run_subprocess_cancellable(
            ["ffmpeg"],
            timeout=1,
            progress_cb=lambda _pct, _msg: None,
        )


def test_b407_lufs_normalize_timeout_is_hard_error(monkeypatch):
    from services import export_service

    def raise_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(["ffmpeg"], 1)

    monkeypatch.setattr(export_service, "_run_subprocess_cancellable", raise_timeout)

    with pytest.raises(RuntimeError, match="LUFS.*Timeout"):
        export_service._normalize_audio_lufs("input.wav", "output.wav")
