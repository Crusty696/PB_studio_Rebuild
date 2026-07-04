"""Regression tests for configured FFmpeg/FFprobe resolver usage.

No real FFmpeg/FFprobe process is started here. The tests patch
``subprocess.run`` and assert the command uses the configured resolver path.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtGui import QImage


def test_startup_checks_prefers_explicit_ffmpeg_env(monkeypatch):
    import services.startup_checks as startup_checks

    monkeypatch.setenv("PB_FFMPEG_EXE", r"C:\PB_Studio_H1_3\ffmpeg.exe")
    monkeypatch.setenv("PB_FFPROBE_EXE", r"C:\PB_Studio_H1_3\ffprobe.exe")

    assert startup_checks.get_ffmpeg_bin() == r"C:\PB_Studio_H1_3\ffmpeg.exe"
    assert startup_checks.get_ffprobe_bin() == r"C:\PB_Studio_H1_3\ffprobe.exe"


def test_frame_extract_worker_uses_configured_ffmpeg(monkeypatch):
    import workers.video as video_mod

    configured_ffmpeg = r"C:\PB-Studio-Bin\ffmpeg.exe"
    captured: dict[str, list[str]] = {}

    monkeypatch.setattr(
        video_mod,
        "get_ffmpeg_bin",
        lambda: configured_ffmpeg,
        raising=False,
    )

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=1, stdout=b"", stderr=b"mock stderr")

    monkeypatch.setattr(video_mod.subprocess, "run", fake_run)

    worker = video_mod.FrameExtractWorker(
        file_path=r"C:\media\clip.mp4",
        time_sec=1.0,
        width=2,
        height=2,
    )
    worker.run()

    assert captured["cmd"][0] == configured_ffmpeg


def test_media_grid_thumb_worker_uses_configured_ffmpeg(monkeypatch, tmp_path):
    import ui.widgets.media_grid as media_grid

    configured_ffmpeg = r"C:\PB-Studio-Bin\ffmpeg.exe"
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"fake video")
    thumb = tmp_path / "thumb.jpg"
    captured: dict[str, list[str]] = {}

    monkeypatch.setattr(
        media_grid,
        "get_ffmpeg_bin",
        lambda: configured_ffmpeg,
        raising=False,
    )
    monkeypatch.setattr(media_grid, "_ensure_thumb_dir", lambda: None)
    monkeypatch.setattr(media_grid, "_thumb_path", lambda _path: thumb)
    monkeypatch.setattr(
        media_grid,
        "_placeholder_image",
        lambda w, h, _icon="": QImage(w, h, QImage.Format.Format_ARGB32),
    )

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(media_grid.subprocess, "run", fake_run)

    worker = media_grid._ThumbWorker(str(source), 16, 9)
    worker._extract()

    assert captured["cmd"][0] == configured_ffmpeg


def test_ingest_probe_uses_configured_ffprobe(monkeypatch):
    import services.ingest_service as ingest_service

    configured_ffprobe = r"C:\PB-Studio-Bin\ffprobe.exe"
    captured: dict[str, list[str]] = {}

    monkeypatch.setattr(
        ingest_service,
        "get_ffprobe_bin",
        lambda: configured_ffprobe,
        raising=False,
    )

    payload = {
        "format": {"duration": "12.5"},
        "streams": [
            {
                "codec_type": "video",
                "r_frame_rate": "25/1",
                "width": 1920,
                "height": 1080,
                "codec_name": "h264",
            }
        ],
    }

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(ingest_service.subprocess, "run", fake_run, raising=False)

    meta = ingest_service._probe_video_meta(str(Path(r"C:\media\clip.mp4")))

    assert captured["cmd"][0] == configured_ffprobe
    assert meta["duration"] == 12.5
    assert meta["width"] == 1920


def test_lufs_service_uses_current_configured_ffmpeg(monkeypatch):
    import services.lufs_service as lufs_service

    configured_ffmpeg = r"C:\PB-Studio-Bin\ffmpeg.exe"
    captured: dict[str, list[str]] = {}

    monkeypatch.setattr(
        lufs_service,
        "get_ffmpeg_bin",
        lambda: configured_ffmpeg,
        raising=False,
    )
    monkeypatch.setattr(lufs_service.LUFSService, "_timeout_for_file", lambda *_args: 120)

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="", stderr='{"input_i":"-14","input_tp":"-1","input_lra":"8"}')

    monkeypatch.setattr(lufs_service.subprocess, "run", fake_run, raising=False)

    stderr = lufs_service.LUFSService()._run_ffmpeg(r"C:\media\mix.m4a")

    assert stderr
    assert captured["cmd"][0] == configured_ffmpeg
