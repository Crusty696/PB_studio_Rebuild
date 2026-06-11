"""Papierkorb-Dialog — B-462 Stage 2 (Task 12, option C).

Zeigt soft-geloeschte Medien des aktiven Projekts und bietet zwei Tier-Aktionen:
- "Ausgewaehlte wiederherstellen": setzt ``deleted_at`` zurueck (reversibel).
- "Papierkorb leeren": loescht ALLE soft-geloeschten Medien physisch und
  endgueltig (irreversibel, mit Bestaetigung).

Oeffnbar via: Material/Analyse → Toolbar-Button "Papierkorb".
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView,
    QAbstractItemView,
)

from services.ingest_service import (
    get_soft_deleted_media, restore_media, purge_soft_deleted_media,
)

logger = logging.getLogger(__name__)


class TrashDialog(QDialog):
    """Papierkorb-Ansicht fuer soft-geloeschte Medien eines Projekts."""

    def __init__(self, project_id: int | None = None, parent=None):
        super().__init__(parent)
        self._project_id = project_id
        self.setWindowTitle("Papierkorb — soft-geloeschte Medien")
        self.setMinimumSize(560, 360)

        layout = QVBoxLayout(self)

        self._info = QLabel()
        layout.addWidget(self._info)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Typ", "Titel", "Geloescht am"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        layout.addWidget(self.table, stretch=1)

        btn_row = QHBoxLayout()
        self.btn_restore = QPushButton("Ausgewaehlte wiederherstellen")
        self.btn_purge = QPushButton("Papierkorb leeren")
        self.btn_close = QPushButton("Schliessen")
        btn_row.addWidget(self.btn_restore)
        btn_row.addWidget(self.btn_purge)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_close)
        layout.addLayout(btn_row)

        self.btn_restore.clicked.connect(self._on_restore)
        self.btn_purge.clicked.connect(self._on_purge)
        self.btn_close.clicked.connect(self.accept)

        self._reload()

    # ── Daten ─────────────────────────────────────────────────────────────
    def _reload(self) -> None:
        try:
            items = get_soft_deleted_media(self._project_id)
        except (ValueError, RuntimeError, OSError) as e:
            logger.exception("TrashDialog: get_soft_deleted_media failed")
            QMessageBox.critical(self, "Papierkorb", f"Papierkorb laden fehlgeschlagen:\n{e}")
            items = []

        self.table.setRowCount(0)
        for it in items:
            row = self.table.rowCount()
            self.table.insertRow(row)
            type_item = QTableWidgetItem(it.get("type", ""))
            # ID + Typ am ersten Item speichern fuer Restore-Sammlung.
            type_item.setData(Qt.UserRole, (it.get("type"), it.get("id")))
            self.table.setItem(row, 0, type_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(it.get("title", ""))))
            stamp = it.get("deleted_at")
            stamp_txt = stamp.strftime("%Y-%m-%d %H:%M") if hasattr(stamp, "strftime") else str(stamp or "")
            self.table.setItem(row, 2, QTableWidgetItem(stamp_txt))

        count = self.table.rowCount()
        self._info.setText(
            f"{count} soft-geloeschte Medien im Papierkorb."
            if count else "Papierkorb ist leer."
        )
        self.btn_restore.setEnabled(count > 0)
        self.btn_purge.setEnabled(count > 0)

    def _selected_ids(self) -> tuple[list[int], list[int]]:
        video_ids: list[int] = []
        audio_ids: list[int] = []
        for idx in self.table.selectionModel().selectedRows():
            item = self.table.item(idx.row(), 0)
            data = item.data(Qt.UserRole) if item else None
            if not data:
                continue
            mtype, mid = data
            if mtype == "Video":
                video_ids.append(int(mid))
            elif mtype == "Audio":
                audio_ids.append(int(mid))
        return video_ids, audio_ids

    # ── Aktionen ──────────────────────────────────────────────────────────
    def _on_restore(self) -> None:
        video_ids, audio_ids = self._selected_ids()
        if not video_ids and not audio_ids:
            QMessageBox.information(
                self, "Wiederherstellen",
                "Bitte zuerst Zeilen auswaehlen.",
            )
            return
        try:
            n = restore_media(video_ids, audio_ids)
        except (ValueError, RuntimeError, OSError) as e:
            logger.exception("TrashDialog: restore_media failed")
            QMessageBox.critical(self, "Wiederherstellen", f"Wiederherstellen fehlgeschlagen:\n{e}")
            return
        QMessageBox.information(self, "Wiederherstellen", f"{n} Medien wiederhergestellt.")
        self._reload()

    def _on_purge(self) -> None:
        count = self.table.rowCount()
        if count == 0:
            return
        confirm = QMessageBox.warning(
            self,
            "Papierkorb endgueltig leeren",
            f"{count} Medien werden UNWIDERRUFLICH physisch geloescht "
            "(inkl. Analyse-Daten und Embeddings). Dies kann NICHT rueckgaengig "
            "gemacht werden.\n\nFortfahren?",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            n = purge_soft_deleted_media(self._project_id)
        except (ValueError, RuntimeError, OSError) as e:
            logger.exception("TrashDialog: purge_soft_deleted_media failed")
            QMessageBox.critical(self, "Papierkorb leeren", f"Endgueltiges Loeschen fehlgeschlagen:\n{e}")
            return
        QMessageBox.information(self, "Papierkorb leeren", f"{n} Medien endgueltig geloescht.")
        self._reload()
