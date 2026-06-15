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

import logging
import subprocess
from pathlib import Path

from services import startup_checks
from services.nvenc_policy import require_nvenc, required_message

logger = logging.getLogger(__name__)

__all__ = ["generate_proxy"]


def _ffmpeg() -> str:
    ff = str(startup_checks.get_ffmpeg_bin())
    if not ff:
        raise RuntimeError("ffmpeg not in PATH")
    return ff


def _ffprobe() -> str | None:
    probe = str(startup_checks.get_ffprobe_bin())
    return probe or None


def _is_valid_video(path: Path) -> bool:
    """B-366: True only if ``path`` is a probeable file with a video stream.

    Used to validate a reuse-candidate proxy. A non-zero-byte junk file is
    rejected because ffprobe either fails or reports no ``codec_type=video``
    stream. If ffprobe is not on PATH we cannot validate -> treat as invalid
    so the caller re-encodes instead of trusting an unverified file.
    """
    probe = _ffprobe()
    if probe is None:
        return False
    res = subprocess.run(
        [
            probe, "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_type",
            "-of", "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True, text=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return res.returncode == 0 and "video" in res.stdout


def _has_nvenc() -> bool:
    """Pruefen ob h264_nvenc verfuegbar (FFmpeg-Build-Feature)."""
    res = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-encoders"],
        capture_output=True, text=True, timeout=10,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return "h264_nvenc" in res.stdout


def _try_encode(src: Path, dst: Path, max_width: int, bitrate: str, codec: str) -> bool:
    cmd = [
        _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        # B-367: never upscale. ``scale={max_width}:-2`` enlarges sources
        # narrower than ``max_width``. ``min(iw,{max_width})`` caps the output
        # width at the source width; height stays aspect-preserving and even.
        "-vf", f"scale='min(iw,{max_width})':-2",
        "-c:v", codec,
        "-b:v", bitrate,
        # F-17: re-encode audio to AAC instead of -c:a copy. Copying the source
        # audio codec into the proxy MP4 fails for MP4-incompatible codecs
        # (e.g. PCM), which would abort the whole proxy stage.
        "-c:a", "aac", "-b:a", "128k",
        str(dst),
    ]
    if "nvenc" in codec:
        # B-505: NVENC app-weit serialisieren — gleicher GpuSerializer wie
        # export_service/convert_service/video_service. GTX 1060 (Pascal)
        # erlaubt nur 2-3 NVENC-Sessions; parallele Encodes enden in
        # "OpenEncodeSessionEx failed". Lock NUR um den Subprocess-Lauf.
        from services.brain_v3.gpu_serializer import get_default_serializer
        with get_default_serializer().acquire("proxy_gen"):
            res = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    else:
        res = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
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
    # B-366: ``reuse`` must not trust an arbitrary non-zero file. Validate the
    # existing target via ffprobe (must decode + contain a video stream); a junk
    # ``proxy.mp4`` is rejected and re-encoded below instead of returned as-is.
    if reuse and dst.exists() and dst.stat().st_size > 0 and _is_valid_video(dst):
        return dst

    dst.parent.mkdir(parents=True, exist_ok=True)

    if codec == "auto":
        if _has_nvenc():
            # B-505: TimeoutExpired vom NVENC-Versuch fangen — vorher riss
            # ein haengender NVENC-Encode (z.B. Session-Stau) die ganze
            # Proxy-Stage ab, obwohl der CPU-Fallback funktioniert haette.
            try:
                if _try_encode(src, dst, max_width, bitrate, "h264_nvenc"):
                    return dst
            except subprocess.TimeoutExpired:
                logger.warning(
                    "proxy: h264_nvenc timeout for %s -> libx264 (CPU) fallback",
                    src.name,
                )
            if require_nvenc():
                raise RuntimeError(
                    required_message(f"proxy h264_nvenc failed for {src.name}")
                )
        elif require_nvenc():
            raise RuntimeError(
                required_message("proxy h264_nvenc nicht verfuegbar")
            )
        # F-17: NVENC unavailable or failed -> CPU fallback is allowed per GPU
        # rule, but make it visible instead of silent.
        logger.warning(
            "proxy: h264_nvenc unavailable/failed for %s -> libx264 (CPU) fallback",
            src.name,
        )
        if _try_encode(src, dst, max_width, bitrate, "libx264"):
            return dst
        raise RuntimeError("proxy encode failed (both nvenc + libx264)")

    if codec == "libx264" and require_nvenc():
        raise RuntimeError(
            required_message("proxy codec=libx264 angefordert; CPU-Fallback verboten")
        )
    if not _try_encode(src, dst, max_width, bitrate, codec):
        raise RuntimeError(f"proxy encode failed with codec={codec}")
    return dst
