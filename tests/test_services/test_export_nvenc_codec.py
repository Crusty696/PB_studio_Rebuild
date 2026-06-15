"""F-7 (B-339): export re-encode prefers NVENC, falls back to libx264."""
from __future__ import annotations

import importlib

import pytest

import services.export_service as es


def _reset_cache():
    es._export_nvenc_available = None


def test_video_encode_args_uses_nvenc_when_available(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(
        "services.convert_service.detect_nvenc",
        lambda: {"h264_nvenc": True, "hevc_nvenc": True},
    )
    args = es._video_encode_args()
    assert args[:2] == ["-c:v", "h264_nvenc"]
    assert "-cq" in args  # nvenc rate-control, not libx264 -crf
    _reset_cache()


def test_video_encode_args_falls_back_to_libx264(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(
        "services.convert_service.detect_nvenc",
        lambda: {"h264_nvenc": False, "hevc_nvenc": False},
    )
    args = es._video_encode_args()
    assert args == ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]
    _reset_cache()


def test_video_encode_args_falls_back_on_detect_error(monkeypatch):
    _reset_cache()
    def _boom():
        raise RuntimeError("ffmpeg missing")
    monkeypatch.setattr("services.convert_service.detect_nvenc", _boom)
    args = es._video_encode_args()
    assert args[1] == "libx264"
    _reset_cache()


def test_video_encode_args_strict_nvenc_blocks_cpu_fallback(monkeypatch):
    _reset_cache()
    monkeypatch.setenv("PB_REQUIRE_NVENC", "1")
    monkeypatch.setattr(
        "services.convert_service.detect_nvenc",
        lambda: {"h264_nvenc": False, "hevc_nvenc": False},
    )

    with pytest.raises(RuntimeError, match="NVENC_REQUIRED_FAILED"):
        es._video_encode_args()
    _reset_cache()


def test_convert_strict_nvenc_blocks_cpu_fallback(monkeypatch, tmp_path):
    from services.convert_service import convert
    from services.errors import ConversionError

    src = tmp_path / "input.mp4"
    src.write_bytes(b"not a real video; strict fails before ffmpeg run")
    monkeypatch.setenv("PB_REQUIRE_NVENC", "1")
    monkeypatch.setattr(
        "services.convert_service.detect_nvenc",
        lambda: {"h264_nvenc": False, "hevc_nvenc": False, "cuda_hwaccel": False},
    )

    with pytest.raises(ConversionError, match="NVENC_REQUIRED_FAILED"):
        convert(src, preset_name="edit_proxy", output_path=tmp_path / "out.mp4")


def test_run_ffmpeg_serializes_only_nvenc(monkeypatch):
    """Befund 1: NVENC-Encodes laufen unter dem gpu_serializer (Pascal-Session-
    Limit), libx264 (CPU) NICHT."""
    from contextlib import contextmanager

    calls = {"acquired": 0, "impl": 0}

    class _FakeSerializer:
        @contextmanager
        def acquire(self, holder):
            calls["acquired"] += 1
            yield

    monkeypatch.setattr(
        "services.brain_v3.gpu_serializer.get_default_serializer",
        lambda: _FakeSerializer(),
    )
    monkeypatch.setattr(
        es, "_run_ffmpeg_impl",
        lambda *a, **k: calls.__setitem__("impl", calls["impl"] + 1),
    )

    es._run_ffmpeg(["ffmpeg", "-c:v", "h264_nvenc", "out.mp4"])
    assert calls["acquired"] == 1 and calls["impl"] == 1

    es._run_ffmpeg(["ffmpeg", "-c:v", "libx264", "out.mp4"])
    assert calls["acquired"] == 1  # libx264 holt KEINEN GPU-Lock
    assert calls["impl"] == 2


def test_preprocess_segment_uses_video_encode_args(monkeypatch, tmp_path):
    """B-339: Preprocess darf keinen hardcodierten libx264-Command bauen."""
    commands = []
    source = tmp_path / "source.mp4"
    source.write_bytes(b"dummy")

    monkeypatch.setattr(
        es,
        "_video_encode_args",
        lambda: ["-c:v", "h264_nvenc", "-preset", "p4"],
    )
    monkeypatch.setattr(
        es,
        "_run_ffmpeg",
        lambda cmd, **kwargs: commands.append(cmd),
    )

    temp_files = []
    es._preprocess_segment(
        {
            "path": str(source),
            "start": 0.0,
            "end": 1.0,
            "source_start": 0.0,
            "source_duration": 1.0,
        },
        index=1,
        w="1920",
        h="1080",
        fps=30.0,
        temp_files=temp_files,
    )

    assert commands
    assert "-c:v" in commands[0]
    assert commands[0][commands[0].index("-c:v") + 1] == "h264_nvenc"
    assert "libx264" not in commands[0]
