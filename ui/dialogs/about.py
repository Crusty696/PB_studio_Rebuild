"""About Dialog for PB Studio."""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt


class AboutDialog(QDialog):
    def __init__(self, version: str = "0.4.0", parent=None):
        super().__init__(parent)
        self.setWindowTitle("About PB_studio")
        self.setFixedSize(400, 280)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("PB_studio")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: 800; color: #D4AF37;")
        layout.addWidget(title)

        subtitle = QLabel("Director's Cockpit")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 14px; color: #909090; font-weight: 600;")
        layout.addWidget(subtitle)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #2A2A2A;")
        layout.addWidget(line)

        info = QLabel(
            f"Version {version}\n\n"
            "Beat-synchronisierte Video-Produktion\n"
            "mit KI-gestuetztem Pacing.\n\n"
            "Built with PySide6 + FFmpeg + Demucs + librosa"
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet("color: #707070; font-size: 12px; line-height: 1.5;")
        layout.addWidget(info)

        btn = QPushButton("Schliessen")
        btn.setObjectName("btn_accent")
        btn.setMaximumWidth(140)
        btn.setToolTip("Diesen Dialog schliessen und zur App zurueckkehren")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
