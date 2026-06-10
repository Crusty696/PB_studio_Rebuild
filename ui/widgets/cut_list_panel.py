"""CutListPanel — textuelle Cutliste fuer das SCHNITT-Sub-Tab (B-295).

I-1 follow-up (post 13208ac): Source/Strength-Spalten entfernt bis Schema-
Migration cut_source/cut_strength persistent macht. Aktuelles Schema
hat diese Felder nicht — get_cut_list liefert sie zwar weiter (Forward-
Compat), aber UI rendert sie aktuell nicht (kein leeres-Spalten-Lying).
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton, QMenu,
)

# M-5: Module-top import statt lokalem Import in refresh().
from services.timeline_service import get_cut_list

logger = logging.getLogger(__name__)


class CutListPanel(QWidget):
    """B-295: Cutliste eines Projekts als sortierte Tabelle.

    Spalten (5, post I-1): # / Zeit / Dauer / Lock / Clip.
    Klick auf Zeile -> cut_selected(time) emittiert.
    """

    cut_selected = Signal(float)
    # B-295: Edit-Affordances via Kontextmenue. entry_id = TimelineEntry-ID.
    cut_lock_toggle_requested = Signal(int, bool)  # (entry_id, new_locked)
    cut_remove_requested = Signal(int)             # (entry_id)

    # ItemDataRole-Offsets fuer Zeilen-Metadaten am "#"-Item (Spalte 0).
    _ROLE_ENTRY_ID = int(Qt.ItemDataRole.UserRole) + 10
    _ROLE_LOCKED = int(Qt.ItemDataRole.UserRole) + 11

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
        self.btn_refresh.setToolTip("Cutliste aus der aktuellen Timeline neu laden.")
        self.btn_refresh.setAccessibleName("Cutliste aktualisieren")
        self.btn_refresh.clicked.connect(self.refresh)
        header.addWidget(self.btn_refresh)
        layout.addLayout(header)

        # I-1: 5 Spalten statt 7 — Source/Strength entfernt bis Schema-Migration.
        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(
            ["#", "Zeit", "Dauer", "Lock", "Clip"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setToolTip(
            "Cutliste der aktuellen Timeline. Zeile anklicken setzt den Playhead "
            "auf den Cut-Zeitpunkt."
        )
        self.table.setAccessibleName("Cutliste der aktuellen Timeline")
        self.table.cellClicked.connect(self._on_cell_clicked)
        # B-295: Rechtsklick-Kontextmenue (Sperren/Entsperren, Cut entfernen).
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.table)

        # M-2: konsistenter initial-Empty-State-Text (vorher "Noch keine Timeline.").
        self.info_label = QLabel("Kein Projekt aktiv. — set_project() rufen.")
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
            cuts = get_cut_list(self._project_id)
        # M-3: broad fuer UI-Safety. Erwartete Exceptions: SQLAlchemyError
        # (DB-Drift / lock), ImportError (Service-Modul-Drift), AttributeError
        # (Schema-Drift TimelineEntry/VideoClip), KeyError (dict-Schema-Drift).
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
            idx_item = QTableWidgetItem(str(cut["index"]))
            # B-295: entry_id + locked am "#"-Item ablegen fuer das Kontextmenue.
            if cut.get("entry_id") is not None:
                idx_item.setData(self._ROLE_ENTRY_ID, int(cut["entry_id"]))
            idx_item.setData(self._ROLE_LOCKED, bool(cut.get("locked")))
            self.table.setItem(row, 0, idx_item)
            # I-2: Time als UserRole-Daten attachieren — Klick liest Wert
            # statt Display-String zu parsen (Locale-safe gegen Dezimaltrenner).
            time_item = QTableWidgetItem(f"{cut['time']:.2f}s")
            time_item.setData(Qt.ItemDataRole.UserRole, float(cut["time"]))
            self.table.setItem(row, 1, time_item)
            self.table.setItem(row, 2, QTableWidgetItem(f"{cut['duration']:.2f}s"))
            self.table.setItem(row, 3, QTableWidgetItem("LOCK" if cut.get("locked") else ""))
            self.table.setItem(row, 4, QTableWidgetItem(cut.get("title", "")))
        self.info_label.setText(f"{len(cuts)} Cuts.")

    def _on_cell_clicked(self, row: int, column: int) -> None:
        time_item = self.table.item(row, 1)
        if time_item is None:
            return
        # I-2: UserRole-Wert statt Display-String parsen (Locale-safe).
        t = time_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(t, (int, float)):
            self.cut_selected.emit(float(t))

    def _on_context_menu(self, pos) -> None:
        """B-295: Rechtsklick-Menue auf einer Cut-Zeile — Sperren/Entsperren + Entfernen."""
        item = self.table.itemAt(pos)
        if item is None:
            return
        idx_item = self.table.item(item.row(), 0)
        if idx_item is None:
            return
        entry_id = idx_item.data(self._ROLE_ENTRY_ID)
        if entry_id is None:
            return
        entry_id = int(entry_id)
        locked = bool(idx_item.data(self._ROLE_LOCKED))

        menu = QMenu(self)
        act_lock = menu.addAction("Entsperren" if locked else "Sperren")
        act_remove = menu.addAction("Cut entfernen")
        chosen = self._exec_menu(menu, self.table.viewport().mapToGlobal(pos))
        if chosen is act_lock:
            self.cut_lock_toggle_requested.emit(entry_id, not locked)
        elif chosen is act_remove:
            self.cut_remove_requested.emit(entry_id)

    def _exec_menu(self, menu: QMenu, global_pos):
        """Gekapselter modaler Menue-Aufruf — in Tests patchbar (``QMenu.exec``
        ist eine C++-Methode und laesst sich nicht direkt monkeypatchen)."""
        return menu.exec(global_pos)

    def rendered_row_count(self) -> int:
        """B-295 Test-Affordance."""
        return self.table.rowCount()
