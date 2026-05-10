"""CutListPanel — textuelle Cutliste fuer das SCHNITT-Sub-Tab (B-295)."""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton,
)
from PySide6.QtGui import QBrush, QColor

logger = logging.getLogger(__name__)

_SOURCE_COLORS = {
    "beat": QColor(74, 222, 128),
    "scene": QColor(96, 165, 250),
    "energy": QColor(251, 191, 36),
    "drum": QColor(248, 113, 113),
    "transition": QColor(167, 139, 250),
    "drop": QColor(244, 114, 182),
    "anchor": QColor(212, 164, 74),
}


class CutListPanel(QWidget):
    """B-295: Cutliste eines Projekts als sortierte Tabelle.

    Spalten: # / Zeit / Dauer / Quelle / Staerke / Lock / Clip.
    Klick auf Zeile → ``cut_selected(time)`` emittiert.
    """

    cut_selected = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project_id: Optional[int] = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("Cutliste")
        title.setStyleSheet(
            "color: #d4a44a; font-weight: 700; font-size: 12px; "
            "letter-spacing: 1.5px; text-transform: uppercase;"
        )
        header.addWidget(title)
        header.addStretch()
        self.btn_refresh = QPushButton("Aktualisieren")
        self.btn_refresh.setFixedHeight(22)
        self.btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self.btn_refresh)
        layout.addLayout(header)

        self.table = QTableWidget(0, 7, self)
        self.table.setHorizontalHeaderLabels(
            ["#", "Zeit", "Dauer", "Quelle", "Staerke", "Lock", "Clip"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self.table)

        self.info_label = QLabel("Noch keine Timeline.")
        self.info_label.setStyleSheet("color: #6b7280; font-size: 10px;")
        layout.addWidget(self.info_label)

    def set_project(self, project_id: Optional[int]) -> None:
        """B-295 Public-API: Projekt setzen + refresh."""
        self._project_id = project_id
        self.refresh()

    def refresh(self) -> None:
        if self._project_id is None:
            self._render_empty("Kein Projekt aktiv.")
            return
        try:
            from services.timeline_service import get_cut_list
            cuts = get_cut_list(self._project_id)
        except Exception as exc:
            logger.warning("CutListPanel.refresh failed: %s", exc)
            self._render_empty(f"Fehler: {exc}")
            return
        self._render_cuts(cuts)

    def _render_empty(self, msg: str) -> None:
        self.table.setRowCount(0)
        self.info_label.setText(msg)

    def _render_cuts(self, cuts: list[dict]) -> None:
        self.table.setRowCount(len(cuts))
        for row, cut in enumerate(cuts):
            self.table.setItem(row, 0, QTableWidgetItem(str(cut["index"])))
            self.table.setItem(row, 1, QTableWidgetItem(f"{cut['time']:.2f}s"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{cut['duration']:.2f}s"))
            src_item = QTableWidgetItem(cut.get("source", ""))
            color = _SOURCE_COLORS.get(cut.get("source", ""), None)
            if color is not None:
                src_item.setForeground(QBrush(color))
            self.table.setItem(row, 3, src_item)
            self.table.setItem(row, 4, QTableWidgetItem(f"{cut.get('strength', 0.0):.2f}"))
            self.table.setItem(row, 5, QTableWidgetItem("LOCK" if cut.get("locked") else ""))
            self.table.setItem(row, 6, QTableWidgetItem(cut.get("title", "")))
        self.info_label.setText(f"{len(cuts)} Cuts.")

    def _on_cell_clicked(self, row: int, column: int) -> None:
        time_item = self.table.item(row, 1)
        if time_item is None:
            return
        try:
            t = float(time_item.text().rstrip("s"))
            self.cut_selected.emit(t)
        except ValueError:
            pass

    def rendered_row_count(self) -> int:
        """B-295 Test-Affordance."""
        return self.table.rowCount()
