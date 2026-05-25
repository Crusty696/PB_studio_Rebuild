"""AI Status Dot — kleiner Statusindikator für den ChatDock-Header.

Grün (#2ECC71) = AI bereit, Gelb (#F39C12) = Verbindung wird geprüft.
Kein Backend-Name im Tooltip; nur allgemeiner AI-Verfuegbarkeitsstatus.
"""

import logging
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import QTimer, QThread, QObject, Signal, Slot, Qt

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
        """Called once the worker's thread is running.  Starts the QTimer.

        P8-FREEZE-FIX: _poll() ruft synchron Ollama-HTTP mit 2s Timeout.
        Wenn start_polling durch Race-Condition im Main-Thread laeuft
        (Auto-Connection kann DirectConnection werden), blockiert das
        den UI-Event-Loop. Fix: ersten Poll per QTimer.singleShot(0, ...)
        absetzen — das garantiert Ausfuehrung im *worker* Event-Loop.
        """
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.setInterval(_POLL_INTERVAL_MS)
            self._timer.timeout.connect(self._poll)
        
        if not self._timer.isActive():
            self._timer.start()
            # Erster Poll deferred — MUSS im Worker-Event-Loop laufen
            QTimer.singleShot(0, self._poll)

    @Slot()
    def stop(self):
        """Stop the timer (safe to call from any thread via QMetaObject)."""
        if self._timer is not None and self._timer.isActive():
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
        # P8-FREEZE-FIX: explizit QueuedConnection, damit start_polling
        # und _poll NIEMALS im Main-Thread laufen koennen. Auto-Connection
        # hat in einem Race-Fenster DirectConnection geliefert → Main-Thread
        # hing in socket.create_connection() fuer 2s pro Poll-Cycle.
        self._worker.result.connect(self._on_poll_result, Qt.ConnectionType.QueuedConnection)
        self._thread.started.connect(self._worker.start_polling, Qt.ConnectionType.QueuedConnection)
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
            self.setToolTip(self.tr("AI-Verfuegbarkeit: bereit fuer Chat- und Assistenzfunktionen."))
        else:
            self.setToolTip(self.tr("AI-Verfuegbarkeit: wird im Hintergrund geprueft."))

    def _invoke_worker_stop(self):
        """Stoppt den Worker-Timer thread-safe via QueuedConnection.

        QTimer darf nur aus dem Owner-Thread gestoppt werden.
        QMetaObject.invokeMethod mit QueuedConnection stellt sicher,
        dass stop() im Worker-Thread laeuft.
        """
        if self._worker and self._thread and self._thread.isRunning():
            # invokeMethod queued: laeuft im Worker-Thread Event-Loop
            from PySide6.QtCore import QMetaObject, Qt as QtConst
            QMetaObject.invokeMethod(
                self._worker, "stop", QtConst.ConnectionType.QueuedConnection
            )

    def hideEvent(self, event):
        """Polling stoppen wenn Widget versteckt (Tab-Wechsel)."""
        self._invoke_worker_stop()
        super().hideEvent(event)

    def showEvent(self, event):
        """Polling wieder starten wenn Widget sichtbar wird."""
        if self._worker and self._thread and self._thread.isRunning():
            from PySide6.QtCore import QMetaObject, Qt as QtConst
            QMetaObject.invokeMethod(
                self._worker, "start_polling", QtConst.ConnectionType.QueuedConnection
            )
        super().showEvent(event)

    def closeEvent(self, event):
        """K-013 / B-036 Fix: Cleanup beim Schliessen des Widgets/Fensters."""
        self.stop()
        super().closeEvent(event)

    def stop(self) -> None:
        """Stop the polling thread before the owning window is destroyed."""
        self._invoke_worker_stop()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(500)
