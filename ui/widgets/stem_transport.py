"""Stem Transport Bar — Play/Pause/Stop, Seek-Slider, Zeitanzeige, Zoom.

Globale Transport-Controls für den STEMS Workspace.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QSlider,
)


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
        self._btn_stop.setAccessibleName("Stems Stop")
        self._btn_stop.setStatusTip("Stem-Wiedergabe stoppen und zum Anfang zurueckspringen")
        self._btn_stop.setStyleSheet(btn_style)
        self._btn_stop.clicked.connect(self.stop_requested)
        layout.addWidget(self._btn_stop)

        # Play/Pause
        self._btn_play = QPushButton("\u25B6")
        self._btn_play.setFixedSize(36, 36)
        self._btn_play.setToolTip("Play / Pause")
        self._btn_play.setAccessibleName("Stems Play / Pause")
        self._btn_play.setStatusTip("Stem-Wiedergabe starten oder pausieren")
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
        self._pos_slider.setAccessibleName("Wiedergabe-Position")
        self._pos_slider.setStatusTip("Wiedergabe-Position in der Stem-Spur")
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
        self._zoom_slider.setAccessibleName("Waveform Zoom")
        self._zoom_slider.setStatusTip("Zoomstufe der Stem-Wellenform anpassen (1.0x bis 50.0x)")
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
