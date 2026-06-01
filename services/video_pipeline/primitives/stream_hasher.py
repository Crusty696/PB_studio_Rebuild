"""Stream-Hasher.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 11 (Tier 2 Building-Blocks)

Liefert deterministischen content-Hash fuer Audio-/Video-Dateien.

- Fast mode (default): first 5 MB + last 5 MB + filesize + format-meta.
  Container-abhaengig (MP4 + MOV mit identischem Stream haben unterschiedlichen Hash).
- Strict mode: decode via ffmpeg + hash raw packets.
  Container-uebergreifend, langsamer.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

from services import startup_checks

__all__ = ["stream_sha256"]


_FAST_HEAD_BYTES = 5 * 1024 * 1024
_FAST_TAIL_BYTES = 5 * 1024 * 1024


def _hash_fast(path: Path) -> str:
    size = path.stat().st_size
    h = hashlib.sha256()
    h.update(f"size:{size}\n".encode())
    h.update(f"ext:{path.suffix.lower()}\n".encode())
    with open(path, "rb") as fh:
        head = fh.read(min(_FAST_HEAD_BYTES, size))
        h.update(head)
        if size > _FAST_HEAD_BYTES + _FAST_TAIL_BYTES:
            fh.seek(-_FAST_TAIL_BYTES, os.SEEK_END)
            tail = fh.read(_FAST_TAIL_BYTES)
            h.update(tail)
    return h.hexdigest()


def _hash_strict(path: Path, kind: str) -> str:
    ffmpeg = str(startup_checks.get_ffmpeg_bin())
    if not ffmpeg:
        raise RuntimeError("ffmpeg not in PATH (strict mode requires ffmpeg)")

    if kind == "video":
        args = [ffmpeg, "-hide_banner", "-loglevel", "error",
                "-i", str(path), "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    elif kind == "audio":
        args = [ffmpeg, "-hide_banner", "-loglevel", "error",
                "-i", str(path), "-vn", "-f", "s16le", "-ac", "1", "-ar", "16000", "-"]
    else:
        raise ValueError(f"kind must be 'video' or 'audio', got {kind!r}")

    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    h = hashlib.sha256()
    chunk_size = 1 << 20
    try:
        while True:
            chunk = proc.stdout.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    finally:
        proc.stdout.close()
        proc.wait(timeout=10)
    if proc.returncode != 0:
        err = proc.stderr.read().decode(errors="ignore")
        raise RuntimeError(f"ffmpeg strict hash failed: {err}")
    return h.hexdigest()


def stream_sha256(path: Path, *, kind: str = "video", strict: bool = False) -> str:
    """Liefert SHA-256 als Hex.

    Args:
        path: Quelldatei.
        kind: ``"video"`` oder ``"audio"`` (nur fuer strict mode).
        strict: Container-uebergreifender Decoded-Hash (langsamer) vs Fast (default).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if strict:
        return _hash_strict(path, kind)
    return _hash_fast(path)
