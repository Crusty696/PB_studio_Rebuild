"""B-505: Proxy-NVENC-Encodes unter GpuSerializer + CPU-Fallback.

Deckt ab:
1. ``VideoAnalyzer.create_proxy``: NVENC-Encode laeuft INNERHALB von
   ``get_default_serializer().acquire(...)`` (Lock nur um den
   Subprocess-Lauf); FFmpeg-Fehler mit NVENC-Signatur
   (OpenEncodeSessionEx / nvcuda) → genau ein libx264-Retry
   (``-preset veryfast``, ohne GPU-Lock); fremde FFmpeg-Fehler → kein
   Retry.
2. ``proxy_generator._try_encode``: NVENC unter Serializer, libx264 ohne;
   ``generate_proxy(codec="auto")``: TimeoutExpired des NVENC-Versuchs
   → CPU-Fallback statt Abbruch.
"""
from __future__ import annotations

import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest


class SerializerSpy:
    """Mock-GpuSerializer: zaehlt acquire-Eintritte + aktive Halter."""

    def __init__(self):
        self.holders: list[str] = []
        self.active = 0

    @contextmanager
    def acquire(self, holder: str = "anonymous"):
        self.holders.append(holder)
        self.active += 1
        try:
            yield
        finally:
            self.active -= 1


@pytest.fixture
def serializer_spy(monkeypatch):
    import services.brain.gpu_serializer as gs
    spy = SerializerSpy()
    monkeypatch.setattr(gs, "get_default_serializer", lambda: spy)
    return spy


# ---------------------------------------------------------------------------
# VideoAnalyzer.create_proxy
# ---------------------------------------------------------------------------

def _install_fake_popen(monkeypatch, spy, script):
    """``script``: Liste von (returncode, stderr_text, create_output).

    Jeder Popen-Aufruf konsumiert den naechsten Eintrag. Captured:
    Liste von (cmd, spy.active-zum-Startzeitpunkt).
    """
    captured: list[tuple[list, int]] = []

    class FakeProcess:
        def __init__(self, cmd, **kwargs):
            rc, stderr_text, create_output = script[len(captured)]
            captured.append((cmd, spy.active))
            self.returncode = rc
            stderr_file = kwargs.get("stderr")
            if stderr_file is not None and stderr_text:
                stderr_file.write(stderr_text)
            if create_output:
                Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
                Path(cmd[-1]).write_bytes(b"proxy")

        def poll(self):
            return self.returncode

        def communicate(self):
            return "", ""

    monkeypatch.setattr("services.video_service.subprocess.Popen", FakeProcess)
    return captured


def test_create_proxy_nvenc_runs_under_serializer(tmp_path, monkeypatch, serializer_spy):
    from services.video_service import VideoAnalyzer

    monkeypatch.setattr("services.video_service._proxy_dir", lambda: tmp_path / "proxies")
    captured = _install_fake_popen(monkeypatch, serializer_spy, [(0, "", True)])

    src = tmp_path / "input.mp4"
    src.write_bytes(b"video")
    result = VideoAnalyzer().create_proxy(str(src), target_height=480)

    assert Path(result).exists()
    assert serializer_spy.holders == ["proxy_encode"]
    cmd, active_at_start = captured[0]
    assert cmd[cmd.index("-c:v") + 1] == "h264_nvenc"
    # Lock-Granularitaet: Subprocess startet WAEHREND der Lock gehalten wird
    assert active_at_start == 1


def test_create_proxy_nvenc_failure_falls_back_to_libx264(
        tmp_path, monkeypatch, serializer_spy):
    from services.video_service import VideoAnalyzer

    monkeypatch.setattr("services.video_service._proxy_dir", lambda: tmp_path / "proxies")
    captured = _install_fake_popen(monkeypatch, serializer_spy, [
        (1, "OpenEncodeSessionEx failed: out of memory (10): (no details)", False),
        (0, "", True),
    ])

    src = tmp_path / "input.mp4"
    src.write_bytes(b"video")
    result = VideoAnalyzer().create_proxy(str(src), target_height=480)

    assert Path(result).exists()
    assert len(captured) == 2
    nvenc_cmd, nvenc_active = captured[0]
    cpu_cmd, cpu_active = captured[1]
    assert nvenc_cmd[nvenc_cmd.index("-c:v") + 1] == "h264_nvenc"
    assert nvenc_active == 1
    assert cpu_cmd[cpu_cmd.index("-c:v") + 1] == "libx264"
    assert cpu_cmd[cpu_cmd.index("-preset") + 1] == "veryfast"
    # CPU-Retry laeuft OHNE GPU-Lock
    assert cpu_active == 0
    # Serializer wurde genau einmal betreten (nur NVENC)
    assert serializer_spy.holders == ["proxy_encode"]


def test_create_proxy_strict_nvenc_blocks_cpu_retry(
        tmp_path, monkeypatch, serializer_spy):
    from services.errors import FFmpegError
    from services.video_service import VideoAnalyzer

    monkeypatch.setenv("PB_REQUIRE_NVENC", "1")
    monkeypatch.setattr("services.video_service._proxy_dir", lambda: tmp_path / "proxies")
    captured = _install_fake_popen(monkeypatch, serializer_spy, [
        (1, "OpenEncodeSessionEx failed: out of memory (10): (no details)", False),
    ])

    src = tmp_path / "input.mp4"
    src.write_bytes(b"video")
    with pytest.raises(FFmpegError):
        VideoAnalyzer().create_proxy(str(src), target_height=480)

    assert len(captured) == 1
    assert captured[0][0][captured[0][0].index("-c:v") + 1] == "h264_nvenc"


