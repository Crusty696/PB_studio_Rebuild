"""GPU-Recovery-Dialog - shown at startup when the GPU is in a stuck state.

P16: Surface Book 2 Code-47 (CM_PROB_HELD_FOR_EJECT) recovery flow.
Presents a friendly German dialog that explains the situation and offers
three options: close PB Studio (so the user can reboot manually), continue
on CPU, or cancel.

NOTE: This dialog never triggers an automatic system reboot. Earlier
versions used ``shutdown /r /t 5`` from the "Restart" button — that
destroyed unsaved work in OTHER programs the user had open (Word docs,
browser tabs, etc). PB Studio cannot know what else is running, so the
user reboots manually via the Start menu after saving their work.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import (
    ACCENT,
    ACCENT_BRIGHT,
    ACCENT_DIM,
    BG0,
    BG1,
    BG2,
    BG3,
    BG4,
    T1,
    T2,
    T3,
    WARN,
)

logger = logging.getLogger(__name__)

UserChoice = Literal["restart", "cpu_fallback", "cancel"]

_BODY_TEXT = (
    "⚠ GPU im Standby-Modus\n"
    "\n"
    "Deine NVIDIA GTX 1060 ist gerade nicht verfuegbar.\n"
    "Windows hat sie als „sicher entfernbar“ markiert.\n"
    "\n"
    "Empfohlen: Computer einmal neu starten.\n"
    "Reboot loest diesen Zustand fast immer auf.\n"
    "\n"
    "WICHTIG: Speichere zuerst alle offenen Programme\n"
    "(Word, Browser, …) — PB Studio startet den\n"
    "Computer NICHT automatisch. Du machst den Reboot\n"
    "selbst ueber Start → Power → Neu starten.\n"
    "\n"
    "⛔ Bitte NICHT: GPU im Geraete-Manager\n"
    "   deaktivieren/aktivieren — kann zu einem\n"
    "   Bluescreen fuehren."
)


class GpuRecoveryDialog(QDialog):
    """Friendly dialog explaining Code-47 (held_for_eject) and offering recovery."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("GPU im Standby-Modus")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setStyleSheet(f"background-color: {BG1};")
        self._choice: UserChoice = "cancel"
        self._build_ui()

    # -- UI --------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setFixedHeight(52)
        header.setStyleSheet(f"background: {BG0}; border-bottom: 1px solid {BG3};")
        hdr = QHBoxLayout(header)
        hdr.setContentsMargins(20, 0, 16, 0)
        title = QLabel("GPU im Standby-Modus")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {WARN}; background: transparent;"
        )
        hdr.addWidget(title)
        hdr.addStretch()
        outer.addWidget(header)

        # Body
        body_wrap = QWidget()
        body_wrap.setStyleSheet(f"background: {BG1};")
        body_layout = QVBoxLayout(body_wrap)
        body_layout.setContentsMargins(24, 20, 24, 18)
        body_layout.setSpacing(12)

        body = QLabel(_BODY_TEXT)
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.PlainText)
        body.setStyleSheet(
            f"color: {T1}; background: transparent; font-size: 13px; "
            "line-height: 160%;"
        )
        body_layout.addWidget(body)

        hint = QLabel(
            "Tipp: 1) Andere Programme speichern  2) PB Studio beenden  "
            "3) Computer ueber Start-Menue neu starten  "
            "4) PB Studio neu oeffnen — GPU ist dann wieder da."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"color: {T3}; background: transparent; font-size: 11px; font-style: italic;"
        )
        body_layout.addWidget(hint)

        outer.addWidget(body_wrap, stretch=1)

        # Footer with buttons (left -> right)
        footer = QWidget()
        footer.setFixedHeight(60)
        footer.setStyleSheet(f"background: {BG0}; border-top: 1px solid {BG3};")
        ft = QHBoxLayout(footer)
        ft.setContentsMargins(20, 10, 16, 10)
        ft.setSpacing(10)

        self._btn_restart = QPushButton("\U0001F504 PB Studio beenden")
        self._btn_restart.setObjectName("btn_primary")
        self._btn_restart.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_restart.setMinimumHeight(32)
        self._btn_restart.setStyleSheet(
            f"QPushButton#btn_primary {{"
            f"background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1,"
            f" stop:0 {ACCENT}, stop:1 {ACCENT_DIM});"
            f" color: {BG0}; border: none; border-radius: 6px;"
            f" font-weight: 700; font-size: 12px; padding: 4px 14px; }}"
            f"QPushButton#btn_primary:hover {{"
            f" background: {ACCENT_BRIGHT}; }}"
        )
        self._btn_restart.clicked.connect(self._on_restart)
        ft.addWidget(self._btn_restart)

        self._btn_cpu = QPushButton("⏵ Mit CPU starten — langsamer")
        self._btn_cpu.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cpu.setMinimumHeight(32)
        self._btn_cpu.setStyleSheet(
            f"QPushButton {{ background: {BG3}; color: {T1};"
            f" border: 1px solid rgba(255,255,255,30); border-radius: 6px;"
            f" font-weight: 600; font-size: 12px; padding: 4px 14px; }}"
            f"QPushButton:hover {{ background: {BG4}; }}"
        )
        self._btn_cpu.clicked.connect(self._on_cpu_fallback)
        ft.addWidget(self._btn_cpu)

        ft.addStretch()

        self._btn_cancel = QPushButton("Abbrechen")
        self._btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cancel.setMinimumHeight(32)
        self._btn_cancel.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {T2};"
            f" border: 1px solid rgba(255,255,255,20); border-radius: 6px;"
            f" font-weight: 500; font-size: 12px; padding: 4px 14px; }}"
            f"QPushButton:hover {{ color: {T1}; border-color: rgba(255,255,255,40); }}"
        )
        self._btn_cancel.clicked.connect(self._on_cancel)
        ft.addWidget(self._btn_cancel)

        outer.addWidget(footer)

    # -- Handlers --------------------------------------------------------

    def _on_restart(self) -> None:
        """Close PB Studio so the user can reboot manually.

        Earlier versions called ``shutdown /r /t 5`` here — that destroyed
        unsaved work in OTHER programs (Word, browser). PB Studio cannot
        know what else is running, so the user reboots themselves.
        """
        self._choice = "restart"
        logger.info("User waehlte Reboot — PB Studio wird beendet, Reboot durch User.")
        self.accept()

    def _on_cpu_fallback(self) -> None:
        """Force CPU mode for the rest of this process and accept."""
        self._choice = "cpu_fallback"
        os.environ["PB_STUDIO_FORCE_CPU"] = "1"
        self.accept()

    def _on_cancel(self) -> None:
        self._choice = "cancel"
        self.reject()

    # -- API -------------------------------------------------------------

    def choice(self) -> UserChoice:
        """Return which button the user picked (``cancel`` by default)."""
        return self._choice
