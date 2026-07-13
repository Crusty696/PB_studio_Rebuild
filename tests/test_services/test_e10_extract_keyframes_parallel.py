from __future__ import annotations

from pathlib import Path
import subprocess
import threading
import time
from types import SimpleNamespace

from services.video_analysis_service import SceneInfo, extract_keyframes


def test_e10_parallel_commands_order_and_skip_cache(tmp_path, monkeypatch):
    import services.video_analysis_service as svc

    video = tmp_path / "input.mp4"
    video.write_bytes(b"video")
    output = tmp_path / "frames"
    scenes = [
        SceneInfo(index=index, start_time=float(index * 2), end_time=float(index * 2 + 2))
        for index in range(5)
    ]
    monkeypatch.setattr("services.startup_checks.get_ffmpeg_bin", lambda: "ffmpeg-e10")
    monkeypatch.setattr(svc, "subprocess_kwargs", lambda: {})

    commands: list[list[str]] = []
    active = 0
    max_active = 0
    lock = threading.Lock()

    def _run(command, **kwargs):
        nonlocal active, max_active
        with lock:
            commands.append(command)
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.03)
        Path(command[-1]).write_bytes(f"jpeg-{command[3]}".encode())
        with lock:
            active -= 1
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(svc.subprocess, "run", _run)

    result = extract_keyframes(str(video), scenes, output_dir=output)

    assert result is scenes
    assert [scene.index for scene in result] == [0, 1, 2, 3, 4]
    assert max_active == 4
    assert len(commands) == 5
    expected_midpoints = {str(index * 2 + 1.0) for index in range(5)}
    assert {command[3] for command in commands} == expected_midpoints
    for command in commands:
        assert command[0:2] == ["ffmpeg-e10", "-y"]
        assert command[2] == "-ss"
        assert command[4:6] == ["-i", str(video)]
        assert command[6:8] == ["-frames:v", "1"]
        assert command[8:10] == [
            "-vf",
            "scale=384:384:force_original_aspect_ratio=decrease,pad=384:384:(ow-iw)/2:(oh-ih)/2",
        ]
        assert command[10:14] == ["-q:v", "2", "-v", "quiet"]

    commands.clear()
    second = extract_keyframes(str(video), scenes, output_dir=output)
    assert second is scenes
    assert commands == []


def test_e10_expected_ffmpeg_error_stays_scene_local(tmp_path, monkeypatch, caplog):
    import services.video_analysis_service as svc

    video = tmp_path / "input.mp4"
    video.write_bytes(b"video")
    output = tmp_path / "frames"
    scenes = [
        SceneInfo(index=index, start_time=float(index * 2), end_time=float(index * 2 + 2))
        for index in range(5)
    ]
    monkeypatch.setattr("services.startup_checks.get_ffmpeg_bin", lambda: "ffmpeg-e10")
    monkeypatch.setattr(svc, "subprocess_kwargs", lambda: {})

    def _run(command, **kwargs):
        if command[3] == "3.0":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        Path(command[-1]).write_bytes(f"jpeg-{command[3]}".encode())
        return SimpleNamespace(returncode=0, stderr=b"")

    monkeypatch.setattr(svc.subprocess, "run", _run)

    result = extract_keyframes(str(video), scenes, output_dir=output)

    assert result is scenes
    assert [scene.index for scene in result] == [0, 1, 2, 3, 4]
    assert scenes[1].keyframe_path is None
    assert [scene.index for scene in scenes if scene.keyframe_path] == [0, 2, 3, 4]
    assert "Keyframe-Fehler Szene 1" in caplog.text
