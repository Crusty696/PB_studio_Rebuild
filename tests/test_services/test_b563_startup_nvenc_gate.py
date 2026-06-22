from __future__ import annotations

import subprocess
from types import SimpleNamespace

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel

from services import startup_checks


def test_check_nvenc_runs_real_h264_encode_with_resolved_ffmpeg(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(startup_checks.subprocess, "run", fake_run)
    monkeypatch.setattr(startup_checks, "_FFMPEG_BIN", r"C:\PB-Studio-Bin\ffmpeg.exe")

    ok, detail = startup_checks._check_nvenc()

    assert ok is True
    assert detail == ""
    assert calls == [[
        r"C:\PB-Studio-Bin\ffmpeg.exe",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=black:s=256x256:d=1",
        "-frames:v",
        "1",
        "-c:v",
        "h264_nvenc",
        "-f",
        "null",
        "-",
    ]]


def test_strict_nvenc_failure_is_startup_error(monkeypatch, tmp_path):
    monkeypatch.setenv("PB_REQUIRE_NVENC", "1")
    monkeypatch.setattr(startup_checks, "_check_cuda", lambda: (True, "NVIDIA GeForce GTX 1060", 6144))
    monkeypatch.setattr(startup_checks, "_check_ffmpeg", lambda: (True, "8.1.1", True))
    monkeypatch.setattr(
        startup_checks,
        "_check_nvenc",
        lambda: (False, "Driver does not support required NVENC API"),
    )
    monkeypatch.setattr(startup_checks, "_check_disk", lambda _path: 64.0)
    monkeypatch.setattr(startup_checks, "_check_hf_cache", lambda: (True, str(tmp_path), "HF_HOME", "ok", []))
    monkeypatch.setattr(startup_checks, "_check_ollama", lambda: False)
    monkeypatch.setattr(startup_checks, "_check_ml_packages", lambda: (True, True))
    monkeypatch.setattr(startup_checks, "check_python_version", lambda: (True, "3.10.20"))
    monkeypatch.setattr(startup_checks, "_get_nvidia_driver_version", lambda: ("546.33", "NVIDIA GeForce GTX 1060"))

    status = startup_checks.check_system(tmp_path)

    assert status.nvenc_ok is False
    assert any("NVENC_REQUIRED_FAILED" in error for error in status.errors)
    assert any("Driver does not support required NVENC API" in error for error in status.errors)


def test_startup_dialog_shows_nvenc_status_row(qapp):
    from ui.dialogs.startup_check_dialog import StartupCheckDialog

    status = startup_checks.SystemStatus(
        ffmpeg_ok=True,
        ffmpeg_version="8.1.1",
        ffmpeg_path="ffmpeg",
        ffprobe_ok=True,
        nvenc_ok=False,
        nvenc_detail="Driver requires 570+",
        cuda_ok=True,
        gpu_name="NVIDIA GeForce GTX 1060",
        gpu_vram_mb=6144,
        errors=["NVENC_REQUIRED_FAILED"],
    )
    dialog = StartupCheckDialog(status)
    try:
        texts = [label.text() for label in dialog.findChildren(QLabel)]
        assert any("NVENC Encode" in text for text in texts)
        assert any("Driver requires 570+" in text for text in texts)
    finally:
        dialog.close()


def test_setup_wizard_hardware_page_shows_nvenc_status_row(monkeypatch, qapp):
    from ui.dialogs.setup_wizard import _PageHardware

    monkeypatch.setattr(QTimer, "singleShot", lambda *_args: None)
    status = startup_checks.SystemStatus(
        ffmpeg_ok=True,
        ffmpeg_version="8.1.1",
        ffmpeg_path="ffmpeg",
        ffprobe_ok=True,
        nvenc_ok=False,
        nvenc_detail="Driver requires 570+",
        cuda_ok=True,
        gpu_name="NVIDIA GeForce GTX 1060",
        gpu_vram_mb=6144,
        disk_ok=True,
        disk_free_gb=64.0,
    )
    monkeypatch.setattr(startup_checks, "run_startup_checks", lambda: status)

    page = _PageHardware()
    try:
        page._run_check()
        texts = [label.text() for label in page.findChildren(QLabel)]
        assert any("NVENC Encode" in text for text in texts)
        assert any("Driver requires 570+" in text for text in texts)
    finally:
        page.close()
