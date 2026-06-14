from __future__ import annotations

import hashlib
from pathlib import Path


_FAST_CHUNK_SIZE = 5 * 1024 * 1024


def compute_source_sha256(path: str | Path, *, media_type: str, mode: str = "fast") -> str:
    """Compute deterministic source identity for audio/video files.

    ``fast`` hashes first 5 MiB, last 5 MiB, file size, and media type.
    ``strict`` hashes the complete file plus media type.
    """

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Source file missing: {source}")
    if media_type not in {"audio", "video", "image"}:
        raise ValueError(f"Unsupported media_type: {media_type!r}")
    if mode not in {"fast", "strict"}:
        raise ValueError(f"Unsupported hash mode: {mode!r}")

    hasher = hashlib.sha256()
    hasher.update(f"media_type={media_type}\0mode={mode}\0".encode("utf-8"))

    size = source.stat().st_size
    hasher.update(f"size={size}\0".encode("utf-8"))

    with source.open("rb") as fh:
        if mode == "strict":
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                hasher.update(chunk)
        else:
            first = fh.read(_FAST_CHUNK_SIZE)
            fh.seek(max(size - _FAST_CHUNK_SIZE, 0))
            last = fh.read(_FAST_CHUNK_SIZE)
            hasher.update(first)
            hasher.update(b"\0FAST_LAST\0")
            hasher.update(last)

    return hasher.hexdigest()
