"""Resource Monitor Widget — shows CPU / RAM / GPU VRAM in the status bar."""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QProgressBar
from PySide6.QtCore import QTimer

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
        "QProgressBar {"
        "  background: #23242d; border: none; border-radius: 3px;"
        "  min-width: 50px; max-width: 50px; min-height: 8px; max-height: 8px;"
        "}"
        f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
    )


_LABEL_STYLE = "color: #909090; font-size: 10px; padding: 0 2px;"


class ResourceMonitorWidget(QWidget):
    """Lightweight CPU / RAM / GPU VRAM monitor for the status bar.

    Updates every 3 seconds via QTimer. If *psutil* or *torch* are not
    installed the corresponding bar simply stays at 0 %.
    """

    _UPDATE_INTERVAL_MS = 3000

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
        self._cpu_bar.setStyleSheet(_bar_style("#00e5ff"))
        layout.addWidget(self._cpu_label)
        layout.addWidget(self._cpu_bar)

        # -- RAM --
        self._ram_label = QLabel("RAM 0/0 GB")
        self._ram_label.setStyleSheet(_LABEL_STYLE)
        self._ram_bar = QProgressBar()
        self._ram_bar.setRange(0, 100)
        self._ram_bar.setValue(0)
        self._ram_bar.setTextVisible(False)
        self._ram_bar.setStyleSheet(_bar_style("#4ade80"))
        layout.addWidget(self._ram_label)
        layout.addWidget(self._ram_bar)

        # -- GPU VRAM --
        self._gpu_label = QLabel("GPU 0/0 GB")
        self._gpu_label.setStyleSheet(_LABEL_STYLE)
        self._gpu_bar = QProgressBar()
        self._gpu_bar.setRange(0, 100)
        self._gpu_bar.setValue(0)
        self._gpu_bar.setTextVisible(False)
        self._gpu_bar.setStyleSheet(_bar_style("#facc15"))  # gold default
        layout.addWidget(self._gpu_label)
        layout.addWidget(self._gpu_bar)

        # -- Timer --
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update)
        self._timer.start(self._UPDATE_INTERVAL_MS)

        # Initial read
        self._update()

    # ------------------------------------------------------------------
    def _update(self):
        """Poll system metrics (lightweight — runs on UI thread)."""
        self._update_cpu()
        self._update_ram()
        self._update_gpu()

    # ------------------------------------------------------------------
    def _update_cpu(self):
        if _HAS_PSUTIL:
            pct = psutil.cpu_percent(interval=None)
        else:
            pct = 0
        pct = int(pct)
        self._cpu_bar.setValue(pct)
        self._cpu_label.setText(f"CPU {pct}%")

    # ------------------------------------------------------------------
    def _update_ram(self):
        if _HAS_PSUTIL:
            mem = psutil.virtual_memory()
            used_gb = mem.used / (1024 ** 3)
            total_gb = mem.total / (1024 ** 3)
            pct = int(mem.percent)
        else:
            used_gb = total_gb = 0.0
            pct = 0
        self._ram_bar.setValue(pct)
        self._ram_label.setText(f"RAM {used_gb:.1f}/{total_gb:.1f}")

    # ------------------------------------------------------------------
    def _update_gpu(self):
        if _HAS_TORCH and torch.cuda.is_available():
            try:
                idx = torch.cuda.current_device()
                used = torch.cuda.memory_allocated(idx) / (1024 ** 3)
                total = torch.cuda.get_device_properties(idx).total_memory / (1024 ** 3)
                pct = int((used / total) * 100) if total > 0 else 0
            except Exception:
                used = total = 0.0
                pct = 0
        else:
            used = total = 0.0
            pct = 0

        # Color: gold when <70%, orange-red when >=70%
        if pct >= 70:
            color = "#f97316"  # warn orange
        else:
            color = "#facc15"  # gold
        self._gpu_bar.setStyleSheet(_bar_style(color))
        self._gpu_bar.setValue(pct)
        self._gpu_label.setText(f"GPU {used:.1f}/{total:.1f}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def stop(self):
        """Stop the background polling timer."""
        self._timer.stop()

    def start(self):
        """(Re-)start the background polling timer."""
        if not self._timer.isActive():
            self._timer.start(self._UPDATE_INTERVAL_MS)

    # ------------------------------------------------------------------
    # Visibility-aware timer management
    # ------------------------------------------------------------------
    def hideEvent(self, event):
        """Stop polling when the widget is hidden."""
        self._timer.stop()
        super().hideEvent(event)

    def showEvent(self, event):
        """Restart polling when the widget becomes visible."""
        if not self._timer.isActive():
            self._timer.start(self._UPDATE_INTERVAL_MS)
        super().showEvent(event)
