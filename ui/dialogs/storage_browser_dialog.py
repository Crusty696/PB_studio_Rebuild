from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from database import nullpool_session
from services.storage_provenance.storage_browser import StorageBrowserService, StorageBrowserRow

logger = logging.getLogger(__name__)


class StorageBrowserDialog(QDialog):
    """Storage-Browser fuer globale Analyse-Provenance."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Storage-Browser")
        self.setMinimumSize(880, 520)
        self._rows: list[StorageBrowserRow] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        filter_row = QHBoxLayout()
        self._unused_only = QCheckBox("nicht-genutzt in Projekten")
        self._unused_only.setToolTip("Nur Quellen anzeigen, die aktuell keinem Projekt zugeordnet sind.")
        self._unused_only.toggled.connect(self.refresh)
        filter_row.addWidget(self._unused_only)

        filter_row.addWidget(QLabel("alt >"))
        self._older_than_days = QSpinBox()
        self._older_than_days.setRange(0, 3650)
        self._older_than_days.setSuffix(" Tage")
        self._older_than_days.setToolTip("0 deaktiviert den Altersfilter.")
        self._older_than_days.valueChanged.connect(self.refresh)
        filter_row.addWidget(self._older_than_days)
        filter_row.addStretch()

        self._refresh_btn = QPushButton("Aktualisieren")
        self._refresh_btn.clicked.connect(self.refresh)
        filter_row.addWidget(self._refresh_btn)
        layout.addLayout(filter_row)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["SHA", "Datei", "Projekte", "Stages", "Bytes", "Last Used", "Aktion"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self._summary = QLabel("0 Quellen")
        bottom.addWidget(self._summary)
        bottom.addStretch()
        self._delete_selected_btn = QPushButton("Ausgewaehlte loeschen")
        self._delete_selected_btn.setToolTip("Analysen fuer alle ausgewaehlten Zeilen nach Bestaetigung loeschen.")
        self._delete_selected_btn.clicked.connect(self._delete_selected)
        bottom.addWidget(self._delete_selected_btn)
        layout.addLayout(bottom)

    def refresh(self) -> None:
        try:
            with nullpool_session() as session:
                service = StorageBrowserService(session)
                self._rows = service.list_sources(
                    unused_only=self._unused_only.isChecked(),
                    older_than_days=self._older_than_days.value() or None,
                )
        except Exception as exc:
            logger.exception("StorageBrowserDialog refresh failed")
            QMessageBox.critical(self, "Storage-Browser", f"Laden fehlgeschlagen: {exc}")
            self._rows = []
        self._populate()

    def _populate(self) -> None:
        self.table.setRowCount(len(self._rows))
        for row_idx, row in enumerate(self._rows):
            sha_item = QTableWidgetItem(row.short_sha)
            sha_item.setData(Qt.ItemDataRole.UserRole, row.source_sha256)
            sha_item.setToolTip(row.source_sha256)
            self.table.setItem(row_idx, 0, sha_item)
            self.table.setItem(row_idx, 1, QTableWidgetItem(row.file_name))
            self.table.setItem(row_idx, 2, QTableWidgetItem(row.projects_used_by))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(row.stages_done)))
            self.table.setItem(row_idx, 4, QTableWidgetItem(_format_bytes(row.total_bytes)))
            self.table.setItem(row_idx, 5, QTableWidgetItem(_format_datetime(row.last_used)))

            delete_btn = QPushButton("Analysen loeschen")
            delete_btn.setToolTip("Analysen dieser Quelle nach Bestaetigung loeschen.")
            delete_btn.clicked.connect(lambda _checked=False, source_sha=row.source_sha256: self._delete_sources([source_sha]))
            self.table.setCellWidget(row_idx, 6, delete_btn)

        self._summary.setText(f"{len(self._rows)} Quellen")
        self._delete_selected_btn.setEnabled(bool(self._rows))

    def _selected_sources(self) -> list[str]:
        sources: list[str] = []
        for item in self.table.selectedItems():
            if item.column() != 0:
                continue
            source_sha = item.data(Qt.ItemDataRole.UserRole)
            if source_sha:
                sources.append(str(source_sha))
        return sorted(set(sources))

    def _delete_selected(self) -> None:
        self._delete_sources(self._selected_sources())

    def _delete_sources(self, source_hashes: list[str]) -> None:
        if not source_hashes:
            QMessageBox.information(self, "Storage-Browser", "Keine Zeile ausgewaehlt.")
            return
        reply = QMessageBox.question(
            self,
            "Analysen loeschen",
            f"Wirklich Analysen fuer {len(source_hashes)} Quelle(n) loeschen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            with nullpool_session() as session:
                result = StorageBrowserService(session).delete_analysis_sources(source_hashes)
        except Exception as exc:
            logger.exception("StorageBrowserDialog delete failed")
            QMessageBox.critical(self, "Storage-Browser", f"Loeschen fehlgeschlagen: {exc}")
            return
        QMessageBox.information(
            self,
            "Storage-Browser",
            f"{result.deleted_jobs} Analyse-Job(s) geloescht.",
        )
        self.refresh()


def _format_bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KB"
    if value < 1024 * 1024 * 1024:
        return f"{value / (1024 * 1024):.1f} MB"
    return f"{value / (1024 * 1024 * 1024):.1f} GB"


def _format_datetime(value) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M")
