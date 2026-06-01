"""Video-Decoder-Primitive.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 10 (Tier 2 Building-Blocks)

Subprocess-basierter FFmpeg-Wrapper (kein PyAV-Dep). Liefert:
- ``VideoMeta`` via ``probe()`` (ffprobe JSON)
- ``iter_frames()`` als Generator von RGB24-NumPy-Arrays (Pipe-Stream)
- ``extract_frame()`` Einzelframe an Timestamp
- ``extract_audio_stream()`` Audio-Track als WAV-File

Bibliothek-Wahl: ``subprocess`` + System-FFmpeg. PyAV erst in Tier 2
phase 10+ falls Performance-Bottleneck.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

import numpy as np

from services import startup_checks

__all__ = ["VideoDecoder", "VideoMeta"]


@dataclass(frozen=True)
class VideoMeta:
    duration_s: float
    fps: float
    width: int
    height: int
    codec: str
    has_audio: bool
    pixel_format: str = "yuv420p"


def _resolve_ffmpeg() -> str:
    ff = str(startup_checks.get_ffmpeg_bin())
    if not ff:
        raise RuntimeError("ffmpeg not found in PATH")
    return ff


def _resolve_ffprobe() -> str:
    fp = str(startup_checks.get_ffprobe_bin())
    if not fp:
        raise RuntimeError("ffprobe not found in PATH")
    return fp


class VideoDecoder:
    """Minimaler FFmpeg-Decoder-Wrapper fuer Video-Pipeline."""

    def __init__(self, ffmpeg_path: Optional[str] = None, ffprobe_path: Optional[str] = None):
        self._ffmpeg = ffmpeg_path or _resolve_ffmpeg()
        self._ffprobe = ffprobe_path or _resolve_ffprobe()

    def probe(self, path: Path) -> VideoMeta:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"video not found: {path}")

        cmd = [
            self._ffprobe,
            "-v", "error",
            "-print_format", "json",
            "-show_streams",
            "-show_format",
            str(path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {res.stderr}")

        data = json.loads(res.stdout)
        v_stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "video"),
            None,
        )
        if v_stream is None:
            raise RuntimeError(f"no video stream: {path}")

        a_stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "audio"),
            None,
        )

        duration_s = float(data.get("format", {}).get("duration", 0.0))
        if duration_s <= 0:
            duration_s = float(v_stream.get("duration", 0.0))

        fps_str = v_stream.get("r_frame_rate", "0/1")
        num, den = fps_str.split("/") if "/" in fps_str else (fps_str, "1")
        fps = float(num) / float(den) if float(den) != 0 else 0.0

        return VideoMeta(
            duration_s=duration_s,
            fps=fps,
            width=int(v_stream["width"]),
            height=int(v_stream["height"]),
            codec=v_stream.get("codec_name", ""),
            has_audio=a_stream is not None,
            pixel_format=v_stream.get("pix_fmt", "yuv420p"),
        )

    def iter_frames(
        self,
        path: Path,
        *,
        start_s: float = 0.0,
        end_s: Optional[float] = None,
        sample_every_n: int = 1,
    ) -> Iterator[np.ndarray]:
        """Liefert RGB24-Frames als np.ndarray (H, W, 3) uint8.

        ``sample_every_n=1`` -> alle Frames.
        ``sample_every_n=5`` -> jeder 5. Frame.
        ``start_s`` / ``end_s`` -> Zeitfenster.
        """
        path = Path(path)
        meta = self.probe(path)
        h, w = meta.height, meta.width
        frame_bytes = h * w * 3

        cmd = [self._ffmpeg, "-hide_banner", "-loglevel", "error"]
        if start_s > 0:
            cmd += ["-ss", f"{start_s:.6f}"]
        cmd += ["-i", str(path)]
        if end_s is not None:
            duration = max(0.0, end_s - start_s)
            cmd += ["-t", f"{duration:.6f}"]
        if sample_every_n > 1:
            cmd += ["-vf", f"select='not(mod(n\\,{sample_every_n}))'", "-vsync", "0"]
        cmd += [
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-",
        ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=frame_bytes * 4,
        )
        try:
            while True:
                buf = proc.stdout.read(frame_bytes)
                if not buf or len(buf) < frame_bytes:
                    break
                yield np.frombuffer(buf, dtype=np.uint8).reshape((h, w, 3))
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass
            proc.wait(timeout=10)

    def extract_frame(self, path: Path, time_s: float) -> np.ndarray:
        """Liefert genau einen Frame bei ``time_s``."""
        path = Path(path)
        meta = self.probe(path)
        h, w = meta.height, meta.width
        frame_bytes = h * w * 3

        cmd = [
            self._ffmpeg, "-hide_banner", "-loglevel", "error",
            "-ss", f"{time_s:.6f}",
            "-i", str(path),
            "-frames:v", "1",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-",
        ]
        res = subprocess.run(cmd, capture_output=True, timeout=30)
        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg extract_frame failed: {res.stderr.decode(errors='ignore')}")

        if len(res.stdout) < frame_bytes:
            raise RuntimeError(
                f"extract_frame got {len(res.stdout)} bytes, expected {frame_bytes}"
            )
        return np.frombuffer(res.stdout[:frame_bytes], dtype=np.uint8).reshape((h, w, 3))

    def extract_audio_stream(self, path: Path, target_wav: Path) -> Path:
        """Demuxed Audio in WAV PCM 16-bit."""
        path = Path(path)
        target_wav = Path(target_wav)
        target_wav.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            self._ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(path),
            "-vn",
            "-acodec", "pcm_s16le",
            str(target_wav),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg extract_audio failed: {res.stderr}")
        if not target_wav.exists():
            raise RuntimeError(f"audio output not created: {target_wav}")
        return target_wav
