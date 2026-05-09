"""Sub-Tab 'Audio' im SCHNITT-Editor: Waveform + Stems + LUFS + Key.

Plan-Abweichung (Phase 07): Plan referenziert ``StemWorkspaceWidget`` —
real heisst die Klasse im Repo ``StemWorkspace`` (siehe
``ui/widgets/stem_workspace.py``). Konsistent zum Plan-Abweichungs-Pattern
der Phasen 01-06 (z.B. ``DBSession`` -> ``Session``) wird der reale
Klassenname verwendet.
"""
from PySide6.QtCore import Qt, QLineF
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsView, QGraphicsScene,
)
from ui.widgets.stem_workspace import StemWorkspace


class SchnittTabAudio(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._audio_id: int | None = None
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(6)

        # Waveform mit Beatgrid + Strukturmarker
        self.waveform_view = QGraphicsView()
        self.waveform_view.setMinimumHeight(120)
        self.waveform_view.setMaximumHeight(160)
        self.waveform_view.setScene(QGraphicsScene())
        self.waveform_view.setToolTip(
            "Waveform mit Beatgrid und Strukturmarkern (Intro/Drop/Outro)."
        )
        v.addWidget(self.waveform_view)

        # Stems-Mixer (Plan: StemWorkspaceWidget; Repo: StemWorkspace)
        self.stem_workspace = StemWorkspace()
        v.addWidget(self.stem_workspace, stretch=1)

        # Footer-Row: LUFS + Key
        footer = QHBoxLayout()
        self.lufs_label = QLabel("LUFS: —")
        self.lufs_label.setStyleSheet("color:#9ca3af; font-size:11px;")
        footer.addWidget(self.lufs_label)
        footer.addStretch(1)
        self.key_label = QLabel("Tonart: —")
        self.key_label.setStyleSheet("color:#9ca3af; font-size:11px;")
        footer.addWidget(self.key_label)
        v.addLayout(footer)

    def set_lufs(self, lufs_value: float | None) -> None:
        if lufs_value is None:
            self.lufs_label.setText("LUFS: —")
        else:
            self.lufs_label.setText(f"LUFS: {lufs_value:.1f}")

    def set_key(self, key_text: str | None, camelot: str | None = None) -> None:
        if not key_text:
            self.key_label.setText("Tonart: —")
            return
        if camelot:
            self.key_label.setText(f"Tonart: {key_text} ({camelot})")
        else:
            self.key_label.setText(f"Tonart: {key_text}")

    def render_grid_lines(self, beat_times: list[float], pixels_per_second: float = 50.0) -> None:
        scene = self.waveform_view.scene()
        scene.clear()
        pen_beat = QPen(QColor(180, 200, 230, 90), 1)
        height = self.waveform_view.height() or 120
        for t in beat_times:
            x = t * pixels_per_second
            scene.addLine(QLineF(x, 0, x, height), pen_beat)

    def set_audio_id(self, audio_id: int | None) -> None:
        self._audio_id = audio_id
        self.waveform_view.scene().clear()
        if audio_id is None:
            return
        # Beatgrid-Rendering aus DB folgt im Controller (Phase 09 Worker).
