"""AI Status Dot — kleiner Statusindikator für den ChatDock-Header.

Grün (#2ECC71) = AI bereit, Gelb (#F39C12) = wird geladen.
Kein Ollama/Gemma in Tooltips — nur "AI: bereit" / "AI: wird geladen...".
"""

import logging
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import QTimer, QThread, QObject, Signal

logger = logging.getLogger(__name__)

_COLOR_READY = "#2ECC71"
_COLOR_LOADING = "#F39C12"

_DOT_STYLE = (
    "QLabel {{"
    "  background-color: {color};"
    "  border-radius: 5px;"
    "  min-width: 10px; max-width: 10px;"
    "  min-height: 10px; max-height: 10px;"
    "}}"
)


class PollWorker(QObject):
    """Worker für das Polling im Hintergrund."""
    result = Signal(bool)
    
    def __init__(self):
        super().__init__()
        self._running = True

    def stop(self):
        """Signalisiert dem Worker, dass er stoppen soll."""
        self._running = False

    def run(self):
        import time
        while self._running:
            try:
                from services.ollama_client import get_ollama_client
                # Wir nutzen das Singleton um unnötige Instanziierungen zu vermeiden
                ready = get_ollama_client().is_available()
            except Exception as e:
                # B-035 Fix: Intentional broad catch for network/import errors
                logger.debug("AiStatusDot Poll Error: %s", e)
                ready = False
            
            if self._running:
                self.result.emit(ready)
                
            # Schlafen in kleinen Häppchen für schnelleres Beenden
            for _ in range(50): # 5 Sekunden total
                if not self._running: break
                time.sleep(0.1)


class AiStatusDot(QLabel):
    """Kleines Ampel-Dot-Widget das den AI-Verfügbarkeitsstatus anzeigt.
    
    F-033 Fix: Polling runs in a background thread to prevent UI stutter.
    B-036 Fix: Graceful shutdown via closeEvent and stop-flag.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ready = False
        self._apply_style()

        self._worker = PollWorker()
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._worker.result.connect(self._on_poll_result)
        self._thread.started.connect(self._worker.run)
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
        """B-036 Fix: Cleanup beim Schließen des Widgets/Fensters."""
        if self._worker:
            self._worker.stop()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(1000)
        super().closeEvent(event)
