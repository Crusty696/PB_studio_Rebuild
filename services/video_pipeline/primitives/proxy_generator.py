"""Proxy-Generator.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 15 (Tier 2 Building-Blocks)

Erzeugt niedrig aufgeloeste Proxy-Datei via FFmpeg.

Codec-Strategie:
- ``codec="h264_nvenc"`` (Default fuer GTX 1060, NVENC supported).
- ``codec="libx264"`` als CPU-Fallback.
- ``codec="auto"`` probiert NVENC zuerst, faellt zurueck.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


__all__ = ["generate_proxy"]


def _ffmpeg() -> str:
    ff = shutil.which("ffmpeg")
    if ff is None:
        raise RuntimeError("ffmpeg not in PATH")
    return ff


def _has_nvenc() -> bool:
    """Pruefen ob h264_nvenc verfuegbar (FFmpeg-Build-Feature)."""
    res = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-encoders"],
        capture_output=True, text=True, timeout=10,
    )
    return "h264_nvenc" in res.stdout


def _try_encode(src: Path, dst: Path, max_width: int, bitrate: str, codec: str) -> bool:
    cmd = [
        _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-vf", f"scale={max_width}:-2",
        "-c:v", codec,
        "-b:v", bitrate,
        "-c:a", "copy",
        str(dst),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    return res.returncode == 0


def generate_proxy(
    src: Path,
    dst: Path,
    *,
    max_width: int = 960,
    bitrate: str = "3M",
    codec: str = "auto",
    reuse: bool = False,
) -> Path:
    """Erzeugt Proxy-Datei.

    Args:
        src: Original-Video.
        dst: Ziel-Pfad.
        max_width: Max-Breite, Hoehe automatisch (Aspect erhalten).
        bitrate: Ziel-Bitrate (z. B. "3M" oder "500k").
        codec: ``h264_nvenc`` / ``libx264`` / ``auto``.
        reuse: Wenn True + dst existiert -> nicht neu encoden.
    """
    src = Path(src)
    dst = Path(dst)
    if not src.exists():
        raise FileNotFoundError(f"source not found: {src}")
    if reuse and dst.exists() and dst.stat().st_size > 0:
        return dst

    dst.parent.mkdir(parents=True, exist_ok=True)

    if codec == "auto":
        if _has_nvenc() and _try_encode(src, dst, max_width, bitrate, "h264_nvenc"):
            return dst
        if _try_encode(src, dst, max_width, bitrate, "libx264"):
            return dst
        raise RuntimeError("proxy encode failed (both nvenc + libx264)")

    if not _try_encode(src, dst, max_width, bitrate, codec):
        raise RuntimeError(f"proxy encode failed with codec={codec}")
    return dst
