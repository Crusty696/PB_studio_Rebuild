"""Regression tests for configured FFmpeg/FFprobe resolver usage.

No real FFmpeg/FFprobe process is started here. The tests patch
``subprocess.run`` and assert the command uses the configured resolver path.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

from PySide6.QtGui import QImage


def _clear_ffmpeg_env(monkeypatch) -> None:
    for name in (
        "PB_FFMPEG_EXE",
        "PB_FFMPEG_PATH",
        "FFMPEG_PATH",
        "PB_FFPROBE_EXE",
        "PB_FFPROBE_PATH",
        "FFPROBE_PATH",
    ):
        monkeypatch.delenv(name, raising=False)


def _touch_pair(bin_dir: Path) -> tuple[Path, Path]:
    bin_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = bin_dir / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    ffprobe = bin_dir / ("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
    ffmpeg.write_bytes(b"ffmpeg")
    ffprobe.write_bytes(b"ffprobe")
    return ffmpeg.resolve(), ffprobe.resolve()


def test_resolver_uses_git_common_repo_bin_before_path(monkeypatch, tmp_path):
    import services.startup_checks as startup_checks

    _clear_ffmpeg_env(monkeypatch)
    common_repo = tmp_path / "repo"
    common_git = common_repo / ".git"
    gitdir = common_git / "worktrees" / "agent"
    gitdir.mkdir(parents=True)
    (gitdir / "commondir").write_text("../..\n", encoding="utf-8")
    worktree = common_repo / ".worktrees" / "agent"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")
    expected_ffmpeg, expected_ffprobe = _touch_pair(common_repo / "bin")
    path_dir = tmp_path / "path-bin"
    path_ffmpeg, path_ffprobe = _touch_pair(path_dir)
    monkeypatch.setattr(startup_checks, "_PROJECT_ROOT", worktree)
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: str(path_ffprobe if "probe" in name else path_ffmpeg),
    )

    assert Path(startup_checks.get_ffmpeg_bin()) == expected_ffmpeg
    assert Path(startup_checks.get_ffprobe_bin()) == expected_ffprobe


def test_resolver_prefers_source_local_bundle_over_common_and_path(
    monkeypatch, tmp_path
):
    import services.startup_checks as startup_checks

    _clear_ffmpeg_env(monkeypatch)
    project_root = tmp_path / "root"
    expected_ffmpeg, expected_ffprobe = _touch_pair(project_root / "bin")
    monkeypatch.setattr(startup_checks, "_PROJECT_ROOT", project_root)
    monkeypatch.setattr(shutil, "which", lambda name: str(tmp_path / name))

    assert Path(startup_checks.get_ffmpeg_bin()) == expected_ffmpeg
    assert Path(startup_checks.get_ffprobe_bin()) == expected_ffprobe


def test_frozen_resolver_forces_bundle_despite_hostile_env_and_path(
    monkeypatch, tmp_path
):
    import services.startup_checks as startup_checks

    bundle_root = tmp_path / "_internal"
    expected_ffmpeg, expected_ffprobe = _touch_pair(bundle_root / "bin")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_root), raising=False)
    monkeypatch.setenv("PB_FFMPEG_EXE", str(tmp_path / "hostile-ffmpeg.exe"))
    monkeypatch.setenv("PB_FFPROBE_EXE", str(tmp_path / "hostile-ffprobe.exe"))
    monkeypatch.setattr(shutil, "which", lambda name: str(tmp_path / name))

    assert Path(startup_checks.get_ffmpeg_bin()) == expected_ffmpeg
    assert Path(startup_checks.get_ffprobe_bin()) == expected_ffprobe


def test_resolver_returns_absolute_path_fallback(monkeypatch, tmp_path):
    import services.startup_checks as startup_checks

    _clear_ffmpeg_env(monkeypatch)
    project_root = tmp_path / "root"
    project_root.mkdir()
    path_ffmpeg, path_ffprobe = _touch_pair(tmp_path / "path-bin")
    monkeypatch.setattr(startup_checks, "_PROJECT_ROOT", project_root)
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name: str(path_ffprobe if "probe" in name else path_ffmpeg),
    )

    assert Path(startup_checks.get_ffmpeg_bin()) == path_ffmpeg
    assert Path(startup_checks.get_ffprobe_bin()) == path_ffprobe


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
