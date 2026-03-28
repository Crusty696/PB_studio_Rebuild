"""Base classes for background workers."""

import logging

logger = logging.getLogger(__name__)


def format_user_error(exc: Exception) -> str:
    """Wandelt technische Exceptions in user-freundliche Fehlermeldungen um."""
    from services.errors import (
        CUDAOutOfMemoryError, VRAMInsufficientError, AudioLoadError,
        StemSeparationError, FFmpegError, DatabaseLockedError,
    )

    if isinstance(exc, CUDAOutOfMemoryError):
        op = exc.details.get("operation", "")
        return f"GPU-Speicher voll bei {op}. Schliesse andere GPU-Programme und versuche erneut."
    if isinstance(exc, VRAMInsufficientError):
        return (f"Nicht genug GPU-Speicher: {exc.details.get('required_gb', '?')} GB "
                f"benoetigt, {exc.details.get('available_gb', '?')} GB frei.")
    if isinstance(exc, AudioLoadError):
        return f"Audio-Datei konnte nicht geladen werden: {exc}"
    if isinstance(exc, StemSeparationError):
        return f"Stem-Trennung fehlgeschlagen: {exc}"
    if isinstance(exc, FFmpegError):
        return f"FFmpeg-Fehler (Code {exc.returncode}): {exc}"
    if isinstance(exc, DatabaseLockedError):
        return "Datenbank ist gesperrt. Bitte warte und versuche erneut."
    if isinstance(exc, PermissionError):
        return f"Zugriff verweigert: {exc}"
    if isinstance(exc, FileNotFoundError):
        return f"Datei nicht gefunden: {exc}"

    # Generischer Fallback
    return str(exc)


class CancellableMixin:
    """Mixin for workers: adds a _cancelled flag checked via should_stop()."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cancelled = False
        self._errored = False

    def cancel(self):
        self._cancelled = True

    def should_stop(self) -> bool:
        return self._cancelled
