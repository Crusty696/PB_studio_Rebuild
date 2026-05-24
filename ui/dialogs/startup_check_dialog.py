"""StartupCheckDialog — shown on launch ONLY when there are errors or warnings."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from services.startup_checks import SystemStatus
from ui.theme import ACCENT, ACCENT_BRIGHT, BG0, BG1, BG2, ERR, OK, T1, T2, T3, WARN

_HW_REQUIREMENTS_URL = "https://github.com/pbstudio/pb-studio-rebuild#hardware-requirements"


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {T3}; font-size: 10px; font-weight: 700; "
        "text-transform: uppercase; letter-spacing: 1.5px; background: transparent;"
    )
    return lbl


def _check_row(label: str, ok: bool, detail: str = "") -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 4, 0, 4)
    layout.setSpacing(10)

    indicator = QLabel("OK" if ok else "FAIL")
    indicator.setFixedWidth(44)
    indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
    indicator.setToolTip(
        f"Systempruefung fuer {label}: {'bestanden' if ok else 'fehlgeschlagen'}."
    )
    indicator.setStyleSheet(
        f"background: {'rgba(74,222,128,31)' if ok else 'rgba(248,113,113,31)'}; "
        f"color: {OK if ok else ERR}; border-radius: 6px; "
        "font-size: 10px; font-weight: 800; padding: 3px 0;"
    )
    layout.addWidget(indicator)

    txt = label if not detail else f"{label}  <span style='color:{T3}'>{detail}</span>"
    lbl = QLabel(txt)
    lbl.setTextFormat(Qt.TextFormat.RichText)
    lbl.setStyleSheet(f"color: {T1}; font-size: 11px; font-weight: 500; background: transparent;")
    lbl.setToolTip(detail or label)
    layout.addWidget(lbl)
    layout.addStretch()
    return row


def _message_row(text: str, color: str, icon: str) -> QWidget:
    row = QFrame()
    row.setObjectName("card")
    row.setStyleSheet(
        f"background: {BG2}; border: 1px solid rgba(255,255,255,13); "
        "border-radius: 10px;"
    )
    layout = QHBoxLayout(row)
    layout.setContentsMargins(14, 10, 14, 10)
    layout.setSpacing(12)

    icon_lbl = QLabel(icon)
    icon_lbl.setFixedWidth(24)
    icon_lbl.setStyleSheet(
        f"color: {color}; font-size: 16px; font-weight: 800; background: transparent;"
    )
    layout.addWidget(icon_lbl)

    text_lbl = QLabel(text)
    text_lbl.setWordWrap(True)
    text_lbl.setStyleSheet(f"color: {T2}; font-size: 11px; line-height: 1.4; background: transparent;")
    text_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    text_lbl.setToolTip(text)
    layout.addWidget(text_lbl)
    return row


class StartupCheckDialog(QDialog):
    def __init__(self, status: SystemStatus, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PB Studio — System Check")
        self.setMinimumWidth(540)
        self.setMaximumWidth(640)
        self.setStyleSheet(f"background-color: {BG0}; color: {T1}; font-family: 'Segoe UI Variable Text', sans-serif;")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        outer = QVBoxLayout(self)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QWidget()
        header.setFixedHeight(64)
        header.setStyleSheet(f"background-color: {BG1}; border-bottom: 1px solid rgba(255,255,255,13);")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(24, 0, 24, 0)
        title = QLabel("System Check")
        title.setStyleSheet(f"color: {ACCENT_BRIGHT}; font-size: 18px; font-weight: 800; background: transparent;")
        h_layout.addWidget(title)
        h_layout.addStretch()

        badge_color = ERR if status.errors else WARN
        badge_text = f"{len(status.errors)} Fehler" if status.errors else f"{len(status.warnings)} Warnung(en)"
        badge = QLabel(badge_text)
        badge.setStyleSheet(
            f"background: {badge_color}; color: {BG0}; border-radius: 12px; "
            "padding: 3px 12px; font-size: 11px; font-weight: 800;"
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
        ffmpeg_detail = f"v{status.ffmpeg_version} · {status.ffmpeg_path}" if status.ffmpeg_version else status.ffmpeg_path
        cl.addWidget(_check_row("FFmpeg", status.ffmpeg_ok, ffmpeg_detail))
        cl.addWidget(_check_row("ffprobe", status.ffprobe_ok, status.ffprobe_path))
        gpu_detail = f"{status.gpu_name}  {round(status.gpu_vram_mb / 1024)} GB" if status.cuda_ok else ""
        cl.addWidget(_check_row("CUDA GPU", status.cuda_ok, gpu_detail))
        cl.addWidget(_check_row("Speicherplatz (>1 GB)", status.disk_ok, f"{status.disk_free_gb:.1f} GB frei"))
        cl.addWidget(_check_row("Ollama (KI-Dienst)", status.ollama_ok))
        cl.addSpacing(8)

        cl.addWidget(_section_label("Portabilitaet"))
        cl.addSpacing(4)
        hf_detail = status.hf_cache_detail
        if status.hf_cache_path:
            hf_detail = f"{status.hf_cache_source}: {status.hf_cache_path}"
        cl.addWidget(_check_row("Hugging-Face Cache", status.hf_cache_ok, hf_detail))
        cl.addSpacing(8)

        cl.addWidget(_section_label("KI-Modelle"))
        cl.addSpacing(4)
        cl.addWidget(_check_row("beat_this (Beat-Analyse)", status.beat_this_ok,
                                "" if status.beat_this_ok else "Fallback: librosa"))
        cl.addWidget(_check_row("demucs (Stem-Separation)", status.demucs_ok,
                                "" if status.demucs_ok else "nicht verfuegbar"))
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

        if status.ml_warnings:
            cl.addSpacing(6)
            cl.addWidget(_section_label("KI-Modell Hinweise"))
            for msg in status.ml_warnings:
                cl.addWidget(_message_row(msg, ACCENT, "i"))

        if status.model_cache_warnings:
            cl.addSpacing(6)
            cl.addWidget(_section_label("Modell-Cache Hinweise"))
            for msg in status.model_cache_warnings:
                cl.addWidget(_message_row(msg, ACCENT, "i"))

        cl.addSpacing(12)

        # Hardware requirements link
        hw_link = QLabel(
            f'<a href="{_HW_REQUIREMENTS_URL}" style="color: {ACCENT}; '
            'text-decoration: none;">▸ Hardware-Anforderungen ansehen</a>'
        )
        hw_link.setTextFormat(Qt.TextFormat.RichText)
        hw_link.setOpenExternalLinks(True)
        hw_link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hw_link.setStyleSheet("background: transparent; font-size: 11px;")
        cl.addWidget(hw_link)

        cl.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        # Footer — "Beenden" + "Trotzdem starten" when errors; "Weiter" for warnings only
        footer = QWidget()
        footer.setFixedHeight(56)
        footer.setStyleSheet(f"background-color: {BG1};")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(20, 0, 20, 0)
        f_layout.addStretch()

        if status.errors:
            btn_quit = QPushButton("Beenden")
            btn_quit.setToolTip(
                "PB Studio nicht starten, weil kritische Systempruefungen fehlgeschlagen sind."
            )
            btn_quit.setStyleSheet(
                f"QPushButton {{ background: rgba(248,113,113,38); color: {ERR}; "
                f"border: 1px solid {ERR}; border-radius: 6px; padding: 6px 18px; font-weight: 700; }}"
                f"QPushButton:hover {{ background: rgba(248,113,113,77); }}"
            )
            btn_quit.clicked.connect(self.reject)
            f_layout.addWidget(btn_quit)

            f_layout.addSpacing(8)

            btn_start = QPushButton("Trotzdem starten (degradierter Modus)")
            btn_start.setToolTip(
                "App trotz Fehlern starten. Einige GPU-, KI- oder Medienfunktionen koennen ausfallen."
            )
            btn_start.setStyleSheet(
                f"QPushButton {{ background: rgba(251,191,36,38); color: {WARN}; "
                f"border: 1px solid {WARN}; border-radius: 6px; padding: 6px 18px; font-weight: 700; }}"
                f"QPushButton:hover {{ background: rgba(251,191,36,77); }}"
            )
            btn_start.clicked.connect(self.accept)
            f_layout.addWidget(btn_start)
        else:
            btn_ok = QPushButton("Weiter")
            btn_ok.setToolTip(
                "System Check schliessen und PB Studio starten."
            )
            btn_ok.setStyleSheet(
                f"QPushButton {{ background: {ACCENT}; color: {BG0}; border: none; "
                "border-radius: 6px; padding: 6px 20px; font-weight: 700; }}"
                f"QPushButton:hover {{ background: {ACCENT_BRIGHT}; }}"
            )
            btn_ok.clicked.connect(self.accept)
            f_layout.addWidget(btn_ok)

        outer.addWidget(footer)

        self.adjustSize()
        if self.height() > 620:
            self.setFixedHeight(620)


def maybe_show_startup_dialog(status: SystemStatus, parent=None) -> bool:
    """Show startup check dialog if needed. Returns False if user chose to exit."""
    if not status.errors and not status.warnings:
        return True
    dlg = StartupCheckDialog(status, parent)
    result = dlg.exec()
    # Only reject (exit) when there were hard errors and user clicked "Beenden"
    if status.errors and result == QDialog.DialogCode.Rejected:
        return False
    return True
