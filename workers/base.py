"""Base classes for background workers."""

import logging
import threading

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
    """Mixin for workers: adds a thread-safe _cancelled flag checked via should_stop().

    cancel() wird vom Main-Thread aufgerufen, should_stop() vom Worker-Thread.
    Ohne Lock koennte der Worker-Thread den Flag-Wechsel nicht sehen (CPU-Cache).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cancelled = False
        self._errored = False
        self._cancel_lock = threading.Lock()

    def cancel(self):
        with self._cancel_lock:
            self._cancelled = True

    def should_stop(self) -> bool:
        with self._cancel_lock:
            return self._cancelled


# ──────────────────────────────────────────────────────────────────────────
# Cycle 14 / Option B: BaseWorker — Unified Worker-Pattern
# ──────────────────────────────────────────────────────────────────────────


def _import_qobject():
    """Lazy QObject-Import. Erlaubt headless Tests ohne PySide6."""
    try:
        from PySide6.QtCore import QObject, Signal
        return QObject, Signal
    except ImportError:
        return None, None


_QObject, _Signal = _import_qobject()


if _QObject is not None:
    class BaseWorker(_QObject, CancellableMixin):
        """Cycle 14 / Option B: Unified Worker-Klasse für alle PB Studio
        Background-Operations.

        Standard-Signals:
        - finished(object): Worker erfolgreich beendet, payload optional
        - error(str): Worker mit Fehler beendet, format_user_error()-Output
        - progress(int, str): Fortschritt 0-100 + Status-Text

        Lifecycle-Garantien:
        - ``run()`` ist der Entry-Point. Er ruft ``_do_work()`` (Subklasse
          implementiert das) und kümmert sich um Exception-Handling +
          finally-Cleanup. Subklassen überschreiben NUR ``_do_work()``.
        - Bei Exception: ``error.emit(format_user_error(exc))`` wird
          gefeuert, ``self._errored = True`` gesetzt, dann ``finished``
          (für Cleanup-Caller).
        - ``task_id`` wird vom TaskManager automatisch gesetzt
          (``services.task_manager._start_in_main_thread``). Im
          ``_do_work`` über ``self.task_id`` lesbar — wichtig für
          B-047-Pattern (project_manager.create_project(task_id=...)).

        Subklassen-Beispiel:

        .. code-block:: python

            class MyWorker(BaseWorker):
                def __init__(self, foo: str):
                    super().__init__()
                    self.foo = foo

                def _do_work(self):
                    # Tu was, optional self.progress.emit(50, 'mid')
                    if self.should_stop():
                        return None  # Cancel
                    return {'result': self.foo}
        """
        finished = _Signal(object)
        error = _Signal(str)
        progress = _Signal(int, str)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # task_id wird vom TaskManager nach moveToThread gesetzt
            self.task_id: str | None = None

        def _do_work(self):
            """Subklassen überschreiben hier. Rückgabewert geht an finished()."""
            raise NotImplementedError(
                f"{self.__class__.__name__}._do_work() not implemented"
            )

        def run(self) -> None:
            """Entry-Point. NICHT überschreiben — das macht die ganze
            Lifecycle-Verwaltung kaputt. Stattdessen ``_do_work``.
            """
            ok = False
            payload = None
            try:
                payload = self._do_work()
                ok = True
            except Exception as exc:  # noqa: BLE001 — top-level safety net
                self._errored = True
                msg = format_user_error(exc)
                logger.exception(
                    "%s.run() failed: %s", self.__class__.__name__, msg,
                )
                try:
                    self.error.emit(msg)
                except RuntimeError:
                    pass  # Worker bereits deleteLater'd
            finally:
                try:
                    if ok:
                        self.finished.emit(payload)
                    else:
                        # Auch bei Error: finished feuern damit Cleanup-
                        # Caller (TaskManager._safe_cleanup) ihren Hook
                        # bekommen.
                        self.finished.emit(None)
                except RuntimeError:
                    pass
else:
    # Headless / no-PySide6 Fallback. BaseWorker existiert nicht — wer
    # ihn importiert ohne Qt verfügbar bekommt einen klaren ImportError.
    class BaseWorker:  # type: ignore[no-redef]
        """Stub: PySide6 nicht installiert."""
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "BaseWorker benötigt PySide6 — Qt-Application-Kontext fehlt."
            )
