"""About Dialog for PB Studio."""

import logging
import sys
import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)
from PySide6.QtCore import Qt, QCoreApplication

from ui.theme import BG0, BG1, BG3, BG4, ACCENT, ACCENT_BRIGHT, T2, T3, T4

logger = logging.getLogger(__name__)


def _build_date() -> str:
    """Return a human-readable build date (modification time of this file)."""
    try:
        mtime = Path(__file__).stat().st_mtime
        return datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except OSError:
        return "n/a"


def _gpu_info() -> str:
    """Try to detect GPU name + CUDA version."""
    try:
        import torch  # type: ignore
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            cuda = torch.version.cuda or "n/a"
            return f"{name}  |  CUDA {cuda}"
    except (ImportError, AttributeError, OSError) as exc:
        logger.warning("_gpu_info: failed to detect GPU: %s", exc)
    return QCoreApplication.translate("AboutDialog", "Keine CUDA-GPU erkannt")


def _badge(text: str, bg: str = BG3, fg: str = T2) -> QLabel:
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
        self.setFixedSize(460, 450)
        self.setStyleSheet(f"background-color: {BG1};")

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 20, 24, 20)

        # ── Title ──
        title = QLabel("PB Studio")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            f"font-size: 30px; font-weight: 800; color: {ACCENT}; background: transparent;"
        )
        layout.addWidget(title)

        # ── Subtitle ──
        subtitle = QLabel("Director's Cockpit \u2014 Beat-Synchronized Video Editor")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(
            f"font-size: 13px; color: {T3}; font-weight: 600; background: transparent;"
        )
        layout.addWidget(subtitle)

        # ── Separator ──
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background-color: {BG3};")
        layout.addWidget(line)

        # ── Version + Build Date ──
        ver_label = QLabel(f"Version {version}  ·  Build {_build_date()}")
        ver_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver_label.setStyleSheet(
            f"font-size: 14px; color: {ACCENT}; font-weight: 700; background: transparent;"
        )
        layout.addWidget(ver_label)

        layout.addSpacing(4)

        # ── Tech Stack Badges ──
        tech_label = QLabel("Tech Stack")
        tech_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tech_label.setStyleSheet(
            f"font-size: 11px; color: {T4}; font-weight: 600;"
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
        line2.setStyleSheet(f"background-color: {BG3};")
        layout.addWidget(line2)

        # ── Hardware / Runtime Info ──
        gpu_text = _gpu_info()
        py_ver = f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        info = QLabel(f"{gpu_text}\n{py_ver}")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet(
            f"color: {T3}; font-size: 12px; line-height: 1.6; background: transparent;"
        )
        layout.addWidget(info)

        layout.addStretch()

        # ── Separator ──
        line3 = QFrame()
        line3.setFrameShape(QFrame.Shape.HLine)
        line3.setStyleSheet(f"background-color: {BG3};")
        layout.addWidget(line3)

        # ── Credits ──
        credits = QLabel("© 2024–2026 Paperclip / PB Studio Team")
        credits.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credits.setStyleSheet(
            f"color: {T4}; font-size: 11px; background: transparent;"
        )
        layout.addWidget(credits)

        # ── Bottom Button Row ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_docs = QPushButton(self.tr("Dokumentation"))
        btn_docs.setMaximumWidth(140)
        btn_docs.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_docs.setToolTip(self.tr("Öffnet die PB Studio Dokumentation im Browser"))
        btn_docs.setStyleSheet(
            f"QPushButton {{ background: {BG3}; color: {T2}; border: 1px solid {BG4};"
            "border-radius: 6px; padding: 7px 14px; font-weight: 600; font-size: 12px; }"
            f"QPushButton:hover {{ background: {BG4}; }}"
        )
        btn_docs.clicked.connect(self._open_docs)
        btn_row.addWidget(btn_docs)

        btn_row.addStretch()

        btn = QPushButton(self.tr("Schliessen"))
        btn.setObjectName("btn_accent")
        btn.setMaximumWidth(140)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(self.tr("Diesen Dialog schliessen und zur App zurueckkehren"))
        btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: {BG0}; border: none;"
            "border-radius: 6px; padding: 8px 20px; font-weight: 700; font-size: 13px; }"
            f"QPushButton:hover {{ background: {ACCENT_BRIGHT}; }}"
        )
        btn.clicked.connect(self.accept)
        btn_row.addWidget(btn)

        layout.addLayout(btn_row)

    @staticmethod
    def _open_docs() -> None:
        """Open the documentation README in the default viewer."""
        import subprocess, os
        docs_path = Path(__file__).parent.parent.parent / "README.md"
        try:
            if docs_path.exists():
                if sys.platform == "win32":
                    os.startfile(str(docs_path))
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", str(docs_path)])
                else:
                    subprocess.Popen(["xdg-open", str(docs_path)])
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning("_open_docs: failed to open README: %s", exc)
