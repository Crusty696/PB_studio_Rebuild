"""Usability shell around the SCHNITT timeline."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.timeline import InteractiveTimeline


class TimelineShell(QWidget):
    """Timeline plus visible zoom, status and legend controls."""

    def __init__(self, timeline: InteractiveTimeline | None = None, parent=None):
        super().__init__(parent)
        self.timeline = timeline or InteractiveTimeline()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)

        self.status_label = QLabel("Timeline bereit")
        self.status_label.setObjectName("schnitt_timeline_status")
        self.status_label.setStyleSheet("color: #cbd5e1; font-size: 12px; font-weight: 600;")
        toolbar.addWidget(self.status_label)

        toolbar.addStretch(1)

        self.legend_label = QLabel("A1 Audio | V1 Video | Marker: Beats/Anker")
        self.legend_label.setObjectName("schnitt_timeline_legend")
        self.legend_label.setToolTip(
            "Wirkung: Erklaert die Spuren und Marker in der Timeline. "
            "Wann: Nutze es zur Orientierung beim Schneiden und Zoomen. "
            "Ergebnis: A1 ist Master-Audio, V1 sind Video-Clips, Marker zeigen Beats/Anker."
        )
        self.legend_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        toolbar.addWidget(self.legend_label)

        self.zoom_label = QLabel("Zoom 100%")
        self.zoom_label.setObjectName("schnitt_timeline_zoom_label")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setMinimumWidth(86)
        self.zoom_label.setStyleSheet("color: #cbd5e1; font-size: 12px; font-weight: 600;")
        toolbar.addWidget(self.zoom_label)

        self.btn_zoom_out = self._button(
            "-",
            "Timeline herauszoomen",
            "Wirkung: Zeigt mehr Zeit auf einmal. Wann: Nutze es fuer Ueberblick ueber lange Edits. Ergebnis: Clips werden horizontal schmaler, A1/V1 bleiben gleich hoch.",
        )
        self.btn_zoom_fit = self._button(
            "Fit",
            "Timeline auf Inhalt einpassen",
            "Wirkung: Passt die komplette Timeline horizontal in den sichtbaren Bereich. Wann: Nutze es nach Auto-Edit oder Import. Ergebnis: Zeitachse wird eingepasst, Spuren bleiben lesbar.",
        )
        self.btn_zoom_reset = self._button(
            "1:1",
            "Timeline-Zoom auf 100 Prozent zuruecksetzen",
            "Wirkung: Setzt den Zoom auf Normalansicht. Wann: Nutze es nach starkem Zoomen. Ergebnis: Ein stabiler Arbeitszoom ohne vertikale Spur-Skalierung.",
        )
        self.btn_zoom_in = self._button(
            "+",
            "Timeline hineinzoomen",
            "Wirkung: Zeigt mehr Detail pro Sekunde. Wann: Nutze es fuer genaue Cuts und Anker. Ergebnis: Clips werden horizontal breiter, A1/V1 bleiben gleich hoch.",
        )

        for button in (
            self.btn_zoom_out,
            self.btn_zoom_fit,
            self.btn_zoom_reset,
            self.btn_zoom_in,
        ):
            toolbar.addWidget(button)

        layout.addLayout(toolbar)
        layout.addWidget(self.timeline, stretch=1)

        self.btn_zoom_out.clicked.connect(lambda: self._zoom_by(1 / 1.15))
        self.btn_zoom_in.clicked.connect(lambda: self._zoom_by(1.15))
        self.btn_zoom_fit.clicked.connect(self._fit_to_content)
        self.btn_zoom_reset.clicked.connect(self._reset_zoom)

    def _button(self, text: str, label: str, tooltip: str) -> QPushButton:
        button = QPushButton(text)
        button.setMinimumSize(48, 36)
        button.setToolTip(tooltip)
        button.setAccessibleName(label)
        button.setObjectName("schnitt_" + label.lower().replace(" ", "_"))
        return button

    def _zoom_by(self, factor: float) -> None:
        self.timeline.zoom_by_factor(factor)
        self._update_zoom_label()

    def _fit_to_content(self) -> None:
        self.timeline.fit_to_content()
        self._update_zoom_label()

    def _reset_zoom(self) -> None:
        self.timeline.reset_zoom()
        self._update_zoom_label()

    def _update_zoom_label(self) -> None:
        zoom = int(round(self.timeline.transform().m11() * 100))
        self.zoom_label.setText(f"Zoom {zoom}%")
