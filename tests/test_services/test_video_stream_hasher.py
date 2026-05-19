"""Phase 11 — Stream-Hasher RED-Test.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 11 (Tier 2 Building-Blocks)
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
def synth_video(tmp_path: Path) -> Path:
    out = tmp_path / "synth.mp4"
    subprocess.run(
        [
            shutil.which("ffmpeg"), "-y", "-f", "lavfi",
            "-i", "testsrc=duration=1:size=160x120:rate=10",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
        ],
        check=True, capture_output=True, timeout=30,
    )
    return out


def test_stream_sha_deterministic(synth_video: Path):
    from services.video_pipeline.primitives.stream_hasher import stream_sha256
    h1 = stream_sha256(synth_video)
    h2 = stream_sha256(synth_video)
    assert h1 == h2
    assert len(h1) == 64


def test_stream_sha_differs_on_modified_file(synth_video: Path, tmp_path: Path):
    from services.video_pipeline.primitives.stream_hasher import stream_sha256
    h1 = stream_sha256(synth_video)

    other = tmp_path / "other.mp4"
    subprocess.run(
        [
            shutil.which("ffmpeg"), "-y", "-f", "lavfi",
            "-i", "testsrc=duration=2:size=160x120:rate=10",  # 2s statt 1s
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(other),
        ],
        check=True, capture_output=True, timeout=30,
    )
    h2 = stream_sha256(other)
    assert h1 != h2


def test_stream_sha_fast_mode_uses_file_bytes(synth_video: Path):
    from services.video_pipeline.primitives.stream_hasher import stream_sha256
    h = stream_sha256(synth_video, strict=False)
    assert isinstance(h, str)
    assert len(h) == 64


def test_stream_sha_missing_file_raises(tmp_path: Path):
    from services.video_pipeline.primitives.stream_hasher import stream_sha256
    with pytest.raises(FileNotFoundError):
        stream_sha256(tmp_path / "nope.mp4")
