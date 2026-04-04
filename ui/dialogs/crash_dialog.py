"""Crash dialog for PB Studio.

Shown by the global exception hook when an unhandled exception occurs.
Displays a compressed stacktrace and lets the user open the log file.
"""

from __future__ import annotations

import os
import subprocess
import sys
import traceback
from pathlib import Path
from types import TracebackType
from typing import Type

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFrame,
)
from PySide6.QtCore import Qt, QCoreApplication
from PySide6.QtGui import QFont

from ui.theme import BG0, BG1, BG3, BG4, ACCENT, ACCENT_BRIGHT, ERR, T2, T3, T4


_LOG_PATH = Path(__file__).parent.parent.parent / "logs" / "pb_studio.log"


class CrashDialog(QDialog):
    """Shows unhandled exception details and offers quick recovery actions."""

    def __init__(
        self,
        exc_type: Type[BaseException],
        exc_value: BaseException,
        exc_tb: TracebackType | None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(self.tr("PB Studio — Unerwarteter Fehler"))
        self.setFixedSize(580, 460)
        self.setStyleSheet(f"background-color: {BG1};")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(20, 18, 20, 18)

        # ── Header ─────────────────────────────────────────────────────
        header = QLabel(self.tr("Ein unerwarteter Fehler ist aufgetreten"))
        header.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {ERR}; background: transparent;"
        )
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        # ── Error type + message ───────────────────────────────────────
        exc_name = exc_type.__name__ if exc_type else "Exception"
        exc_msg = str(exc_value) if exc_value else ""
        summary = QLabel(f"<b>{exc_name}:</b> {exc_msg[:200]}")
        summary.setWordWrap(True)
        summary.setStyleSheet(f"color: {T2}; font-size: 12px; background: transparent;")
        layout.addWidget(summary)

        # ── Separator ─────────────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {BG3};")
        layout.addWidget(sep)

        # ── Stacktrace (compressed — last 20 lines) ───────────────────
        trace_label = QLabel(self.tr("Stacktrace:"))
        trace_label.setStyleSheet(f"color: {T4}; font-size: 10px; font-weight: 700;"
                                   "letter-spacing: 1px; background: transparent;")
        layout.addWidget(trace_label)

        tb_text = self._format_traceback(exc_type, exc_value, exc_tb)
        self._trace_edit = QTextEdit()
        self._trace_edit.setReadOnly(True)
        self._trace_edit.setFont(QFont("Courier New", 9))
        self._trace_edit.setStyleSheet(
            f"background: {BG0}; color: {T2}; border: 1px solid {BG3};"
            "border-radius: 4px; padding: 6px;"
        )
        self._trace_edit.setPlainText(tb_text)
        self._trace_edit.setMinimumHeight(180)
        layout.addWidget(self._trace_edit)

        # ── Hint ──────────────────────────────────────────────────────
        hint = QLabel(
            self.tr(
                "Die vollständige Fehler-Log-Datei enthält weitere Details. "
                "Bitte sende sie beim Melden eines Bugs mit."
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {T4}; font-size: 11px; background: transparent;")
        layout.addWidget(hint)

        # ── Buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_log = QPushButton(self.tr("Log-Datei öffnen"))
        btn_log.setStyleSheet(
            f"QPushButton {{ background: {BG3}; color: {T2}; border: 1px solid {BG4};"
            "border-radius: 6px; padding: 8px 16px; font-weight: 600; font-size: 12px; }"
            f"QPushButton:hover {{ background: {BG4}; }}"
        )
        btn_log.clicked.connect(self._open_log)
        btn_row.addWidget(btn_log)

        btn_row.addStretch()

        btn_close = QPushButton(self.tr("Schliessen"))
        btn_close.setStyleSheet(
            "QPushButton { background: #d4a44a; color: #1a1b23; border: none;"
            "border-radius: 6px; padding: 8px 20px; font-weight: 700; font-size: 13px; }"
            "QPushButton:hover { background: #e0b65c; }"
        )
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)

        layout.addLayout(btn_row)

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _format_traceback(
        exc_type: Type[BaseException] | None,
        exc_value: BaseException | None,
        exc_tb: TracebackType | None,
        max_lines: int = 40,
    ) -> str:
        if exc_type is None:
            return QCoreApplication.translate("CrashDialog", "(Kein Stacktrace verfügbar)")
        lines = traceback.format_exception(exc_type, exc_value, exc_tb)
        text = "".join(lines)
        # Trim to last max_lines lines
        all_lines = text.splitlines()
        if len(all_lines) > max_lines:
            omitted = len(all_lines) - max_lines
            all_lines = [QCoreApplication.translate("CrashDialog", "... ({omitted} Zeilen ausgeblendet) ...").format(omitted=omitted)] + all_lines[-max_lines:]
        return "\n".join(all_lines)

    @staticmethod
    def _open_log() -> None:
        log = _LOG_PATH
        if not log.exists():
            # Try logs/ relative to CWD
            log = Path("logs") / "pb_studio.log"
        if log.exists():
            if sys.platform == "win32":
                os.startfile(str(log))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(log)])
            else:
                subprocess.Popen(["xdg-open", str(log)])
