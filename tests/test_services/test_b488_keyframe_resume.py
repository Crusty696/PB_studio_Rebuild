from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from services.video_pipeline.stages.scene_detect_stage import SceneDetectStage
from services.video_pipeline.stages.keyframe_extract_stage import KeyframeExtractStage

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

def test_keyframe_extract_resume_skips_existing_files(synth_2scene_video: Path, tmp_path: Path):
    storage = tmp_path / "out"
    
    # 1. Run scene detect to get scenes.json
    SceneDetectStage().run(synth_2scene_video, storage)
    
    # 2. Run first extraction
    stage = KeyframeExtractStage()
    res1 = stage.run(synth_2scene_video, storage)
    
    assert res1.status == "done"
    keyframe_count = res1.metrics["keyframe_count"]
    assert keyframe_count >= 5
    
    kf_dir = storage / "keyframes"
    jpegs_first = list(kf_dir.glob("*.jpg"))
    assert len(jpegs_first) == keyframe_count
    
    # 3. Check keyframes.json exists
    index_path = storage / "keyframes.json"
    assert index_path.exists()
    
    # 4. Mock extract_frame so it raises an error if called.
    # This proves that the stage skips calling it for existing files!
    mock_decoder = MagicMock()
    mock_decoder.extract_frame.side_effect = RuntimeError("Decoder called on existing file!")
    
    stage_resume = KeyframeExtractStage(decoder=mock_decoder)
    
    # Run the stage again
    res2 = stage_resume.run(synth_2scene_video, storage)
    
    # It must succeed because all files exist
    assert res2.status == "done"
    assert res2.metrics["keyframe_count"] == keyframe_count
    assert res2.metrics["skipped_count"] == res1.metrics["skipped_count"]
    
    # And keyframes.json must be fully written
    index_data = json.loads(index_path.read_text())
    assert len(index_data) == keyframe_count
    assert all("path" in item for item in index_data)
