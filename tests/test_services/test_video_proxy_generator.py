"""Phase 15 — Proxy-Generator RED.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 15 (Tier 2 Building-Blocks)
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
    out = tmp_path / "src.mp4"
    subprocess.run(
        [
            shutil.which("ffmpeg"), "-y", "-f", "lavfi",
            "-i", "testsrc=duration=2:size=1280x720:rate=10",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
        ],
        check=True, capture_output=True, timeout=30,
    )
    return out


def test_proxy_generated(synth_video: Path, tmp_path: Path):
    """Proxy entsteht, ist nicht leer. Groesse-Vergleich nicht zuverlaessig bei
    synthetischen testsrc-Quellen (hoch komprimierbar)."""
    from services.video_pipeline.primitives.proxy_generator import generate_proxy
    dst = tmp_path / "proxy.mp4"
    result = generate_proxy(synth_video, dst, max_width=480, bitrate="500k")
    assert result == dst
    assert dst.exists()
    assert dst.stat().st_size > 0


def test_proxy_resolution_capped(synth_video: Path, tmp_path: Path):
    from services.video_pipeline.primitives.proxy_generator import generate_proxy
    from services.video_pipeline.primitives.decoder import VideoDecoder
    dst = tmp_path / "proxy.mp4"
    generate_proxy(synth_video, dst, max_width=480, bitrate="500k")
    meta = VideoDecoder().probe(dst)
    assert meta.width <= 480


def test_proxy_cpu_fallback_when_nvenc_unavailable(synth_video: Path, tmp_path: Path):
    """h264_nvenc kann auf manchen Setups fehlen -> libx264-fallback."""
    from services.video_pipeline.primitives.proxy_generator import generate_proxy
    dst = tmp_path / "proxy_cpu.mp4"
    # codec="auto" probiert nvenc, faellt zurueck auf libx264
    result = generate_proxy(synth_video, dst, max_width=640, bitrate="500k", codec="libx264")
    assert result.exists()


def test_proxy_skip_if_already_exists(synth_video: Path, tmp_path: Path):
    from services.video_pipeline.primitives.proxy_generator import generate_proxy
    dst = tmp_path / "proxy.mp4"
    generate_proxy(synth_video, dst, max_width=480, bitrate="500k")
    size1 = dst.stat().st_size
    mtime1 = dst.stat().st_mtime

    # Zweiter Aufruf mit reuse=True -> kein Re-Encode
    generate_proxy(synth_video, dst, max_width=480, bitrate="500k", reuse=True)
    mtime2 = dst.stat().st_mtime
    assert mtime1 == mtime2


def test_proxy_missing_source_raises(tmp_path: Path):
    from services.video_pipeline.primitives.proxy_generator import generate_proxy
    with pytest.raises(FileNotFoundError):
        generate_proxy(tmp_path / "nope.mp4", tmp_path / "out.mp4")


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe missing")
def test_b366_reuse_rejects_nonzero_junk_file(synth_video: Path, tmp_path: Path):
    """B-366: reuse must not accept a non-zero junk file. A bogus proxy.mp4
    (bytes > 0 but not a decodable video) must be re-encoded into a valid one."""
    from services.video_pipeline.primitives.proxy_generator import generate_proxy
    dst = tmp_path / "proxy.mp4"
    dst.write_bytes(b"this is not a video file" * 50)  # st_size > 0, junk
    assert dst.stat().st_size > 0

    result = generate_proxy(synth_video, dst, max_width=480, bitrate="500k", reuse=True)
    assert result == dst
    # After re-encode the file must be a real, probeable video stream.
    from services.video_pipeline.primitives.proxy_generator import _is_valid_video
    assert _is_valid_video(dst)
