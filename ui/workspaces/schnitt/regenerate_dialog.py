"""QMessageBox-Helper für Re-Generate-Confirm im Sub-Tab Pacing & Anker.

Phase 06 / Task 6.3 — SCHNITT-Redesign 2026-05-09.
"""
from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget


def confirm_regenerate(parent: QWidget | None) -> bool:
    """Zeigt einen Warning-Dialog und gibt True zurueck wenn der User
    'Ja' klickt. Default-Button ist 'Nein' um versehentliche Klicks
    zu vermeiden.
    """
    answer = QMessageBox.warning(
        parent,
        "Pacing neu anwenden?",
        "Achtung: Dies überschreibt aktuelle ungelockte Schnitte. Fortfahren?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes
