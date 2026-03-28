"""StartupCheckDialog — shown on launch ONLY when there are errors or warnings."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from services.startup_checks import SystemStatus
from ui.theme import ACCENT, ACCENT_BRIGHT, BG0, BG1, BG2, BG3, ERR, OK, T1, T2, T3, WARN


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {T3}; font-size: 10px; font-weight: 600; "
        "text-transform: uppercase; letter-spacing: 1px; background: transparent;"
    )
    return lbl


def _check_row(label: str, ok: bool, detail: str = "") -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 2, 0, 2)
    layout.setSpacing(8)

    indicator = QLabel("OK" if ok else "FAIL")
    indicator.setFixedWidth(40)
    indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
    indicator.setStyleSheet(
        f"background: {'rgba(74,222,128,20)' if ok else 'rgba(248,113,113,20)'}; "
        f"color: {OK if ok else ERR}; border-radius: 4px; "
        "font-size: 10px; font-weight: 700; padding: 2px 0;"
    )
    layout.addWidget(indicator)

    txt = label if not detail else f"{label}  <span style='color:{T3}'>{detail}</span>"
    lbl = QLabel(txt)
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setStyleSheet(f"color: {T2}; font-size: 11px; background: transparent;")
    layout.addWidget(lbl)
    layout.addStretch()
    return row


def _message_row(text: str, color: str, icon: str) -> QWidget:
    row = QFrame()
    row.setObjectName("card")
    row.setStyleSheet(
        f"QFrame#card {{ background: {BG2}; border: 1px solid rgba(255,255,255,10); "
        "border-radius: 6px; }}"
    )
    layout = QHBoxLayout(row)
    layout.setContentsMargins(12, 8, 12, 8)
    layout.setSpacing(10)

    icon_lbl = QLabel(icon)
    icon_lbl.setFixedWidth(20)
    icon_lbl.setStyleSheet(
        f"color: {color}; font-size: 16px; font-weight: 700; background: transparent;"
    )
    layout.addWidget(icon_lbl)

    text_lbl = QLabel(text)
    text_lbl.setWordWrap(True)
    text_lbl.setStyleSheet(f"color: {T2}; font-size: 11px; background: transparent;")
    text_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    layout.addWidget(text_lbl)
    return row


class StartupCheckDialog(QDialog):
    def __init__(self, status: SystemStatus, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PB Studio — System Check")
        self.setMinimumWidth(520)
        self.setMaximumWidth(640)
        self.setStyleSheet(f"background-color: {BG0}; color: {T1};")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet(f"background-color: {BG1};")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 20, 0)
        title = QLabel("System Check")
        title.setStyleSheet(f"color: {ACCENT_BRIGHT}; font-size: 18px; font-weight: 800; background: transparent;")
        h_layout.addWidget(title)
        h_layout.addStretch()

        badge_color = ERR if status.errors else WARN
        badge_text = f"{len(status.errors)} Fehler" if status.errors else f"{len(status.warnings)} Warnung(en)"
        badge = QLabel(badge_text)
        badge.setStyleSheet(
            f"background: {badge_color}; color: {BG0}; border-radius: 10px; "
            "padding: 2px 10px; font-size: 11px; font-weight: 700;"
        )
        h_layout.addWidget(badge)
        outer.addWidget(header)

        # Content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setStyleSheet(f"background: {BG0};")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.setSpacing(6)

        cl.addWidget(_section_label("Abhaengigkeiten"))
        cl.addSpacing(4)
        ffmpeg_detail = f"v{status.ffmpeg_version}" if status.ffmpeg_version else ""
        cl.addWidget(_check_row("FFmpeg", status.ffmpeg_ok, ffmpeg_detail))
        cl.addWidget(_check_row("ffprobe", status.ffprobe_ok))
        gpu_detail = f"{status.gpu_name}  {round(status.gpu_vram_mb / 1024)} GB" if status.cuda_ok else ""
        cl.addWidget(_check_row("CUDA GPU", status.cuda_ok, gpu_detail))
        cl.addWidget(_check_row("Speicherplatz (>1 GB)", status.disk_ok, f"{status.disk_free_gb:.1f} GB frei"))
        cl.addSpacing(12)

        if status.errors:
            cl.addWidget(_section_label("Fehler"))
            for msg in status.errors:
                cl.addWidget(_message_row(msg, ERR, "X"))
            cl.addSpacing(10)

        if status.warnings:
            cl.addWidget(_section_label("Warnungen"))
            for msg in status.warnings:
                cl.addWidget(_message_row(msg, WARN, "!"))

        cl.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        # Footer
        footer = QWidget()
        footer.setFixedHeight(56)
        footer.setStyleSheet(f"background-color: {BG1};")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(20, 0, 20, 0)
        f_layout.addStretch()
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(self.accept)
        ok_btn = btn_box.button(QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("Weiter")
        ok_btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT}; color: {BG0}; border: none; "
            "border-radius: 6px; padding: 6px 20px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {ACCENT_BRIGHT}; }}"
        )
        f_layout.addWidget(btn_box)
        outer.addWidget(footer)

        self.adjustSize()
        if self.height() > 620:
            self.setFixedHeight(620)


def maybe_show_startup_dialog(status: SystemStatus, parent=None) -> None:
    if not status.errors and not status.warnings:
        return
    dlg = StartupCheckDialog(status, parent)
    dlg.exec()
