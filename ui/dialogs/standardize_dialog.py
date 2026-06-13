"""StandardizeVideosDialog — modaler Ziel-Format-Dialog (B-525).

Profi-Pattern (Premiere "Create Proxies", DaVinci Optimized-Media-Settings):
Aufloesung/Framerate/Container/Copy werden NICHT inline in die enge
Material-&-Analyse-Spalte gequetscht (das verursachte die Layout-Ueberlappung
B-525), sondern in einem eigenen modalen Dialog gewaehlt, der per Button im
Video-Pool ausgeloest wird.

``selected()`` liefert (resolution_text, fps_text, format_text) — exakt die
Strings, die ``ConvertController._run_standardize`` erwartet.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QLabel,
    QDialogButtonBox,
)


# Identisch zu den frueheren Inline-Combos in convert_workspace.py, plus der
# B-525-Copy-Option.
_RESOLUTIONS = [
    "1920x1080 (1080p)", "2560x1440 (2K)", "3840x2160 (4K)", "1280x720 (720p)",
]
_FRAMERATES = ["30 fps", "24 fps", "25 fps", "50 fps", "60 fps"]
_FORMATS = [
    "mp4 (H.264)", "mp4 (H.265/HEVC)", "mov (ProRes)", "mkv (H.264)",
    "mp4 (Kopieren/Copy)",
]


class StandardizeVideosDialog(QDialog):
    """Modaler Dialog zur Auswahl des Ziel-Formats fuer die Standardisierung."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Videos standardisieren")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        intro = QLabel(
            "Alle Videos im Pool auf ein gemeinsames Ziel-Format konvertieren. "
            "Die Originaldateien bleiben unveraendert."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.setSpacing(8)

        self.convert_resolution = QComboBox()
        self.convert_resolution.addItems(_RESOLUTIONS)
        self.convert_resolution.setToolTip(
            "Ziel-Aufloesung fuer die Standardisierung aller Videos im Pool."
        )
        form.addRow("Aufloesung:", self.convert_resolution)

        self.convert_fps = QComboBox()
        self.convert_fps.addItems(_FRAMERATES)
        self.convert_fps.setToolTip(
            "Ziel-Framerate. Einheitliche FPS vermeiden Ruckler in Timeline und Export."
        )
        form.addRow("Framerate:", self.convert_fps)

        self.convert_format = QComboBox()
        self.convert_format.addItems(_FORMATS)
        self.convert_format.setToolTip(
            "Codec/Container. H.264 ist kompatibel, HEVC kleiner, ProRes "
            "schnittfreundlich. 'Kopieren/Copy' re-encodet nicht (Stream-Copy)."
        )
        form.addRow("Container:", self.convert_format)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Konvertieren starten")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected(self) -> tuple[str, str, str]:
        """(resolution_text, fps_text, format_text) der aktuellen Auswahl."""
        return (
            self.convert_resolution.currentText(),
            self.convert_fps.currentText(),
            self.convert_format.currentText(),
        )
