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
        toolbar.setSpacing(4)

        self.status_label = QLabel("Timeline bereit")
        self.status_label.setObjectName("schnitt_timeline_status")
        self.status_label.setStyleSheet("color: #9ca3af; font-size: 10px;")
        toolbar.addWidget(self.status_label)

        toolbar.addStretch(1)

        self.legend_label = QLabel("A1 Audio | V1 Video | Marker: Beats/Anker")
        self.legend_label.setObjectName("schnitt_timeline_legend")
        self.legend_label.setToolTip(
            "Legende fuer Timeline-Spuren: A1 ist Audio, V1 ist Video, Linien markieren Beats und Anker."
        )
        self.legend_label.setStyleSheet("color: #6b7280; font-size: 10px;")
        toolbar.addWidget(self.legend_label)

        self.zoom_label = QLabel("Zoom 100%")
        self.zoom_label.setObjectName("schnitt_timeline_zoom_label")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setMinimumWidth(72)
        self.zoom_label.setStyleSheet("color: #9ca3af; font-size: 10px;")
        toolbar.addWidget(self.zoom_label)

        self.btn_zoom_out = self._button("-", "Timeline herauszoomen")
        self.btn_zoom_fit = self._button("Fit", "Timeline auf Inhalt einpassen")
        self.btn_zoom_reset = self._button("1:1", "Timeline-Zoom auf 100 Prozent zuruecksetzen")
        self.btn_zoom_in = self._button("+", "Timeline hineinzoomen")

        for button in (
            self.btn_zoom_out,
            self.btn_zoom_fit,
            self.btn_zoom_reset,
            self.btn_zoom_in,
        ):
            toolbar.addWidget(button)

        layout.addLayout(toolbar)
        layout.addWidget(self.timeline, stretch=1)

        self.btn_zoom_out.clicked.connect(lambda: self._zoom_by(1 / 1.25))
        self.btn_zoom_in.clicked.connect(lambda: self._zoom_by(1.25))
        self.btn_zoom_fit.clicked.connect(self._fit_to_content)
        self.btn_zoom_reset.clicked.connect(self._reset_zoom)

    def _button(self, text: str, label: str) -> QPushButton:
        button = QPushButton(text)
        button.setFixedSize(34, 24)
        button.setToolTip(label)
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
