"""AI Status Dot — kleiner Statusindikator für den ChatDock-Header.

Grün (#2ECC71) = AI bereit, Gelb (#F39C12) = wird geladen.
Kein Ollama/Gemma in Tooltips — nur "AI: bereit" / "AI: wird geladen...".
"""

import logging
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import QTimer, QThread, QObject, Signal, Slot

logger = logging.getLogger(__name__)

_COLOR_READY = "#2ECC71"
_COLOR_LOADING = "#F39C12"
_POLL_INTERVAL_MS = 5000  # 5 seconds between polls

_DOT_STYLE = (
    "QLabel {{"
    "  background-color: {color};"
    "  border-radius: 5px;"
    "  min-width: 10px; max-width: 10px;"
    "  min-height: 10px; max-height: 10px;"
    "}}"
)


class PollWorker(QObject):
    """Worker fuer das Polling im Hintergrund.

    K-013 Fix: Replaced blocking while-loop with QTimer so the thread's
    event-loop stays alive and thread.quit() works reliably.
    """

    result = Signal(bool)

    def __init__(self):
        super().__init__()
        self._timer: QTimer | None = None

    @Slot()
    def start_polling(self):
        """Called once the worker's thread is running.  Starts the QTimer."""
        self._timer = QTimer()
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        # fire immediately so the dot updates without waiting
        self._poll()

    @Slot()
    def stop(self):
        """Stop the timer (safe to call from any thread via QMetaObject)."""
        if self._timer is not None:
            self._timer.stop()

    def _poll(self):
        try:
            from services.ollama_client import get_ollama_client
            ready = get_ollama_client().is_available()
        except Exception as e:
            logger.debug("AiStatusDot Poll Error: %s", e)
            ready = False
        self.result.emit(ready)


class AiStatusDot(QLabel):
    """Kleines Ampel-Dot-Widget das den AI-Verfuegbarkeitsstatus anzeigt.

    F-033 Fix: Polling runs in a background thread to prevent UI stutter.
    K-013 Fix: Worker uses QTimer instead of blocking while-loop.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ready = False
        self._apply_style()

        self._worker = PollWorker()
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._worker.result.connect(self._on_poll_result)
        self._thread.started.connect(self._worker.start_polling)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_poll_result(self, ready: bool):
        if ready != self._ready:
            self._ready = ready
            self._apply_style()

    def _apply_style(self) -> None:
        color = _COLOR_READY if self._ready else _COLOR_LOADING
        self.setStyleSheet(_DOT_STYLE.format(color=color))
        if self._ready:
            self.setToolTip(self.tr("AI: bereit"))
        else:
            self.setToolTip(self.tr("AI: wird geladen..."))

    def closeEvent(self, event):
        """K-013 / B-036 Fix: Cleanup beim Schliessen des Widgets/Fensters."""
        if self._worker:
            self._worker.stop()  # stops the QTimer
        if self._thread and self._thread.isRunning():
            self._thread.quit()   # exits the thread's event-loop (now works!)
            self._thread.wait(5000)
        super().closeEvent(event)
