"""Resource Monitor Widget — shows CPU / RAM / GPU VRAM in the status bar."""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot

from ui.theme import ACCENT, BG2, INFO_CYAN, OK, T3, WARN

# ---------------------------------------------------------------------------
# Optional dependencies — graceful fallback
# ---------------------------------------------------------------------------
try:
    import psutil  # type: ignore
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

try:
    import torch  # type: ignore
    _HAS_TORCH = True
except ImportError:
    _HAS_TORCH = False


def _bar_style(color: str) -> str:
    """Return a minimal QProgressBar stylesheet for the given accent color."""
    return (
        f"QProgressBar {{"
        f"  background: {BG2}; border: none; border-radius: 3px;"
        "  min-width: 50px; max-width: 50px; min-height: 8px; max-height: 8px;"
        "}"
        f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
    )


_LABEL_STYLE = f"color: {T3}; font-size: 10px; padding: 0 2px;"


_POLL_INTERVAL_MS = 3000  # 3 seconds between polls


class _MonitorWorker(QObject):
    """Collects CPU/RAM/GPU metrics via QTimer (non-blocking).

    K-012 Fix: Replaced blocking while-loop with QTimer so the thread's
    event-loop stays alive and thread.quit() works reliably.
    """

    updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self._timer: QTimer | None = None

    @Slot()
    def start_polling(self):
        """Called once the worker's thread is running.  Starts the QTimer."""
        self._timer = QTimer()
        self._timer.setInterval(_POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._collect)
        self._timer.start()
        # fire immediately so first values appear without waiting
        self._collect()

    @Slot()
    def stop(self):
        """Stop the timer (safe to call from any thread via QMetaObject)."""
        if self._timer is not None:
            self._timer.stop()

    def _collect(self):
        stats: dict = {}
        # CPU
        if _HAS_PSUTIL:
            stats['cpu'] = int(psutil.cpu_percent())
        # RAM
        if _HAS_PSUTIL:
            mem = psutil.virtual_memory()
            stats['ram_used'] = mem.used / (1024 ** 3)
            stats['ram_total'] = mem.total / (1024 ** 3)
            stats['ram_pct'] = int(mem.percent)
        # GPU
        if _HAS_TORCH and torch.cuda.is_available():
            try:
                idx = torch.cuda.current_device()
                stats['gpu_used'] = torch.cuda.memory_allocated(idx) / (1024 ** 3)
                stats['gpu_total'] = torch.cuda.get_device_properties(idx).total_memory / (1024 ** 3)
                stats['gpu_pct'] = (
                    int((stats['gpu_used'] / stats['gpu_total']) * 100)
                    if stats['gpu_total'] > 0
                    else 0
                )
            except Exception:
                pass  # GPU stats are non-critical
        self.updated.emit(stats)


class ResourceMonitorWidget(QWidget):
    """Lightweight CPU / RAM / GPU VRAM monitor for the status bar.

    F-032 Fix: Polling runs in a background thread to prevent UI stutter.
    K-012 Fix: Worker uses QTimer instead of blocking while-loop.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        # -- CPU --
        self._cpu_label = QLabel("CPU 0%")
        self._cpu_label.setStyleSheet(_LABEL_STYLE)
        self._cpu_bar = QProgressBar()
        self._cpu_bar.setRange(0, 100)
        self._cpu_bar.setValue(0)
        self._cpu_bar.setTextVisible(False)
        self._cpu_bar.setStyleSheet(_bar_style(INFO_CYAN))
        layout.addWidget(self._cpu_label)
        layout.addWidget(self._cpu_bar)

        # -- RAM --
        self._ram_label = QLabel("RAM 0/0 GB")
        self._ram_label.setStyleSheet(_LABEL_STYLE)
        self._ram_bar = QProgressBar()
        self._ram_bar.setRange(0, 100)
        self._ram_bar.setValue(0)
        self._ram_bar.setTextVisible(False)
        self._ram_bar.setStyleSheet(_bar_style(OK))
        layout.addWidget(self._ram_label)
        layout.addWidget(self._ram_bar)

        # -- GPU VRAM --
        self._gpu_label = QLabel("GPU 0/0 GB")
        self._gpu_label.setStyleSheet(_LABEL_STYLE)
        self._gpu_bar = QProgressBar()
        self._gpu_bar.setRange(0, 100)
        self._gpu_bar.setValue(0)
        self._gpu_bar.setTextVisible(False)
        self._gpu_bar.setStyleSheet(_bar_style(ACCENT))
        layout.addWidget(self._gpu_label)
        layout.addWidget(self._gpu_bar)

        # Background Worker for polling
        self._worker = _MonitorWorker()
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._worker.updated.connect(self._on_stats_updated)
        self._thread.started.connect(self._worker.start_polling)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_stats_updated(self, stats: dict):
        """Update UI with stats from background thread."""
        if 'cpu' in stats:
            self._cpu_bar.setValue(stats['cpu'])
            self._cpu_label.setText(f"CPU {stats['cpu']}%")
        
        if 'ram_pct' in stats:
            self._ram_bar.setValue(stats['ram_pct'])
            self._ram_label.setText(f"RAM {stats['ram_used']:.1f}/{stats['ram_total']:.1f}")
            
        if 'gpu_pct' in stats:
            pct = stats['gpu_pct']
            color = WARN if pct >= 70 else ACCENT
            self._gpu_bar.setStyleSheet(_bar_style(color))
            self._gpu_bar.setValue(pct)
            self._gpu_label.setText(f"GPU {stats.get('gpu_used', 0.0):.1f}/{stats.get('gpu_total', 0.0):.1f}")

    def stop(self):
        """K-012 / B-036 Fix: Graceful shutdown — stop timer, then quit event-loop."""
        if self._worker:
            self._worker.stop()  # stops the QTimer
        if self._thread and self._thread.isRunning():
            self._thread.quit()   # exits the thread's event-loop (now works!)
            self._thread.wait(5000)

    def start(self):
        if not self._thread.isRunning():
            self._thread.start()
