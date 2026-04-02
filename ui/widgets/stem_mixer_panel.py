"""Stem Mixer Panel — Volume, Mute, Solo Controls für einen einzelnen Stem-Track.

Kapselt die linke 200px-Kontrollspalte des StemTrackWidget:
Track-Label, Mute-Button, Solo-Button, Volume-Slider mit dB-Anzeige.
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider,
)


class StemMixerPanel(QWidget):
    """Linke Controls-Spalte (200px) eines Stem-Tracks.

    Enthält: Track-Label (farbig), Mute-Button, Solo-Button, Volume-Slider + dB.
    """

    volume_changed = Signal(str, int)   # (stem_name, 0-100)
    mute_toggled = Signal(str, bool)    # (stem_name, is_muted)

    def __init__(self, stem_name: str, color: str, label: str,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._stem_name = stem_name
        self._color = color

        self.setFixedWidth(200)
        self.setObjectName("stem_track_controls")
        self.setStyleSheet(
            f"#stem_track_controls {{ background: #161616; "
            f"border-right: 2px solid {color}; }}"
        )

        ctrl_layout = QVBoxLayout(self)
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

    @property
    def solo_btn(self) -> QPushButton:
        return self._solo_btn

    @property
    def is_muted(self) -> bool:
        """[I-05 FIX] Public API statt direktem Zugriff auf _mute_btn."""
        return self._mute_btn.isChecked()

    def set_enabled_state(self, enabled: bool):
        """Aktiviert/Deaktiviert die Controls wenn kein Stem vorhanden."""
        self._mute_btn.setEnabled(enabled)
        self._solo_btn.setEnabled(enabled)
        self._vol_slider.setEnabled(enabled)

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
