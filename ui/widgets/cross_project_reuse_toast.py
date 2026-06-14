from __future__ import annotations

import logging

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QCheckBox, QMessageBox, QWidget

logger = logging.getLogger(__name__)


def show_cross_project_reuse_toast(parent: QWidget | None, message: str, mute_key: str) -> QMessageBox | None:
    """Show non-modal cross-project reuse notice and persist mute checkbox."""

    try:
        box = QMessageBox(parent)
        box.setWindowTitle("Analyse-Ergebnisse wiederverwendet")
        box.setText(message)
        box.setIcon(QMessageBox.Icon.Information)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.setWindowModality(Qt.WindowModality.NonModal)
        checkbox = QCheckBox("Nicht mehr fragen")
        box.setCheckBox(checkbox)

        def _store_mute(checked: bool) -> None:
            QSettings("PB Studio", "Rebuild").setValue(mute_key, checked)

        checkbox.toggled.connect(_store_mute)
        box._pb_reuse_checkbox = checkbox
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        box.show()
        return box
    except Exception as exc:
        logger.warning("OTK-021 reuse notice failed: %s", exc)
        return None
