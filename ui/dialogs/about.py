"""About Dialog for PB Studio."""

import sys

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)
from PySide6.QtCore import Qt

from ui.theme import BG1, ACCENT, T1


def _gpu_info() -> str:
    """Try to detect GPU name + CUDA version."""
    try:
        import torch  # type: ignore
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            cuda = torch.version.cuda or "n/a"
            return f"{name}  |  CUDA {cuda}"
    except Exception:
        pass
    return "Keine CUDA-GPU erkannt"


def _badge(text: str, bg: str = "#2a2d3a", fg: str = "#c0c0c0") -> QLabel:
    """Return a small colored badge label."""
    lbl = QLabel(text)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(
        f"background: {bg}; color: {fg}; border-radius: 6px;"
        "padding: 3px 8px; font-size: 11px; font-weight: 600;"
    )
    return lbl


class AboutDialog(QDialog):
    def __init__(self, version: str = "0.5.0", parent=None):
        super().__init__(parent)
        self.setWindowTitle("About PB Studio")
        self.setFixedSize(460, 420)
        self.setStyleSheet(f"background-color: {BG1};")

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 20, 24, 20)

        # ── Title ──
        title = QLabel("PB Studio")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 30px; font-weight: 800; color: #d4a44a; background: transparent;"
        )
        layout.addWidget(title)

        # ── Subtitle ──
        subtitle = QLabel("Director's Cockpit \u2014 Beat-Synchronized Video Editor")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(
            "font-size: 13px; color: #909090; font-weight: 600; background: transparent;"
        )
        layout.addWidget(subtitle)

        # ── Separator ──
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #2a2a2a;")
        layout.addWidget(line)

        # ── Version ──
        ver_label = QLabel(f"Version {version}")
        ver_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver_label.setStyleSheet(
            "font-size: 14px; color: #d4a44a; font-weight: 700; background: transparent;"
        )
        layout.addWidget(ver_label)

        layout.addSpacing(4)

        # ── Tech Stack Badges ──
        tech_label = QLabel("Tech Stack")
        tech_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tech_label.setStyleSheet(
            "font-size: 11px; color: #606060; font-weight: 600;"
            "text-transform: uppercase; letter-spacing: 1px; background: transparent;"
        )
        layout.addWidget(tech_label)

        badges = [
            ("beat_this", "#1e3a5f", "#5eaeff"),
            ("Demucs", "#2d1f4e", "#b48eff"),
            ("SigLIP", "#1a3330", "#4ade80"),
            ("RAFT", "#3b2a1a", "#f59e42"),
            ("FFmpeg", "#1a2e1a", "#66bb6a"),
            ("PySceneDetect", "#2a2a3a", "#90caf9"),
            ("faster-whisper", "#2a1a2a", "#f48fb1"),
        ]

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        row1.addStretch()
        for text, bg, fg in badges[:4]:
            row1.addWidget(_badge(text, bg, fg))
        row1.addStretch()
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        row2.addStretch()
        for text, bg, fg in badges[4:]:
            row2.addWidget(_badge(text, bg, fg))
        row2.addStretch()
        layout.addLayout(row2)

        layout.addSpacing(6)

        # ── Separator ──
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setStyleSheet("background-color: #2a2a2a;")
        layout.addWidget(line2)

        # ── Hardware / Runtime Info ──
        gpu_text = _gpu_info()
        py_ver = f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        info = QLabel(f"{gpu_text}\n{py_ver}")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet(
            "color: #707070; font-size: 12px; line-height: 1.6; background: transparent;"
        )
        layout.addWidget(info)

        layout.addStretch()

        # ── Close Button ──
        btn = QPushButton("Schliessen")
        btn.setObjectName("btn_accent")
        btn.setMaximumWidth(160)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Diesen Dialog schliessen und zur App zurueckkehren")
        btn.setStyleSheet(
            "QPushButton { background: #d4a44a; color: #1a1b23; border: none;"
            "border-radius: 6px; padding: 8px 20px; font-weight: 700; font-size: 13px; }"
            "QPushButton:hover { background: #e0b65c; }"
        )
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
