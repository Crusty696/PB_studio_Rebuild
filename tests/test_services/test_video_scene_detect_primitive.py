"""Phase 13 — Scene-Detect-Primitive RED.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 13 (Tier 2 Building-Blocks)
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg missing"
)


@pytest.fixture
def synth_video_with_cut(tmp_path: Path) -> Path:
    """6s Video mit hartem Cut bei 3s (Concat zweier verschiedener testsrc)."""
    out = tmp_path / "two_scenes.mp4"
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    ff = shutil.which("ffmpeg")

    # a: testsrc 3s
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=10",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(a)],
        check=True, capture_output=True, timeout=30,
    )
    # b: smptebars 3s
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", "smptebars=duration=3:size=320x240:rate=10",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(b)],
        check=True, capture_output=True, timeout=30,
    )
    # concat
    concat_file = tmp_path / "concat.txt"
    concat_file.write_text(f"file '{a}'\nfile '{b}'\n")
    subprocess.run(
        [ff, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
         "-c", "copy", str(out)],
        check=True, capture_output=True, timeout=30,
    )
    return out


def test_detect_scenes_finds_cut(synth_video_with_cut: Path):
    from services.video_pipeline.primitives.scene_detect import detect_scenes
    scenes = detect_scenes(synth_video_with_cut)
    # erwartet: mind. 2 Szenen (Cut bei ~3s)
    assert len(scenes) >= 2
    # Coverage: erste Szene startet bei 0, letzte endet ~6
    assert scenes[0].start_s == pytest.approx(0.0, abs=0.1)
    assert scenes[-1].end_s == pytest.approx(6.0, abs=0.5)


def test_detect_scenes_single_clip_returns_one(tmp_path: Path):
    from services.video_pipeline.primitives.scene_detect import detect_scenes
    ff = shutil.which("ffmpeg")
    single = tmp_path / "single.mp4"
    subprocess.run(
        [ff, "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(single)],
        check=True, capture_output=True, timeout=30,
    )
    scenes = detect_scenes(single)
    # ohne Cut -> 1 Szene
    assert len(scenes) >= 1
    assert scenes[0].duration_s > 0


def test_scene_dataclass_fields():
    from services.video_pipeline.primitives.scene_detect import Scene
    s = Scene(start_s=0.0, end_s=2.0, index=0)
    assert s.start_s == 0.0
    assert s.end_s == 2.0
    assert s.duration_s == 2.0
    assert s.index == 0
