"""Debug/test background workers."""

import time as _t

from PySide6.QtCore import QObject, Signal

from .base import CancellableMixin


class DummyProgressWorker(QObject, CancellableMixin):
    """Test-Worker: Zaehlt 10 Sekunden hoch fuer UI-Test der Task-Engine."""
    finished = Signal(int, int)   # (done_steps, total_steps)
    error = Signal(str)
    progress = Signal(int, str)   # (percent, message)

    def __init__(self, steps: int = 10, interval_ms: int = 1000):
        super().__init__()
        self.steps = steps
        self.interval_s = interval_ms / 1000.0

    def run(self):
        _ok = False
        try:
            for i in range(1, self.steps + 1):
                if self.should_stop():
                    self.progress.emit(0, "Abgebrochen")
                    break
                pct = int(100 * i / self.steps)
                self.progress.emit(pct, f"Schritt {i}/{self.steps}")
                _t.sleep(self.interval_s)
            self.finished.emit(self.steps, self.steps)
            _ok = True
        except Exception as e:
            self._errored = True
            self.error.emit(str(e))
        finally:
            if not _ok and not self._errored:
                self.finished.emit(0, 0)
