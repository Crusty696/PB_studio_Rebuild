"""Resource Monitor Widget — shows CPU / RAM / GPU VRAM in the status bar."""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import QTimer

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


class ResourceMonitorWidget(QWidget):
    """Lightweight CPU / RAM / GPU VRAM monitor for the status bar.

    F-032 Fix: Polling runs in a background thread to prevent UI stutter.
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
        from PySide6.QtCore import QThread, QObject, Signal

        class MonitorWorker(QObject):
            updated = Signal(dict)

            def __init__(self):
                super().__init__()
                self._running = True  # B-036 Fix: Graceful shutdown flag

            def stop(self):
                """Signal worker to stop gracefully."""
                self._running = False

            def run(self):
                import time
                while self._running:  # B-036 Fix: Check flag instead of infinite loop
                    stats = {}
                    # CPU
                    if _HAS_PSUTIL: stats['cpu'] = int(psutil.cpu_percent())
                    # RAM
                    if _HAS_PSUTIL:
                        mem = psutil.virtual_memory()
                        stats['ram_used'] = mem.used / (1024**3)
                        stats['ram_total'] = mem.total / (1024**3)
                        stats['ram_pct'] = int(mem.percent)
                    # GPU
                    if _HAS_TORCH and torch.cuda.is_available():
                        try:
                            idx = torch.cuda.current_device()
                            stats['gpu_used'] = torch.cuda.memory_allocated(idx) / (1024**3)
                            stats['gpu_total'] = torch.cuda.get_device_properties(idx).total_memory / (1024**3)
                            stats['gpu_pct'] = int((stats['gpu_used'] / stats['gpu_total']) * 100) if stats['gpu_total'] > 0 else 0
                        except Exception:  # B-035 Fix: Specify exception type (was bare except)
                            pass  # broad catch intentional — GPU stats are non-critical, failure OK

                    if self._running:  # Check before emit
                        self.updated.emit(stats)

                    # B-036 Fix: Sleep in small chunks for faster shutdown response
                    for _ in range(30):  # 3 seconds = 30 × 100ms
                        if not self._running:
                            break
                        time.sleep(0.1)

        self._worker = MonitorWorker()
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._worker.updated.connect(self._on_stats_updated)
        self._thread.started.connect(self._worker.run)
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
        """B-036 Fix: Graceful shutdown instead of terminate()."""
        if self._worker:
            self._worker.stop()  # Signal worker to stop
        if self._thread and self._thread.isRunning():
            self._thread.quit()   # Request event loop exit
            self._thread.wait(5000)  # Wait up to 5 seconds

    def start(self):
        if not self._thread.isRunning():
            self._thread.start()
