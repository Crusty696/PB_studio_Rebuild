"""Runtime policy for PB Studio NVENC requirements."""

from __future__ import annotations

import os


NVENC_REQUIRED_CODE = "NVENC_REQUIRED_FAILED"


def require_nvenc() -> bool:
    """Return True when CPU video-encode fallbacks are forbidden."""
    value = os.environ.get("PB_REQUIRE_NVENC", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def required_message(detail: str) -> str:
    """Build one stable error string for strict-NVENC failures."""
    return f"{NVENC_REQUIRED_CODE}: {detail}"
