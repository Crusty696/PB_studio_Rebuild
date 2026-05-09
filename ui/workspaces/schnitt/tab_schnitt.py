"""Sub-Tab 'Schnitt' im SCHNITT-Editor: Preview + Transport + Timeline."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
)
from ui.timeline import InteractiveTimeline
from ui.widgets.video_preview import VideoPreviewWidget


class SchnittTabSchnitt(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(4, 4, 4, 4)
        v.setSpacing(4)

        preview_row = QHBoxLayout()
        preview_row.addStretch(1)
        self.video_preview = VideoPreviewWidget()
        self.video_preview.setMinimumSize(640, 360)
        self.video_preview.setMaximumSize(640, 360)
        preview_row.addWidget(self.video_preview)
        preview_row.addStretch(1)
        v.addLayout(preview_row)

        transport = QHBoxLayout()
        transport.addStretch(1)
        self.btn_play = QPushButton("▶")
        self.btn_play.setFixedSize(28, 24)
        self.btn_play.setToolTip("Vorschau Play / Pause")
        transport.addWidget(self.btn_play)
        self.btn_stop = QPushButton("■")
        self.btn_stop.setFixedSize(28, 24)
        self.btn_stop.setToolTip("Vorschau Stop")
        transport.addWidget(self.btn_stop)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #6b7280; font-size: 10px;")
        transport.addWidget(self.time_label)
        transport.addStretch(1)
        v.addLayout(transport)

        self.timeline_view = InteractiveTimeline()
        self.timeline_view.setToolTip(
            "Timeline: Drag&Drop, Mausrad zum Zoomen, Lock-Icon pro Clip."
        )
        v.addWidget(self.timeline_view, stretch=1)

        self.cut_info_label = QLabel("")
        self.cut_info_label.setStyleSheet("color: #6b7280; font-size: 10px; padding: 1px 4px;")
        v.addWidget(self.cut_info_label)
