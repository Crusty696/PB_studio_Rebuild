"""Stem Track Widget — Einzelner Stem-Track mit Waveform-Anzeige.

Enthält:
- PeakWorker: Berechnet Peak-Daten aus WAV-Dateien im Background-Thread
- WaveformWidget: Zeichnet eine Stem-Wellenform via QPainter
- StemTrackWidget: Horizontaler Track-Streifen [StemMixerPanel | WaveformWidget]

Performance: Aggressives Downsampling für 1h+ DJ-Mixes.
Peak-Daten werden in einem Worker-Thread berechnet und gecacht.
"""

from __future__ import annotations

import logging

import numpy as np
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtCore import QLine
from PySide6.QtGui import QPainter, QColor, QPen, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QSizePolicy,
)

from .stem_mixer_panel import StemMixerPanel

logger = logging.getLogger(__name__)

# Peak-Auflösung: max Peaks pro Waveform-Cache
PEAKS_TARGET = 8000  # Genug für Full-HD Breite, wenig genug für Speed


# =====================================================================
# Peak-Generator Worker (QThread)
# =====================================================================

class PeakWorker(QObject):
    """Berechnet Peak-Daten aus WAV-Dateien in einem Background-Thread.

    Liest die Datei chunk-weise und berechnet min/max Peaks pro Segment.
    Ergebnis: numpy array (N, 2) mit [min_peak, max_peak] pro Segment.
    """
    finished = Signal(str, object)  # (stem_name, peaks_array)
    error = Signal(str, str)        # (stem_name, error_msg)

    def __init__(self, stem_name: str, file_path: str, target_peaks: int = PEAKS_TARGET):
        super().__init__()
        self._stem_name = stem_name
        self._file_path = file_path
        self._target_peaks = target_peaks
        self._cancelled = False  # [I-04 FIX] Cancellation-Flag

    def cancel(self):
        """Signalisiert dem Worker, die Berechnung abzubrechen."""
        self._cancelled = True

    def run(self):
        try:
            import soundfile as sf

            with sf.SoundFile(self._file_path, mode="r") as f:
                total_frames = f.frames
                channels = f.channels

                if total_frames == 0:
                    self.finished.emit(self._stem_name, np.zeros((0, 2), dtype=np.float32))
                    return

                frames_per_peak = max(1, total_frames // self._target_peaks)
                actual_peaks = (total_frames + frames_per_peak - 1) // frames_per_peak

                peaks = np.zeros((actual_peaks, 2), dtype=np.float32)

                chunk_size = frames_per_peak * 4
                peak_idx = 0
                frames_in_segment = 0
                seg_min = 0.0
                seg_max = 0.0

                f.seek(0)
                remaining = total_frames

                while remaining > 0 and peak_idx < actual_peaks:
                    # [I-04 FIX] Check cancellation between chunks
                    if self._cancelled:
                        return

                    read_n = min(chunk_size, remaining)
                    chunk = f.read(read_n, dtype="float32", always_2d=True)
                    if chunk.shape[0] == 0:
                        break
                    remaining -= chunk.shape[0]

                    if channels > 1:
                        mono = chunk.mean(axis=1)
                    else:
                        mono = chunk[:, 0]

                    offset = 0
                    while offset < len(mono) and peak_idx < actual_peaks:
                        need = frames_per_peak - frames_in_segment
                        end = min(offset + need, len(mono))
                        segment = mono[offset:end]

                        if len(segment) == 0:
                            break

                        if frames_in_segment == 0:
                            seg_min = segment.min()
                            seg_max = segment.max()
                        else:
                            seg_min = min(seg_min, segment.min())
                            seg_max = max(seg_max, segment.max())

                        frames_in_segment += len(segment)
                        offset = end

                        if frames_in_segment >= frames_per_peak:
                            peaks[peak_idx, 0] = seg_min
                            peaks[peak_idx, 1] = seg_max
                            peak_idx += 1
                            frames_in_segment = 0
                            seg_min = 0.0
                            seg_max = 0.0

                if self._cancelled:
                    return

                if frames_in_segment > 0 and peak_idx < actual_peaks:
                    peaks[peak_idx, 0] = seg_min
                    peaks[peak_idx, 1] = seg_max
                    peak_idx += 1

                peaks = peaks[:peak_idx]
                self.finished.emit(self._stem_name, peaks)

        except Exception as e:
            if not self._cancelled:
                self.error.emit(self._stem_name, str(e))


# =====================================================================
# Waveform Widget (QPainter, horizontales Band)
# =====================================================================

class WaveformWidget(QWidget):
    """Zeichnet eine einzelne Stem-Wellenform als horizontales Band.

    Bekommt Peak-Daten (N, 2) mit [min, max] und zeichnet diese
    als vertikale Linien um die Mittellinie. Unterstützt Zoom und Scroll.
    """

    clicked_position = Signal(float)  # Relative Position 0.0-1.0

    def __init__(self, color: str = "#808080", parent: QWidget | None = None):
        super().__init__(parent)
        self._peaks: np.ndarray | None = None
        self._color = QColor(color)
        self._color_dim = QColor(color)
        self._color_dim.setAlpha(120)
        self._playhead_pos: float = 0.0  # 0.0 - 1.0
        self._zoom: float = 1.0
        self._scroll_offset: float = 0.0  # 0.0 - 1.0 (Scroll-Position)
        self._loading = False
        self._no_data = True

        self.setMinimumHeight(60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    def set_peaks(self, peaks: np.ndarray):
        """Setzt die Peak-Daten und triggert Repaint."""
        self._peaks = peaks
        self._no_data = (peaks is None or len(peaks) == 0)
        self._loading = False
        self.update()

    def set_loading(self, loading: bool):
        self._loading = loading
        self._no_data = True
        self.update()

    def set_playhead(self, ratio: float):
        """Setzt die Playhead-Position (0.0-1.0)."""
        self._playhead_pos = max(0.0, min(1.0, ratio))
        self.update()

    def set_zoom(self, zoom: float):
        self._zoom = max(1.0, min(50.0, zoom))
        self.update()

    def set_scroll(self, offset: float):
        self._scroll_offset = max(0.0, min(1.0, offset))
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._peaks is not None:
            # Klick → Position berechnen
            w = self.width()
            visible_fraction = 1.0 / self._zoom
            x_ratio = event.position().x() / w
            global_ratio = self._scroll_offset + x_ratio * visible_fraction
            global_ratio = max(0.0, min(1.0, global_ratio))
            self.clicked_position.emit(global_ratio)

    def paintEvent(self, event):
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Background
        painter.fillRect(0, 0, w, h, QColor(14, 14, 14))

        if self._loading:
            painter.setPen(QColor(80, 80, 80))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Peaks werden berechnet...")
            painter.end()
            return

        if self._no_data or self._peaks is None or len(self._peaks) == 0:
            painter.setPen(QColor(50, 50, 50))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Keine Wellenform")
            painter.end()
            return

        peaks = self._peaks
        num_peaks = len(peaks)
        half_h = h / 2.0

        # Zoom & Scroll: welcher Bereich ist sichtbar?
        visible_fraction = 1.0 / self._zoom
        start_ratio = self._scroll_offset
        end_ratio = min(1.0, start_ratio + visible_fraction)

        start_idx = int(start_ratio * num_peaks)
        end_idx = min(num_peaks, int(end_ratio * num_peaks) + 1)
        visible_peaks = end_idx - start_idx

        if visible_peaks <= 0:
            painter.end()
            return

        # Zeichne Wellenform: Eine vertikale Linie pro Pixel
        # Wenn mehr Peaks als Pixel → Downsampling (max/min)
        # Wenn weniger Peaks als Pixel → Stretching

        color = self._color
        pen = QPen(color, 1)
        painter.setPen(pen)

        # [I-03 FIX] Batch drawLines() statt einzelner drawLine() Aufrufe
        lines: list[QLine] = []

        if visible_peaks <= w:
            for i in range(visible_peaks):
                x = int(i * w / visible_peaks)
                p = peaks[start_idx + i]
                y_min = int(half_h - p[1] * half_h)
                y_max = int(half_h - p[0] * half_h)
                lines.append(QLine(x, y_min, x, y_max))
        else:
            for px in range(w):
                p_start = start_idx + int(px * visible_peaks / w)
                p_end = start_idx + int((px + 1) * visible_peaks / w)
                p_end = min(p_end, end_idx)
                if p_start >= p_end:
                    continue
                seg = peaks[p_start:p_end]
                lo = seg[:, 0].min()
                hi = seg[:, 1].max()
                y_min = int(half_h - hi * half_h)
                y_max = int(half_h - lo * half_h)
                lines.append(QLine(px, y_min, px, y_max))

        if lines:
            painter.drawLines(lines)

        # Mittellinie (dezent)
        painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
        painter.drawLine(0, int(half_h), w, int(half_h))

        # Playhead
        if 0.0 <= self._playhead_pos <= 1.0:
            ph_in_visible = (self._playhead_pos - start_ratio) / visible_fraction
            if 0.0 <= ph_in_visible <= 1.0:
                px = int(ph_in_visible * w)
                painter.setPen(QPen(QColor(255, 255, 255, 200), 2))
                painter.drawLine(px, 0, px, h)

        painter.end()


# =====================================================================
# Einzelner Stem-Track (MixerPanel + Waveform)
# =====================================================================

class StemTrackWidget(QWidget):
    """Ein horizontaler Track-Streifen: [StemMixerPanel | WaveformWidget]"""

    volume_changed = Signal(str, int)   # (stem_name, 0-100)
    mute_toggled = Signal(str, bool)    # (stem_name, is_muted)
    seek_requested = Signal(float)      # ratio 0.0-1.0

    def __init__(self, stem_name: str, color: str, label: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._stem_name = stem_name
        self._color = color

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(0)

        # ── Linke Controls-Spalte via StemMixerPanel ──
        self._mixer = StemMixerPanel(stem_name, color, label, self)
        self._mixer.volume_changed.connect(self.volume_changed)
        self._mixer.mute_toggled.connect(self.mute_toggled)

        # Expose internal buttons directly — StemWorkspace._on_solo_toggled
        # calls blockSignals() on _mute_btn directly for flicker-free updates.
        self._mute_btn = self._mixer._mute_btn
        self._solo_btn = self._mixer._solo_btn

        layout.addWidget(self._mixer)

        # ── Waveform (nimmt den ganzen Rest ein) ──
        self._waveform = WaveformWidget(color, self)
        self._waveform.clicked_position.connect(self.seek_requested)
        layout.addWidget(self._waveform, stretch=1)

        self.setStyleSheet(
            "StemTrackWidget { background: #141414; border-bottom: 1px solid #222222; }"
        )

    @property
    def stem_name(self) -> str:
        return self._stem_name

    @property
    def waveform(self) -> WaveformWidget:
        return self._waveform

    @property
    def solo_btn(self) -> "QPushButton":  # noqa: F821
        return self._solo_btn

    @property
    def is_muted(self) -> bool:
        """[I-05 FIX] Public API statt direktem Zugriff auf _mute_btn."""
        return self._mixer.is_muted

    def set_enabled_state(self, enabled: bool):
        """Aktiviert/Deaktiviert den Track wenn kein Stem vorhanden."""
        self._mixer.set_enabled_state(enabled)
        if not enabled:
            self._waveform.set_peaks(np.zeros((0, 2), dtype=np.float32))

    def reset(self):
        self._mixer.reset()
