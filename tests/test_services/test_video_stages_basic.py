"""Phase 34/35/36 — Stage-Wrapper Tests.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg missing"
)


@pytest.fixture
def synth_2scene_video(tmp_path: Path) -> Path:
    """6s 2-Szenen-Video (testsrc + smptebars concat)."""
    out = tmp_path / "src.mp4"
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    ff = shutil.which("ffmpeg")
    for src, gen in [(a, "testsrc"), (b, "smptebars")]:
        subprocess.run(
            [ff, "-y", "-f", "lavfi",
             "-i", f"{gen}=duration=3:size=320x240:rate=10",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)],
            check=True, capture_output=True, timeout=30,
        )
    concat = tmp_path / "concat.txt"
    concat.write_text(f"file '{a}'\nfile '{b}'\n")
    subprocess.run(
        [ff, "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
         "-c", "copy", str(out)],
        check=True, capture_output=True, timeout=30,
    )
    return out


# ===== Phase 34: SceneDetectStage =====

def test_scene_detect_stage_creates_scenes_json(synth_2scene_video: Path, tmp_path: Path):
    from services.video_pipeline.stages.scene_detect_stage import SceneDetectStage
    stage = SceneDetectStage()
    res = stage.run(synth_2scene_video, tmp_path / "out")
    assert res.status == "done"
    assert res.stage_id == "scene_detect"
    out = tmp_path / "out" / "scenes.json"
    assert out.exists()
    data = json.loads(out.read_text())
    assert len(data) >= 2
    assert res.metrics["scene_count"] >= 2


def test_scene_detect_stage_failed_on_missing(tmp_path: Path):
    from services.video_pipeline.stages.scene_detect_stage import SceneDetectStage
    stage = SceneDetectStage()
    res = stage.run(tmp_path / "nope.mp4", tmp_path / "out")
    assert res.status == "failed"
    assert res.error is not None


# ===== Phase 35: KeyframeExtractStage =====

def test_keyframe_stage_runs_after_scene_detect(synth_2scene_video: Path, tmp_path: Path):
    from services.video_pipeline.stages.scene_detect_stage import SceneDetectStage
    from services.video_pipeline.stages.keyframe_extract_stage import KeyframeExtractStage

    storage = tmp_path / "out"
    SceneDetectStage().run(synth_2scene_video, storage)
    res = KeyframeExtractStage(mode="anchors_3").run(synth_2scene_video, storage)

    assert res.status == "done"
    assert res.metrics["keyframe_count"] >= 6   # 2 scenes * 3 anchors
    kf_dir = storage / "keyframes"
    assert kf_dir.exists()
    jpegs = list(kf_dir.glob("*.jpg"))
    assert len(jpegs) >= 6
    index = json.loads((storage / "keyframes.json").read_text())
    assert isinstance(index, list)
    assert all("path" in e and "time_s" in e for e in index)


def test_keyframe_stage_without_scenes_json_fails(synth_2scene_video: Path, tmp_path: Path):
    from services.video_pipeline.stages.keyframe_extract_stage import KeyframeExtractStage
    res = KeyframeExtractStage().run(synth_2scene_video, tmp_path / "out")
    assert res.status == "failed"
    assert "scenes.json" in (res.error or "")


# ===== Phase 36: ProxyGenStage =====

def test_proxy_gen_stage(synth_2scene_video: Path, tmp_path: Path):
    from services.video_pipeline.stages.proxy_gen_stage import ProxyGenStage
    res = ProxyGenStage(max_width=320, bitrate="500k").run(
        synth_2scene_video, tmp_path / "out"
    )
    assert res.status == "done"
    assert (tmp_path / "out" / "proxy.mp4").exists()
    assert res.metrics["bytes"] > 0


def test_proxy_gen_stage_reuse_skips_re_encode(synth_2scene_video: Path, tmp_path: Path):
    from services.video_pipeline.stages.proxy_gen_stage import ProxyGenStage
    stage = ProxyGenStage(max_width=320, bitrate="500k")
    storage = tmp_path / "out"
    r1 = stage.run(synth_2scene_video, storage)
    mtime1 = (storage / "proxy.mp4").stat().st_mtime
    r2 = stage.run(synth_2scene_video, storage)
    mtime2 = (storage / "proxy.mp4").stat().st_mtime
    assert mtime1 == mtime2  # reuse
    assert r2.status == "done"
