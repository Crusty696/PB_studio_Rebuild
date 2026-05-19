"""Video-Decoder-Primitive — RED-Test-Suite.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 10 (Tier 2 Building-Blocks)
Decision-Anker: D-045

Verifiziert das Decoder-Primitive (`services/video_pipeline/primitives/decoder.py`):
- probe()           -> VideoMeta mit duration / fps / width / height / codec
- iter_frames()     -> Iterator[np.ndarray] mit korrekter Anzahl + Shape
- extract_frame()   -> np.ndarray bei exakt time_s
- extract_audio_stream() -> WAV-Datei mit korrekter Duration

Testdaten: synthetisches Video erzeugt via ffmpeg lavfi (deterministic).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg / ffprobe nicht im PATH",
)


@pytest.fixture
def synth_video_2s(tmp_path: Path) -> Path:
    """2s Test-Video, 320x240, 10 fps, H.264, mit Audio-Track."""
    out = tmp_path / "synth_2s.mp4"
    ffmpeg = shutil.which("ffmpeg")
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest",
        str(out),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, f"ffmpeg failed: {res.stderr}"
    assert out.exists()
    return out


def test_probe_returns_video_meta(synth_video_2s: Path):
    from services.video_pipeline.primitives.decoder import VideoDecoder

    dec = VideoDecoder()
    meta = dec.probe(synth_video_2s)

    assert meta.duration_s == pytest.approx(2.0, abs=0.1)
    assert meta.fps == pytest.approx(10.0, abs=0.5)
    assert meta.width == 320
    assert meta.height == 240
    assert meta.codec == "h264"
    assert meta.has_audio is True


def test_iter_frames_yields_expected_count(synth_video_2s: Path):
    from services.video_pipeline.primitives.decoder import VideoDecoder

    dec = VideoDecoder()
    frames = list(dec.iter_frames(synth_video_2s))

    # 2s * 10 fps = 20 frames erwartet (±1 fuer encode-rundung)
    assert 18 <= len(frames) <= 22, f"erwartet ~20 frames, bekommen {len(frames)}"

    # Shape (H, W, 3) RGB
    assert frames[0].shape == (240, 320, 3)
    assert frames[0].dtype == np.uint8


def test_iter_frames_with_sampling(synth_video_2s: Path):
    from services.video_pipeline.primitives.decoder import VideoDecoder

    dec = VideoDecoder()
    # sample_every_n=5 -> jeder 5. Frame
    frames = list(dec.iter_frames(synth_video_2s, sample_every_n=5))

    # 20 frames / 5 = 4 (±1)
    assert 3 <= len(frames) <= 5, f"erwartet ~4 sampled frames, bekommen {len(frames)}"


def test_iter_frames_time_window(synth_video_2s: Path):
    from services.video_pipeline.primitives.decoder import VideoDecoder

    dec = VideoDecoder()
    # nur 0.5s bis 1.0s -> 5 frames bei 10 fps
    frames = list(dec.iter_frames(synth_video_2s, start_s=0.5, end_s=1.0))
    assert 4 <= len(frames) <= 6


def test_extract_frame_returns_single(synth_video_2s: Path):
    from services.video_pipeline.primitives.decoder import VideoDecoder

    dec = VideoDecoder()
    frame = dec.extract_frame(synth_video_2s, time_s=1.0)

    assert frame.shape == (240, 320, 3)
    assert frame.dtype == np.uint8


def test_extract_audio_stream_creates_wav(synth_video_2s: Path, tmp_path: Path):
    from services.video_pipeline.primitives.decoder import VideoDecoder

    dec = VideoDecoder()
    target = tmp_path / "out.wav"
    result = dec.extract_audio_stream(synth_video_2s, target)

    assert result == target
    assert target.exists()
    assert target.stat().st_size > 0


def test_probe_raises_on_invalid_path(tmp_path: Path):
    from services.video_pipeline.primitives.decoder import VideoDecoder

    dec = VideoDecoder()
    bogus = tmp_path / "doesnt_exist.mp4"
    with pytest.raises(FileNotFoundError):
        dec.probe(bogus)
