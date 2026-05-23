"""F-7 (B-339): export re-encode prefers NVENC, falls back to libx264."""
from __future__ import annotations

import importlib

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
