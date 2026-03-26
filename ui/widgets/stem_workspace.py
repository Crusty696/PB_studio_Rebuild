"""STEMS Workspace — DAW-Style 4-Track Stem View mit Wellenformen.

Zeigt 4 horizontale Track-Bänder (Vocals, Drums, Bass, Other) mit:
- Echtzeit-Wellenform via QPainter (Peak-Downsampling in QThread)
- Mute-Button + Volume-Slider pro Track
- Globale Master-Zeitleiste (Play/Pause/Stop, Seek-Slider, Zeitanzeige)

Performance: Aggressives Downsampling für 1h+ DJ-Mixes.
Peak-Daten werden in einem Worker-Thread berechnet und gecacht.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

logger = logging.getLogger(__name__)

import numpy as np
from PySide6.QtCore import Qt, Signal, QThread, QObject
from PySide6.QtCore import QLine
from PySide6.QtGui import QPainter, QColor, QPen, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QScrollBar, QSizePolicy, QFrame,
)


# ── Stem-Konfiguration ──
STEM_CONFIG = {
    "vocals": {"color": "#E91E63", "label": "VOCALS"},
    "drums":  {"color": "#FF9800", "label": "DRUMS"},
    "bass":   {"color": "#00E676", "label": "BASS"},
    "other":  {"color": "#42A5F5", "label": "OTHER"},
}
STEM_ORDER = ["vocals", "drums", "bass", "other"]

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
# Einzelner Stem-Track (Label + Controls + Waveform)
# =====================================================================

class StemTrackWidget(QWidget):
    """Ein horizontaler Track-Streifen: [Controls | Waveform]"""

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

        # ── Linke Controls-Spalte (fix 200px) — DAW Track Header ──
        controls = QWidget()
        controls.setFixedWidth(200)
        controls.setObjectName("stem_track_controls")
        controls.setStyleSheet(
            f"#stem_track_controls {{ background: #161616; "
            f"border-right: 2px solid {color}; }}"
        )
        ctrl_layout = QVBoxLayout(controls)
        ctrl_layout.setContentsMargins(10, 6, 10, 6)
        ctrl_layout.setSpacing(6)

        # ── Row 1: Track Label (links) + Mute/Solo Buttons (rechts) ──
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        name_label = QLabel(label)
        name_label.setStyleSheet(
            f"color: {color}; font-weight: 800; font-size: 13px; "
            "background: transparent; border: none; letter-spacing: 1px;"
        )
        name_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        top_row.addWidget(name_label)
        top_row.addStretch()

        # Mute Button
        self._mute_btn = QPushButton("M")
        self._mute_btn.setFixedSize(28, 22)
        self._mute_btn.setCheckable(True)
        self._mute_btn.setToolTip(f"{label} stumm schalten")
        self._mute_btn.setObjectName("stem_mute_btn")
        self._mute_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: #1E1E1E;
                color: #606060;
                border: 1px solid #2E2E2E;
                border-radius: 3px;
                font-weight: 700;
                font-size: 10px;
            }}
            QPushButton:checked {{
                background: #CC3333;
                color: #FFFFFF;
                border: 1px solid #EE4444;
            }}
            QPushButton:hover {{
                border-color: {color};
            }}
            """
        )
        self._mute_btn.toggled.connect(
            lambda checked: self.mute_toggled.emit(self._stem_name, checked)
        )
        top_row.addWidget(self._mute_btn)

        # Solo Button
        self._solo_btn = QPushButton("S")
        self._solo_btn.setFixedSize(28, 22)
        self._solo_btn.setCheckable(True)
        self._solo_btn.setToolTip(f"{label} solo")
        self._solo_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: #1E1E1E;
                color: #606060;
                border: 1px solid #2E2E2E;
                border-radius: 3px;
                font-weight: 700;
                font-size: 10px;
            }}
            QPushButton:checked {{
                background: #D4AF37;
                color: #0E0E0E;
                border: 1px solid #E8CC6A;
            }}
            QPushButton:hover {{
                border-color: {color};
            }}
            """
        )
        top_row.addWidget(self._solo_btn)
        ctrl_layout.addLayout(top_row)

        # ── Row 2: Volume Slider + dB ──
        vol_row = QHBoxLayout()
        vol_row.setSpacing(4)

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(100)
        self._vol_slider.setFixedHeight(16)
        self._vol_slider.setToolTip(f"{label} Lautstärke")
        self._vol_slider.setStyleSheet(
            f"""
            QSlider::groove:horizontal {{
                background: #252525;
                height: 4px;
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {color};
                width: 12px;
                height: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }}
            QSlider::sub-page:horizontal {{
                background: {color};
                border-radius: 2px;
                opacity: 0.6;
            }}
            """
        )
        self._vol_slider.valueChanged.connect(
            lambda v: self.volume_changed.emit(self._stem_name, v)
        )
        vol_row.addWidget(self._vol_slider)

        self._db_label = QLabel("0 dB")
        self._db_label.setFixedWidth(42)
        self._db_label.setStyleSheet(
            "color: #606060; font-size: 9px; background: transparent; border: none;"
        )
        self._db_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._vol_slider.valueChanged.connect(self._update_db)
        vol_row.addWidget(self._db_label)

        ctrl_layout.addLayout(vol_row)
        ctrl_layout.addStretch()

        layout.addWidget(controls)

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
    def solo_btn(self) -> QPushButton:
        return self._solo_btn

    @property
    def is_muted(self) -> bool:
        """[I-05 FIX] Public API statt direktem Zugriff auf _mute_btn."""
        return self._mute_btn.isChecked()

    def set_enabled_state(self, enabled: bool):
        """Aktiviert/Deaktiviert den Track wenn kein Stem vorhanden."""
        self._mute_btn.setEnabled(enabled)
        self._solo_btn.setEnabled(enabled)
        self._vol_slider.setEnabled(enabled)
        if not enabled:
            self._waveform.set_peaks(np.zeros((0, 2), dtype=np.float32))

    def reset(self):
        self._vol_slider.setValue(100)
        self._mute_btn.setChecked(False)
        self._solo_btn.setChecked(False)

    def _update_db(self, value: int):
        if value == 0:
            self._db_label.setText("-∞ dB")
        else:
            db = 20 * math.log10(value / 100)
            self._db_label.setText(f"{db:.1f} dB")


# =====================================================================
# Master Transport Bar
# =====================================================================

class TransportBar(QWidget):
    """Globale Zeitleiste: Play/Pause, Stop, Seek-Slider, Zeitanzeige."""

    play_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    seek_requested = Signal(float)  # Sekunden

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setObjectName("stem_transport_bar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        btn_style = (
            "QPushButton { background: #1E1E1E; color: #A0A0A0; "
            "border: 1px solid #2E2E2E; border-radius: 4px; "
            "font-size: 14px; font-weight: 700; padding: 4px 10px; }"
            "QPushButton:hover { color: #D0D0D0; border-color: #484848; background: #282828; }"
            "QPushButton:disabled { color: #303030; }"
        )

        # Stop
        self._btn_stop = QPushButton("\u25A0")
        self._btn_stop.setFixedSize(36, 36)
        self._btn_stop.setToolTip("Stop")
        self._btn_stop.setStyleSheet(btn_style)
        self._btn_stop.clicked.connect(self.stop_requested)
        layout.addWidget(self._btn_stop)

        # Play/Pause
        self._btn_play = QPushButton("\u25B6")
        self._btn_play.setFixedSize(36, 36)
        self._btn_play.setToolTip("Play / Pause")
        self._btn_play.setStyleSheet(btn_style)
        self._btn_play.clicked.connect(self._on_play_clicked)
        layout.addWidget(self._btn_play)

        # Zeitanzeige links
        self._time_current = QLabel("0:00")
        self._time_current.setFixedWidth(70)
        self._time_current.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._time_current.setStyleSheet(
            "color: #C0C0C0; font-size: 13px; font-weight: 700; "
            "font-family: monospace; background: transparent; border: none;"
        )
        layout.addWidget(self._time_current)

        # Seek Slider
        self._pos_slider = QSlider(Qt.Orientation.Horizontal)
        self._pos_slider.setRange(0, 10000)
        self._pos_slider.setValue(0)
        self._pos_slider.setToolTip("Position")
        self._pos_slider.setObjectName("stem_seek_slider")
        self._pos_slider.setStyleSheet(
            "QSlider::groove:horizontal { background: #252525; height: 6px; border-radius: 3px; }"
            "QSlider::handle:horizontal { background: #808080; width: 14px; height: 14px; "
            "margin: -4px 0; border-radius: 7px; }"
            "QSlider::sub-page:horizontal { background: #484848; border-radius: 3px; }"
        )
        self._pos_slider.sliderPressed.connect(self._on_seek_start)
        self._pos_slider.sliderReleased.connect(self._on_seek_end)
        self._seeking = False
        layout.addWidget(self._pos_slider, stretch=1)

        # Zeitanzeige rechts (Gesamtdauer)
        self._time_total = QLabel("0:00")
        self._time_total.setFixedWidth(70)
        self._time_total.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._time_total.setStyleSheet(
            "color: #606060; font-size: 13px; font-weight: 500; "
            "font-family: monospace; background: transparent; border: none;"
        )
        layout.addWidget(self._time_total)

        # Zoom-Kontrolle
        layout.addSpacing(16)

        zoom_label = QLabel("Zoom:")
        zoom_label.setStyleSheet(
            "color: #505050; font-size: 10px; background: transparent; border: none;"
        )
        layout.addWidget(zoom_label)

        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setRange(10, 500)  # 1.0x - 50.0x
        self._zoom_slider.setValue(10)
        self._zoom_slider.setFixedWidth(100)
        self._zoom_slider.setToolTip("Waveform Zoom")
        self._zoom_slider.setStyleSheet(
            "QSlider::groove:horizontal { background: #252525; height: 4px; border-radius: 2px; }"
            "QSlider::handle:horizontal { background: #555555; width: 8px; height: 8px; "
            "margin: -2px 0; border-radius: 4px; }"
        )
        layout.addWidget(self._zoom_slider)

        self._zoom_label = QLabel("1.0x")
        self._zoom_label.setFixedWidth(35)
        self._zoom_label.setStyleSheet(
            "color: #505050; font-size: 9px; background: transparent; border: none;"
        )
        layout.addWidget(self._zoom_label)

        # State
        self._duration: float = 0.0
        self._is_playing = False

    @property
    def zoom_slider(self) -> QSlider:
        return self._zoom_slider

    @property
    def zoom_label(self) -> QLabel:
        return self._zoom_label

    def set_duration(self, duration: float):
        self._duration = duration
        self._time_total.setText(self._fmt_time(duration))

    def update_position(self, seconds: float):
        if self._seeking:
            return
        self._time_current.setText(self._fmt_time(seconds))
        if self._duration > 0:
            ratio = seconds / self._duration
            self._pos_slider.setValue(int(ratio * 10000))

    def update_playback_state(self, state: str):
        self._is_playing = (state == "playing")
        self._btn_play.setText("\u23F8" if self._is_playing else "\u25B6")
        self._btn_play.setToolTip("Pause" if self._is_playing else "Play")

    def _on_play_clicked(self):
        if self._is_playing:
            self.pause_requested.emit()
        else:
            self.play_requested.emit()

    def _on_seek_start(self):
        self._seeking = True

    def _on_seek_end(self):
        self._seeking = False
        if self._duration > 0:
            ratio = self._pos_slider.value() / 10000.0
            self.seek_requested.emit(ratio * self._duration)

    @staticmethod
    def _fmt_time(s: float) -> str:
        total = max(0, int(s))
        h, rest = divmod(total, 3600)
        m, sec = divmod(rest, 60)
        if h > 0:
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m}:{sec:02d}"


# =====================================================================
# Haupt-Widget: StemWorkspace
# =====================================================================

class StemWorkspace(QWidget):
    """Kompletter STEMS Workspace mit 4 Track-Bändern und Transport.

    Signals (zum Verbinden mit StemPlayer):
        stem_volume_changed(stem_name, value)
        stem_mute_toggled(stem_name, is_muted)
        play_requested()
        pause_requested()
        stop_requested()
        seek_requested(float)  — Sekunden
    """

    stem_volume_changed = Signal(str, int)
    stem_mute_toggled = Signal(str, bool)
    play_requested = Signal()
    pause_requested = Signal()
    stop_requested = Signal()
    seek_requested = Signal(float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("stem_workspace")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──
        header = QWidget()
        header.setFixedHeight(36)
        header.setObjectName("stem_workspace_header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 0, 12, 0)

        title = QLabel("STEM TRACKS")
        title.setStyleSheet(
            "color: #A0A0A0; font-weight: 700; font-size: 13px; "
            "background: transparent; border: none;"
        )
        header_layout.addWidget(title)

        header_layout.addStretch()

        self._info_label = QLabel("Kein Track geladen")
        self._info_label.setStyleSheet(
            "color: #505050; font-size: 11px; background: transparent; border: none;"
        )
        header_layout.addWidget(self._info_label)

        header_layout.addSpacing(16)

        btn_reset = QPushButton("Reset All")
        btn_reset.setFixedHeight(24)
        btn_reset.setStyleSheet(
            "QPushButton { background: #1E1E1E; color: #606060; border: 1px solid #2E2E2E; "
            "border-radius: 3px; font-size: 10px; padding: 2px 10px; }"
            "QPushButton:hover { color: #B0B0B0; border-color: #484848; }"
        )
        btn_reset.clicked.connect(self._reset_all)
        header_layout.addWidget(btn_reset)

        layout.addWidget(header)

        # Trennlinie
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #222222;")
        layout.addWidget(sep)

        # ── 4 Track-Bänder ──
        tracks_container = QWidget()
        tracks_layout = QVBoxLayout(tracks_container)
        tracks_layout.setContentsMargins(0, 0, 0, 0)
        tracks_layout.setSpacing(0)

        self._tracks: dict[str, StemTrackWidget] = {}
        for name in STEM_ORDER:
            cfg = STEM_CONFIG[name]
            track = StemTrackWidget(name, cfg["color"], cfg["label"], self)
            track.volume_changed.connect(self.stem_volume_changed)
            track.mute_toggled.connect(self._on_mute_toggled)
            track.seek_requested.connect(self._on_waveform_seek)
            track.solo_btn.toggled.connect(
                lambda checked, n=name: self._on_solo_toggled(n, checked)
            )
            tracks_layout.addWidget(track, stretch=1)
            self._tracks[name] = track

        layout.addWidget(tracks_container, stretch=1)

        # ── Horizontal Scrollbar ──
        self._h_scroll = QScrollBar(Qt.Orientation.Horizontal)
        self._h_scroll.setRange(0, 0)
        self._h_scroll.setFixedHeight(14)
        self._h_scroll.setStyleSheet(
            "QScrollBar:horizontal { background: #121212; height: 14px; margin: 0; }"
            "QScrollBar::handle:horizontal { background: #303030; min-width: 30px; "
            "border-radius: 3px; margin: 2px; }"
            "QScrollBar::handle:horizontal:hover { background: #484848; }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }"
        )
        self._h_scroll.valueChanged.connect(self._on_scroll)
        layout.addWidget(self._h_scroll)

        # ── Transport Bar ──
        self._transport = TransportBar(self)
        self._transport.play_requested.connect(self.play_requested)
        self._transport.pause_requested.connect(self.pause_requested)
        self._transport.stop_requested.connect(self.stop_requested)
        self._transport.seek_requested.connect(self.seek_requested)
        self._transport.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        layout.addWidget(self._transport)

        # ── State ──
        self._duration: float = 0.0
        self._current_track_id: int | None = None
        self._peak_threads: list[QThread] = []
        self._peak_workers: list[PeakWorker] = []
        self._solo_active: set[str] = set()

    # ── Public API ──

    def update_for_track(self, track_id: int | None,
                         stem_paths: dict[str, str | None] | None = None):
        """Aktualisiert alle 4 Tracks für einen neuen AudioTrack."""
        self._current_track_id = track_id
        self._cleanup_peak_threads()

        if track_id is None or stem_paths is None:
            self._info_label.setText("Kein Track geladen")
            for track in self._tracks.values():
                track.set_enabled_state(False)
            return

        available = {k: v for k, v in stem_paths.items() if v and Path(v).exists()}
        if not available:
            self._info_label.setText("Keine Stems vorhanden")
            for track in self._tracks.values():
                track.set_enabled_state(False)
            return

        self._info_label.setText(f"Track #{track_id} — {len(available)}/4 Stems")

        for name, track in self._tracks.items():
            if name in available:
                track.set_enabled_state(True)
                track.waveform.set_loading(True)
                self._start_peak_generation(name, available[name])
            else:
                track.set_enabled_state(False)

    def set_duration(self, duration: float):
        """Setzt die Track-Dauer für Transport und Waveforms."""
        self._duration = duration
        self._transport.set_duration(duration)

    def update_position(self, seconds: float):
        """Aktualisiert Playhead-Position in allen Waveforms und Transport."""
        self._transport.update_position(seconds)
        if self._duration > 0:
            ratio = seconds / self._duration
            for track in self._tracks.values():
                track.waveform.set_playhead(ratio)

    def update_playback_state(self, state: str):
        """Aktualisiert Play-Button basierend auf Player-State."""
        self._transport.update_playback_state(state)

    @property
    def current_track_id(self) -> int | None:
        return self._current_track_id

    # ── Interne Logik ──

    def _start_peak_generation(self, stem_name: str, file_path: str):
        """Startet Peak-Berechnung in einem Worker-Thread."""
        thread = QThread()
        worker = PeakWorker(stem_name, file_path)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_peaks_ready)
        worker.error.connect(self._on_peaks_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        # GC-FIX: Starke Referenzen halten bis thread wirklich fertig ist.
        # _remove_finished_thread() wird via finished-Signal aufgerufen —
        # erst dann werden die Python-Wrapper-Objekte freigegeben.
        # (verhindert "Internal C++ object already deleted" wenn quit() async läuft)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread, w=worker: self._remove_finished_thread(t, w))

        self._peak_threads.append(thread)
        self._peak_workers.append(worker)

        thread.start()

    def _remove_finished_thread(self, thread: QThread, worker: "PeakWorker"):
        """Entfernt einen fertigen Thread/Worker aus den Tracking-Listen.

        Wird via thread.finished aufgerufen — zu diesem Zeitpunkt ist der
        C++ QThread noch gültig (deleteLater steht erst in der Queue).
        """
        try:
            self._peak_threads.remove(thread)
        except ValueError:
            pass
        try:
            self._peak_workers.remove(worker)
        except ValueError:
            pass

    def _on_peaks_ready(self, stem_name: str, peaks: np.ndarray):
        """Callback wenn Peak-Daten fertig sind."""
        if stem_name in self._tracks:
            self._tracks[stem_name].waveform.set_peaks(peaks)

    def _on_peaks_error(self, stem_name: str, error_msg: str):
        """Callback bei Fehler in der Peak-Berechnung."""
        logger.warning("[StemWorkspace] Peak-Fehler bei %s: %s", stem_name, error_msg)
        if stem_name in self._tracks:
            self._tracks[stem_name].waveform.set_loading(False)

    def _cleanup_peak_threads(self):
        """Beendet laufende Peak-Threads.

        GC-FIX: KEIN clear() der Listen hier — Python würde sonst die
        Wrapper-Objekte sofort freigeben, während der C++ QThread noch läuft.
        Stattdessen: cancel + quit, und _remove_finished_thread() räumt
        die Listen auf sobald das thread.finished-Signal eintrifft.
        """
        for worker in list(self._peak_workers):
            worker.cancel()
        for thread in list(self._peak_threads):
            if thread.isRunning():
                thread.quit()

    def _on_mute_toggled(self, stem_name: str, muted: bool):
        """Mute-Signal weiterleiten."""
        self.stem_mute_toggled.emit(stem_name, muted)

    def _on_solo_toggled(self, stem_name: str, checked: bool):
        """Solo-Logik: Nur der Solo-Track ist hörbar, alle anderen muted."""
        if checked:
            self._solo_active.add(stem_name)
        else:
            self._solo_active.discard(stem_name)

        if self._solo_active:
            # Mute alle die NICHT solo sind
            for name, track in self._tracks.items():
                should_mute = name not in self._solo_active
                self.stem_mute_toggled.emit(name, should_mute)
        else:
            # Kein Solo aktiv → alle Mutes zurücksetzen (respektiere Mute-Buttons)
            for name, track in self._tracks.items():
                self.stem_mute_toggled.emit(name, track.is_muted)

    def _on_waveform_seek(self, ratio: float):
        """Klick in eine Waveform → Seek in Sekunden."""
        if self._duration > 0:
            self.seek_requested.emit(ratio * self._duration)

    def _on_zoom_changed(self, value: int):
        """Zoom-Slider geändert → alle Waveforms aktualisieren."""
        zoom = value / 10.0
        self._transport.zoom_label.setText(f"{zoom:.1f}x")

        for track in self._tracks.values():
            track.waveform.set_zoom(zoom)

        # Scrollbar-Range anpassen
        if zoom > 1.0:
            max_scroll = int((1.0 - 1.0 / zoom) * 10000)
            self._h_scroll.setRange(0, max_scroll)
            self._h_scroll.setPageStep(int(10000 / zoom))
        else:
            self._h_scroll.setRange(0, 0)

    def _on_scroll(self, value: int):
        """Scrollbar geändert → alle Waveforms scrollen."""
        max_val = self._h_scroll.maximum()
        if max_val > 0:
            offset = value / max_val
        else:
            offset = 0.0
        for track in self._tracks.values():
            track.waveform.set_scroll(offset)

    def _reset_all(self):
        """Alle Tracks zurücksetzen."""
        self._solo_active.clear()
        for track in self._tracks.values():
            track.reset()

    def closeEvent(self, event):
        """Cleanup beim Schließen der StemWorkspace — Bug #26 Fix"""
        # Disconnect signals wenn noch verbunden
        try:
            # Main Workspace signals
            self.stem_volume_changed.disconnect()
            self.stem_mute_toggled.disconnect()
            self.play_requested.disconnect()
            self.pause_requested.disconnect()
            self.stop_requested.disconnect()
            self.seek_requested.disconnect()
        except (TypeError, RuntimeError):
            pass

        # Cleanup Peak Worker threads
        try:
            if hasattr(self, '_peak_threads'):
                for thread in self._peak_threads:
                    thread.quit()
                    thread.wait(1000)
        except (TypeError, RuntimeError):
            pass

        super().closeEvent(event)

