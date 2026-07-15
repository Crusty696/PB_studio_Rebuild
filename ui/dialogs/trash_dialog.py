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
from workers.base import BaseWorker, run_worker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Alle drei Papierkorb-Operationen liefen frueher synchron im GUI-Thread:
#   _reload   -> get_soft_deleted_media   (2x query.all, u.a. aus __init__
#                -> der Dialog blockierte schon beim Oeffnen)
#   _on_purge -> purge_soft_deleted_media (kaskadierende DELETEs ueber Scene/
#                Beatgrid/WaveformData/... PLUS VectorDB-Embedding-Cleanup)
#   _on_restore -> restore_media
# Repo-Norm ist, solche Arbeit ueber BaseWorker/run_worker auszulagern
# (QueuedConnection zurueck in den GUI-Thread).
# ---------------------------------------------------------------------------

class _TrashLoadWorker(BaseWorker):
    """Laedt die soft-geloeschten Medien off-thread."""

    def __init__(self, project_id):
        super().__init__()
        self._project_id = project_id

    def _do_work(self):
        return get_soft_deleted_media(self._project_id)


class _TrashRestoreWorker(BaseWorker):
    """Stellt ausgewaehlte Medien off-thread wieder her."""

    def __init__(self, video_ids: list[int], audio_ids: list[int]):
        super().__init__()
        self._video_ids = list(video_ids)
        self._audio_ids = list(audio_ids)

    def _do_work(self):
        return restore_media(self._video_ids, self._audio_ids)


class _TrashPurgeWorker(BaseWorker):
    """Leert den Papierkorb off-thread (DB-Kaskade + VectorDB-Cleanup)."""

    def __init__(self, project_id):
        super().__init__()
        self._project_id = project_id

    def _do_work(self):
        return purge_soft_deleted_media(self._project_id)


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
    def _set_busy(self, text: str) -> None:
        """Sperrt die Aktionen, solange eine Operation off-thread laeuft.

        Entsperrt wird nicht hier, sondern in ``_populate`` — jeder Pfad
        (Erfolg wie Fehler) endet dort und setzt die Buttons anhand des dann
        tatsaechlichen Tabellen-Inhalts.
        """
        self.btn_restore.setEnabled(False)
        self.btn_purge.setEnabled(False)
        self._info.setText(text)

    def _reload(self) -> None:
        """Laedt den Papierkorb off-thread und fuellt danach die Tabelle."""
        self._set_busy("Lade Papierkorb…")
        run_worker(
            self,
            _TrashLoadWorker(self._project_id),
            on_finish=self._on_loaded,
            on_error=self._on_load_error,
        )

    def _on_load_error(self, msg: str) -> None:
        logger.error("TrashDialog: get_soft_deleted_media failed: %s", msg)
        QMessageBox.critical(self, "Papierkorb", f"Papierkorb laden fehlgeschlagen:\n{msg}")
        self._populate([])

    def _on_loaded(self, items) -> None:
        self._populate(list(items or []))

    def _populate(self, items) -> None:
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
        self._set_busy("Stelle wieder her…")
        run_worker(
            self,
            _TrashRestoreWorker(video_ids, audio_ids),
            on_finish=self._on_restored,
            on_error=self._on_restore_error,
        )

    def _on_restore_error(self, msg: str) -> None:
        logger.error("TrashDialog: restore_media failed: %s", msg)
        QMessageBox.critical(self, "Wiederherstellen", f"Wiederherstellen fehlgeschlagen:\n{msg}")
        self._reload()

    def _on_restored(self, n) -> None:
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
        # Kaskadierende DELETEs + VectorDB-Embedding-Cleanup — bei vielen Clips
        # spuerbar. Lief frueher synchron im Klick-Handler.
        self._set_busy("Loesche endgueltig…")
        run_worker(
            self,
            _TrashPurgeWorker(self._project_id),
            on_finish=self._on_purged,
            on_error=self._on_purge_error,
        )

    def _on_purge_error(self, msg: str) -> None:
        logger.error("TrashDialog: purge_soft_deleted_media failed: %s", msg)
        QMessageBox.critical(self, "Papierkorb leeren", f"Endgueltiges Loeschen fehlgeschlagen:\n{msg}")
        self._reload()

    def _on_purged(self, n) -> None:
        QMessageBox.information(self, "Papierkorb leeren", f"{n} Medien endgueltig geloescht.")
        self._reload()
