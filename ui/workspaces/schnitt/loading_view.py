"""Loading-State der SCHNITT-Workspace mit rotierendem Status-Text + Progress."""
import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QProgressBar, QPushButton, QHBoxLayout,
)


_STAGE_TEXT = {
    "audio_load": "Lade Audio…",
    "beat_grid": "Bestimme Beatgrid…",
    "structure": "Erkenne Songstruktur…",
    "cut_calc": "Setze Schnitte…",
    "clip_select": "Wähle Clips aus…",
    "anchor_sync": "Synchronisiere Anker…",
    "db_write": "Speichere Timeline…",
}


class SchnittLoadingView(QWidget):
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("schnitt_loading")
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 80, 40, 80)
        layout.setSpacing(16)
        layout.addStretch(1)

        title = QLabel("Auto-Edit läuft…")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: 800; color: #f9fafb;")
        layout.addWidget(title)

        self.status_label = QLabel("Vorbereiten…")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: #d4a44a; font-size: 14px;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        layout.addWidget(self.progress_bar)

        cancel_row = QHBoxLayout()
        cancel_row.addStretch(1)
        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_cancel.setFixedHeight(26)
        self.btn_cancel.clicked.connect(self.cancel_requested)
        cancel_row.addWidget(self.btn_cancel)
        cancel_row.addStretch(1)
        layout.addLayout(cancel_row)

        layout.addStretch(2)

    def set_stage(self, stage_key: str, fraction: float) -> None:
        self.status_label.setText(_STAGE_TEXT.get(stage_key, "Vorbereiten…"))
        # T4.6: NaN-Defense — int(NaN) wuerde ValueError werfen.
        if fraction is None or math.isnan(fraction):
            fraction = 0.0
        self.progress_bar.setValue(int(max(0.0, min(1.0, fraction)) * 100))

    def reset(self) -> None:
        self.status_label.setText("Vorbereiten…")
        self.progress_bar.setValue(0)
