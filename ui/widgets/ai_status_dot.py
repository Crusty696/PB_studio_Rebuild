"""AI Status Dot — kleiner Statusindikator für den ChatDock-Header.

Grün (#2ECC71) = AI bereit, Gelb (#F39C12) = wird geladen.
Kein Ollama/Gemma in Tooltips — nur "AI: bereit" / "AI: wird geladen...".
"""

from PySide6.QtWidgets import QLabel
from PySide6.QtCore import QTimer


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


class AiStatusDot(QLabel):
    """Kleines Ampel-Dot-Widget das den AI-Verfügbarkeitsstatus anzeigt.
    
    F-033 Fix: Polling runs in a background thread to prevent UI stutter.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ready = False
        self._apply_style()

        from PySide6.QtCore import QThread, QObject, Signal
        
        class PollWorker(QObject):
            result = Signal(bool)
            def run(self):
                import time
                while True:
                    try:
                        from services.ollama_client import OllamaClient
                        ready = OllamaClient().is_available()
                    except Exception:  # B-035 Fix: broad catch intentional — import/network errors expected
                        ready = False
                    self.result.emit(ready)
                    time.sleep(5)

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
