import logging

from services.convert_service import _run_ffmpeg_with_progress


class _FakePipe:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)


class _FakeProcess:
    def __init__(self, stdout_lines: list[str]) -> None:
        self.stdout = _FakePipe(stdout_lines)
        self.stderr = _FakePipe([])
        self.returncode = 0
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9


def _patch_popen(monkeypatch, stdout_lines: list[str]) -> _FakeProcess:
    proc = _FakeProcess(stdout_lines)
    monkeypatch.setattr("services.convert_service.subprocess.Popen", lambda *a, **kw: proc)
    return proc


def test_ffmpeg_progress_ignores_initial_out_time_ms_na(monkeypatch, caplog) -> None:
    _patch_popen(monkeypatch, ["out_time_ms=N/A\n", "progress=end\n"])
    progress: list[tuple[int, str]] = []

    with caplog.at_level(logging.WARNING, logger="services.convert_service"):
        _run_ffmpeg_with_progress(
            ["ffmpeg"],
            total_duration=10.0,
            progress_cb=lambda pct, msg: progress.append((pct, msg)),
            timeout=5,
        )

    assert "Parsing FFmpeg out_time_ms progress" not in caplog.text
    assert progress == [(100, "Fertig")]


def test_ffmpeg_progress_keeps_warning_for_invalid_out_time_ms(monkeypatch, caplog) -> None:
    _patch_popen(monkeypatch, ["out_time_ms=not-an-int\n", "progress=end\n"])

    with caplog.at_level(logging.WARNING, logger="services.convert_service"):
        _run_ffmpeg_with_progress(
            ["ffmpeg"],
            total_duration=10.0,
            progress_cb=lambda _pct, _msg: None,
            timeout=5,
        )

    assert "Parsing FFmpeg out_time_ms progress" in caplog.text


def test_ffmpeg_progress_parses_valid_out_time_ms(monkeypatch) -> None:
    _patch_popen(monkeypatch, ["out_time_ms=5000000\n", "progress=end\n"])
    progress: list[tuple[int, str]] = []

    _run_ffmpeg_with_progress(
        ["ffmpeg"],
        total_duration=10.0,
        progress_cb=lambda pct, msg: progress.append((pct, msg)),
        timeout=5,
    )

    assert progress == [(50, "50%"), (100, "Fertig")]
