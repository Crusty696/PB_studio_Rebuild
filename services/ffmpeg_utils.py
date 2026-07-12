"""Gemeinsame FFmpeg-/Proxy-Helfer fuer Service-Module."""

from __future__ import annotations

from pathlib import Path


def sanitize_ffmpeg_error(stderr: str, max_lines: int = 3) -> str:
    """Sanitize FFmpeg stderr for safe error messages — strip full paths."""
    if not stderr:
        return "(no stderr)"
    lines = stderr.strip().splitlines()
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    return "\n".join(tail)


def proxy_dir() -> Path:
    """Returns proxy directory for the current project (lazy APP_ROOT read)."""
    import database.session as _session
    return _session.APP_ROOT / "storage" / "proxies"
