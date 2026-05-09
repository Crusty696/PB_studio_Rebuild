"""Sub-Tab 'Audio' im SCHNITT-Editor: Waveform + Stems + LUFS + Key.

Plan-Abweichung (Phase 07): Plan referenziert ``StemWorkspaceWidget`` -
real heisst die Klasse im Repo ``StemWorkspace`` (siehe
``ui/widgets/stem_workspace.py``). Konsistent zum Plan-Abweichungs-Pattern
der Phasen 01-06 (z.B. ``DBSession`` -> ``Session``) wird der reale
Klassenname verwendet.

Plan-Abweichung Tier 2 (T2.1): Plan referenziert
``audio_analysis.waveform_json/beats_json/structure_json`` -- real
existieren ``WaveformData.band_low/band_mid/band_high`` +
``Beatgrid.beat_positions`` + ``StructureSegment``-Rows. Die Methoden
hier verwenden die realen Felder.
"""
from PySide6.QtCore import Qt, QLineF, QRectF
from PySide6.QtGui import QColor, QPen, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsView, QGraphicsScene,
    QGraphicsRectItem, QGraphicsSimpleTextItem,
)

from ui.waveform_item import WaveformGraphicsItem
from ui.widgets.stem_workspace import StemWorkspace


# Zentrale Pixels-per-Second-Konstante (Tier-2 T2.4).
# Genutzt von render_grid_lines, set_structure_markers und
# set_waveform_data. Aenderung an einer Stelle aendert alle
# Renderpfade konsistent.
_PIXELS_PER_SECOND: float = 50.0


# Strukturmarker-Farbpalette (Tier-2 T2.2). Spec-Mapping:
# Intro/Drop/Outro/Buildup/Breakdown.
_STRUCTURE_COLORS: dict[str, str] = {
    "intro": "#3b82f6",
    "drop": "#ef4444",
    "outro": "#6b7280",
    "buildup": "#f59e0b",
    "breakdown": "#a855f7",
}


class SchnittTabAudio(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._audio_id: int | None = None
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(6)

        # Header-Row (Tier-2 T2.3): LUFS + Tonart rechts oben.
        header = QHBoxLayout()
        header.addStretch(1)
        self.lufs_label = QLabel("LUFS: —")
        self.lufs_label.setStyleSheet("color:#9ca3af; font-size:11px;")
        header.addWidget(self.lufs_label)
        self.key_label = QLabel("Tonart: —")
        self.key_label.setStyleSheet("color:#9ca3af; font-size:11px;")
        header.addWidget(self.key_label)
        v.addLayout(header)

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
            # Spec: "Cm — 7A" mit Em-Dash (Tier-2 T2.5).
            self.key_label.setText(f"Tonart: {key_text} — {camelot}")
        else:
            self.key_label.setText(f"Tonart: {key_text}")

    def render_grid_lines(
        self,
        beat_times: list[float],
        pixels_per_second: float = _PIXELS_PER_SECOND,
    ) -> None:
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
        # DB-Lookup macht der Controller; er ruft danach
        # set_waveform_data(...) und set_structure_markers(...) auf.

    def set_waveform_data(
        self,
        waveform_row,
        beat_positions: list[float] | None = None,
        height: float = 100.0,
    ) -> None:
        """Bindet ein WaveformGraphicsItem an die Scene (Tier-2 T2.1).

        Plan-Abweichung: Plan-Felder ``waveform_json``/``beats_json``
        existieren nicht. Stattdessen werden die realen Felder der
        ``WaveformData``-Row (``band_low``/``band_mid``/``band_high``/
        ``duration``) und die ``Beatgrid.beat_positions`` als Liste
        durchgereicht.
        """
        scene = self.waveform_view.scene()
        scene.clear()
        if waveform_row is None:
            return

        item = WaveformGraphicsItem.from_db_data(
            waveform_row,
            beat_positions_json=beat_positions or [],
            pixels_per_second=_PIXELS_PER_SECOND,
            height=height,
        )
        scene.addItem(item)

    def set_structure_markers(self, markers: list[dict]) -> None:
        """Rendert Strukturmarker (Intro/Drop/Outro/Buildup/Breakdown).

        Tier-2 T2.2. ``markers``: Liste von Dicts mit Keys
        ``start`` (float, sec), ``end`` (float, sec), ``label`` (str).
        Unbekannte Labels bekommen einen neutralen Default-Ton.
        """
        if not markers:
            return
        scene = self.waveform_view.scene()
        height = self.waveform_view.height() or 120
        # Marker liegen ueber der Waveform mit reduzierter Hoehe.
        marker_h = max(16.0, height * 0.25)

        font = QFont()
        font.setPointSize(8)

        for m in markers:
            try:
                start = float(m["start"])
                end = float(m["end"])
                label = str(m["label"])
            except (KeyError, TypeError, ValueError):
                continue
            if end <= start:
                continue

            x = start * _PIXELS_PER_SECOND
            w = (end - start) * _PIXELS_PER_SECOND
            color_hex = _STRUCTURE_COLORS.get(label.lower(), "#9ca3af")
            color = QColor(color_hex)

            rect = QGraphicsRectItem(QRectF(x, 0.0, w, marker_h))
            fill = QColor(color)
            fill.setAlpha(110)
            rect.setBrush(QBrush(fill))
            border = QPen(color, 1)
            rect.setPen(border)
            scene.addItem(rect)

            text = QGraphicsSimpleTextItem(label)
            text.setFont(font)
            text.setBrush(QBrush(QColor("#ffffff")))
            text.setPos(x + 2.0, 1.0)
            scene.addItem(text)
