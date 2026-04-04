"""PB Studio Error Hierarchie + Result Pattern.

Zentrale Fehlerdefinitionen fuer die gesamte App.
Services werfen diese Exceptions — Worker fangen sie ab und emittieren error-Signals.
"""


class PBStudioError(Exception):
    """Basis-Exception fuer alle PB Studio Fehler."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


# ── Audio ──────────────────────────────────────────────────────

class AudioError(PBStudioError):
    """Fehler in der Audio-Pipeline."""


class AudioLoadError(AudioError):
    """Audio-Datei konnte nicht geladen werden (corrupt, falsches Format, nicht gefunden)."""


class StemSeparationError(AudioError):
    """Stem-Separation fehlgeschlagen."""


class BeatDetectionError(AudioError):
    """BPM/Beat-Erkennung fehlgeschlagen."""


# ── Video ──────────────────────────────────────────────────────

class VideoError(PBStudioError):
    """Fehler in der Video-Pipeline."""


class FrameExtractionError(VideoError):
    """Frame-Extraktion via FFmpeg fehlgeschlagen."""


class EmbeddingError(VideoError):
    """SigLIP-Embedding-Generierung fehlgeschlagen."""


class SceneDetectionError(VideoError):
    """Szenen-Erkennung fehlgeschlagen."""


# ── GPU ────────────────────────────────────────────────────────

class GPUError(PBStudioError):
    """GPU/CUDA Fehler."""


class CUDANotAvailableError(GPUError):
    """CUDA ist nicht verfuegbar aber wird benoetigt."""


class VRAMInsufficientError(GPUError):
    """Nicht genug VRAM fuer die Operation."""

    def __init__(self, operation: str, required_gb: float = 0, available_gb: float = 0):
        super().__init__(
            f"Nicht genug VRAM fuer {operation}: "
            f"{required_gb:.1f} GB benoetigt, {available_gb:.1f} GB frei",
            {"operation": operation, "required_gb": required_gb, "available_gb": available_gb},
        )


class CUDAOutOfMemoryError(GPUError):
    """CUDA Out of Memory waehrend einer Operation."""

    def __init__(self, operation: str = ""):
        super().__init__(
            f"CUDA Out of Memory bei {operation}" if operation else "CUDA Out of Memory",
            {"operation": operation},
        )


# ── ML Model availability ──────────────────────────────────────

class MLError(PBStudioError):
    """Allgemeiner ML/KI-Fehler."""


class MLModelNotFoundError(MLError):
    """Ein ML-Modell ist nicht heruntergeladen / nicht im lokalen Cache.

    Wird ausgeloest wenn ein HuggingFace- oder beat_this-Modell nicht lokal
    vorhanden ist und kein Internet-Download moeglich/gewuenscht ist.
    """

    def __init__(self, model_id: str, hint: str = ""):
        msg = f"ML-Modell '{model_id}' nicht gefunden (nicht heruntergeladen)."
        if hint:
            msg += f" {hint}"
        super().__init__(msg, {"model_id": model_id, "hint": hint})
        self.model_id = model_id


class MLUnavailableError(MLError):
    """Ein ML-Feature ist nicht verfuegbar (kein Modell, kein GPU, kein Package).

    Wird fuer den UI-sichtbaren Degradierungs-Pfad genutzt.
    """

    def __init__(self, feature: str, reason: str, fallback: str = ""):
        msg = f"ML-Feature '{feature}' nicht verfuegbar: {reason}"
        if fallback:
            msg += f" Fallback: {fallback}"
        super().__init__(msg, {"feature": feature, "reason": reason, "fallback": fallback})
        self.feature = feature
        self.reason = reason
        self.fallback = fallback


# ── Database ───────────────────────────────────────────────────

class DatabaseError(PBStudioError):
    """Datenbank-Fehler."""


class DatabaseLockedError(DatabaseError):
    """SQLite database is locked (zu viele gleichzeitige Writer)."""


# ── Export ─────────────────────────────────────────────────────

class ExportError(PBStudioError):
    """Fehler beim Video-Export."""


class FFmpegError(PBStudioError):
    """FFmpeg-Prozess fehlgeschlagen."""

    def __init__(self, message: str, returncode: int = -1, stderr: str = ""):
        super().__init__(message, {"returncode": returncode, "stderr": stderr[:500]})
        self.returncode = returncode
        self.stderr = stderr


# ── Result Pattern ─────────────────────────────────────────────

from typing import Generic, TypeVar

T = TypeVar("T")


class Result(Generic[T]):
    """Explizites Error-Handling ohne Exceptions.

    Verwendung:
        result = do_something()
        if result.is_ok:
            data = result.unwrap()
        else:
            show_error(result.error)
    """

    __slots__ = ("_value", "_error", "_is_fallback", "_fallback_reason")

    def __init__(self, value: T = None, error: str = None, is_fallback: bool = False,
                 fallback_reason: str = ""):
        self._value = value
        self._error = error
        self._is_fallback = is_fallback
        self._fallback_reason = fallback_reason

    @property
    def is_ok(self) -> bool:
        return self._error is None

    @property
    def is_fallback(self) -> bool:
        """True wenn das Ergebnis ein Fallback-Wert ist (nicht der echte Wert)."""
        return self._is_fallback

    @property
    def fallback_reason(self) -> str:
        """Grund warum ein Fallback-Wert geliefert wurde."""
        return self._fallback_reason

    @property
    def error(self) -> str | None:
        return self._error

    def unwrap(self) -> T:
        if self._error is not None:
            raise ValueError(f"Result.unwrap() auf Fehler: {self._error}")
        return self._value

    def unwrap_or(self, default: T) -> T:
        return default if self._error is not None else self._value

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        return cls(value=value)

    @classmethod
    def err(cls, error: str) -> "Result[T]":
        return cls(error=error)

    @classmethod
    def fallback(cls, value: T, reason: str) -> "Result[T]":
        """Erstellt ein Ergebnis mit Fallback-Wert und Grund."""
        return cls(value=value, is_fallback=True, fallback_reason=reason)

    def __repr__(self):
        if self._error:
            return f"Result.err({self._error!r})"
        fb = " [fallback]" if self._is_fallback else ""
        return f"Result.ok({self._value!r}){fb}"
