"""B-125 regression test: _normalize_audio_lufs must be cancellable.

Cycle-1 (B-116) added cancel_check to _run_ffmpeg / _run_ffmpeg_with_progress
but _normalize_audio_lufs was overlooked — it had its own
``subprocess.run`` calls. Cycle-2 fixes this gap.
"""

from __future__ import annotations

import inspect


def test_normalize_audio_lufs_accepts_cancel_check() -> None:
    """``_normalize_audio_lufs`` must take a ``cancel_check`` parameter
    so callers can interrupt mid-pass."""
    from services import export_service

    sig = inspect.signature(export_service._normalize_audio_lufs)
    assert "cancel_check" in sig.parameters, (
        "BUG-125 regression: _normalize_audio_lufs must accept "
        "cancel_check kwarg so the LUFS pass can be cancelled."
    )


def test_prepare_normalized_audio_propagates_cancel_check() -> None:
    """The wrapper ``_prepare_normalized_audio`` must propagate
    cancel_check so the export pipeline can pass user-cancel through."""
    from services import export_service

    sig = inspect.signature(export_service._prepare_normalized_audio)
    assert "cancel_check" in sig.parameters, (
        "BUG-125: _prepare_normalized_audio must accept and propagate "
        "cancel_check to _normalize_audio_lufs."
    )