def test_create_proxy_nvcuda_signature_triggers_fallback(
        tmp_path, monkeypatch, serializer_spy):
    from services.video_service import VideoAnalyzer

    monkeypatch.setattr("services.video_service._proxy_dir", lambda: tmp_path / "proxies")
    captured = _install_fake_popen(monkeypatch, serializer_spy, [
        (1, "Cannot load nvcuda.dll", False),
        (0, "", True),
    ])

    src = tmp_path / "input.mp4"
    src.write_bytes(b"video")
    VideoAnalyzer().create_proxy(str(src), target_height=480)

    assert len(captured) == 2
    assert captured[1][0][captured[1][0].index("-c:v") + 1] == "libx264"


def test_create_proxy_non_nvenc_error_no_retry(tmp_path, monkeypatch, serializer_spy):
    from services.errors import FFmpegError
    from services.video_service import VideoAnalyzer

    monkeypatch.setattr("services.video_service._proxy_dir", lambda: tmp_path / "proxies")
    captured = _install_fake_popen(monkeypatch, serializer_spy, [
        (1, "Invalid data found when processing input", False),
    ])

    src = tmp_path / "input.mp4"
    src.write_bytes(b"video")
    with pytest.raises(FFmpegError):
        VideoAnalyzer().create_proxy(str(src), target_height=480)

    # Kein libx264-Retry bei nicht-NVENC-Fehler (kaputte Quelle scheitert
    # auf CPU genauso)
    assert len(captured) == 1


def test_is_nvenc_failure_signatures():
    from services.video_service import _is_nvenc_failure

    assert _is_nvenc_failure("OpenEncodeSessionEx failed: out of memory") is True
    assert _is_nvenc_failure("Cannot load nvcuda.dll") is True
    assert _is_nvenc_failure("No NVENC capable devices found") is True
    assert _is_nvenc_failure("Invalid data found when processing input") is False
    assert _is_nvenc_failure("") is False
    assert _is_nvenc_failure(None) is False


# ---------------------------------------------------------------------------
# proxy_generator
# ---------------------------------------------------------------------------

def test_try_encode_nvenc_under_serializer(tmp_path, monkeypatch, serializer_spy):
    import services.video_pipeline.primitives.proxy_generator as pg

    monkeypatch.setattr(pg, "_ffmpeg", lambda: "ffmpeg")
    seen = []

    def fake_run(cmd, **kwargs):
        seen.append((cmd[cmd.index("-c:v") + 1], serializer_spy.active))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(pg.subprocess, "run", fake_run)

    assert pg._try_encode(tmp_path / "a.mp4", tmp_path / "b.mp4", 960, "3M",
                          "h264_nvenc") is True
    assert pg._try_encode(tmp_path / "a.mp4", tmp_path / "b.mp4", 960, "3M",
                          "libx264") is True

    assert seen[0] == ("h264_nvenc", 1)   # NVENC: Lock gehalten
    assert seen[1] == ("libx264", 0)      # CPU: kein Lock
    assert serializer_spy.holders == ["proxy_gen"]


def test_generate_proxy_auto_timeout_falls_back_to_cpu(
        tmp_path, monkeypatch, serializer_spy):
    import services.video_pipeline.primitives.proxy_generator as pg

    monkeypatch.setattr(pg, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(pg, "_has_nvenc", lambda: True)
    codecs = []

    def fake_run(cmd, **kwargs):
        codec = cmd[cmd.index("-c:v") + 1]
        codecs.append(codec)
        if codec == "h264_nvenc":
            raise subprocess.TimeoutExpired(cmd, 300)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(pg.subprocess, "run", fake_run)

    src = tmp_path / "src.mp4"
    src.write_bytes(b"video")
    dst = tmp_path / "out" / "proxy.mp4"

    result = pg.generate_proxy(src, dst, codec="auto")

    assert result == dst
    assert codecs == ["h264_nvenc", "libx264"]


def test_generate_proxy_auto_nvenc_failure_falls_back_to_cpu(
        tmp_path, monkeypatch, serializer_spy):
    import services.video_pipeline.primitives.proxy_generator as pg

    monkeypatch.setattr(pg, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(pg, "_has_nvenc", lambda: True)
    codecs = []

    def fake_run(cmd, **kwargs):
        codec = cmd[cmd.index("-c:v") + 1]
        codecs.append(codec)
        rc = 1 if codec == "h264_nvenc" else 0
        return SimpleNamespace(returncode=rc)

    monkeypatch.setattr(pg.subprocess, "run", fake_run)

    src = tmp_path / "src.mp4"
    src.write_bytes(b"video")
    dst = tmp_path / "out" / "proxy.mp4"

    result = pg.generate_proxy(src, dst, codec="auto")

    assert result == dst
    assert codecs == ["h264_nvenc", "libx264"]


def test_generate_proxy_auto_strict_nvenc_blocks_cpu_fallback(
        tmp_path, monkeypatch, serializer_spy):
    import services.video_pipeline.primitives.proxy_generator as pg

    monkeypatch.setenv("PB_REQUIRE_NVENC", "1")
    monkeypatch.setattr(pg, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(pg, "_has_nvenc", lambda: True)
    codecs = []

    def fake_run(cmd, **kwargs):
        codec = cmd[cmd.index("-c:v") + 1]
        codecs.append(codec)
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(pg.subprocess, "run", fake_run)

    src = tmp_path / "src.mp4"
    src.write_bytes(b"video")
    dst = tmp_path / "out" / "proxy.mp4"

    with pytest.raises(RuntimeError, match="NVENC_REQUIRED_FAILED"):
        pg.generate_proxy(src, dst, codec="auto")

    assert codecs == ["h264_nvenc"]
