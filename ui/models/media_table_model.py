"""QAbstractTableModel for efficient Media Pool rendering (Fix F-006).

P9-C: ``PagedProxyModel`` unten haelt den Pool auf eine feste Seiten-
groesse (Default 16 Zeilen) — damit brauchen wir in der UI keine
Scrollbar und die Toolbar zeigt die klassische ``Seite 1 / N``-Pager.
"""

from __future__ import annotations
from typing import Any
from PySide6.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Signal,
)
import logging

logger = logging.getLogger(__name__)

class MediaTableModel(QAbstractTableModel):
    """Modernes Model für Video- und Audio-Pools. Ersetzt QTableWidget-Loops."""

    def __init__(self, media_type: str = "Video"):
        super().__init__()
        self._media_type = media_type  # "Video" oder "Audio"
        self._items: list[dict] = []
        self._checked_ids: set[int] = set()
        
        # Header Definitionen
        if media_type == "Video":
            self._headers = ["✓", "ID", "Titel", "Auflösung", "FPS", "Codec", "Analyse %", "Pfad"]
            self._keys = ["_chk", "id", "title", "resolution", "fps", "codec", "analysis_percent", "file_path"]
        else:
            self._headers = ["✓", "ID", "Titel", "BPM", "Tonart", "Stems", "Analyse %", "Pfad"]
            self._keys = ["_chk", "id", "title", "bpm", "key", "stems", "analysis_percent", "file_path"]

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._items)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self._headers)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self._headers[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        col = index.column()
        item = self._items[row]
        key = self._keys[col]

        if role == Qt.ItemDataRole.DisplayRole:
            if key == "_chk": return ""
            if key == "analysis_percent":
                percent = item.get(key, 0)
                if isinstance(percent, (int, float)):
                    return f"{int(percent)}%"
                return "-"
            val = item.get(key)
            return str(val) if val is not None else "-"

        # Color coding for analysis_percent column
        if role == Qt.ItemDataRole.ForegroundRole and key == "analysis_percent":
            from PySide6.QtGui import QColor, QBrush
            percent = item.get(key, 0)
            if isinstance(percent, (int, float)):
                if percent >= 100:
                    return QBrush(QColor(74, 222, 128))  # Green
                elif percent >= 50:
                    return QBrush(QColor(212, 164, 74))  # Yellow
                elif percent > 0:
                    return QBrush(QColor(156, 163, 175))  # Gray
            return QBrush(QColor(107, 114, 128))  # Dark gray for 0%

        if role == Qt.ItemDataRole.CheckStateRole and key == "_chk":
            return Qt.CheckState.Checked if item["id"] in self._checked_ids else Qt.CheckState.Unchecked

        return None

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if role == Qt.ItemDataRole.CheckStateRole and self._keys[index.column()] == "_chk":
            item_id = self._items[index.row()]["id"]
            if value == Qt.CheckState.Checked:
                self._checked_ids.add(item_id)
            else:
                self._checked_ids.discard(item_id)
            self.dataChanged.emit(index, index, [role])
            return True
        return False

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        base_flags = super().flags(index)
        if self._keys[index.column()] == "_chk":
            return base_flags | Qt.ItemFlag.ItemIsUserCheckable
        return base_flags

    def set_items(self, items: list[dict]):
        """Aktualisiert die Daten effizient."""
        self.beginResetModel()
        self._items = items
        # Bestehende Check-Zustände beibehalten wenn IDs noch existieren
        current_ids = {i["id"] for i in items}
        self._checked_ids = self._checked_ids.intersection(current_ids)
        self.endResetModel()

    def get_checked_ids(self) -> list[int]:
        return [i["id"] for i in self._items if i["id"] in self._checked_ids]

    def toggle_all(self):
        """Alle sichtbaren Zeilen toggeln."""
        if len(self._checked_ids) == len(self._items):
            self._checked_ids.clear()
        else:
            self._checked_ids = {i["id"] for i in self._items}
        self.layoutChanged.emit()


class PagedProxyModel(QSortFilterProxyModel):
    """Paginations-Proxy fuer den MEDIA-Pool.

    Zeigt immer genau ``page_size`` Zeilen (Default 16) aus dem Source-Model;
    per ``set_page(n)`` wechselt die UI den Ausschnitt.
    """

    pagesChanged = Signal()  # emittiert wenn Seitenzahl sich aendert

    def __init__(self, page_size: int = 16, parent=None):
        super().__init__(parent)
        self._page_size = max(1, int(page_size))
        self._page = 0

    # ------------------------------------------------------------------
    def filterAcceptsRow(self, source_row: int, _parent: QModelIndex) -> bool:  # type: ignore[override]
        start = self._page * self._page_size
        end = start + self._page_size
        return start <= source_row < end

    # ------------------------------------------------------------------
    def setSourceModel(self, source):  # type: ignore[override]
        old = self.sourceModel()
        if old is not None:
            try:
                old.modelReset.disconnect(self._on_source_changed)
                old.rowsInserted.disconnect(self._on_source_changed)
                old.rowsRemoved.disconnect(self._on_source_changed)
            except (TypeError, RuntimeError):
                pass
        super().setSourceModel(source)
        if source is not None:
            source.modelReset.connect(self._on_source_changed)
            source.rowsInserted.connect(self._on_source_changed)
            source.rowsRemoved.connect(self._on_source_changed)
        self._clamp_page()
        self.pagesChanged.emit()

    def _on_source_changed(self, *_args):
        self._clamp_page()
        self.invalidateFilter()
        self.pagesChanged.emit()

    # ------------------------------------------------------------------
    def page_size(self) -> int:
        return self._page_size

    def set_page_size(self, n: int):
        n = max(1, int(n))
        if n != self._page_size:
            self._page_size = n
            self._clamp_page()
            self.invalidateFilter()
            self.pagesChanged.emit()

    def page(self) -> int:
        return self._page

    def page_count(self) -> int:
        src = self.sourceModel()
        total = src.rowCount() if src is not None else 0
        return max(1, (total + self._page_size - 1) // self._page_size)

    def set_page(self, page: int):
        page = max(0, min(int(page), self.page_count() - 1))
        if page != self._page:
            self._page = page
            self.invalidateFilter()
            self.pagesChanged.emit()

    def next_page(self):
        self.set_page(self._page + 1)

    def prev_page(self):
        self.set_page(self._page - 1)

    def _clamp_page(self):
        pc = self.page_count()
        if self._page >= pc:
            self._page = pc - 1
        if self._page < 0:
            self._page = 0

    # ------------------------------------------------------------------
    # Pass-through helpers — der Proxy leitet die Model-spezifischen APIs
    # (Check-Listen, Toggle, set_items) ans Source-Model weiter, damit
    # bestehende Controller weiterhin `pool_table.model().<...>` nutzen
    # koennen.
    # ------------------------------------------------------------------
    def get_checked_ids(self) -> list[int]:
        src = self.sourceModel()
        return src.get_checked_ids() if src is not None else []

    def toggle_all(self):
        src = self.sourceModel()
        if src is not None:
            src.toggle_all()

    def set_items(self, items: list[dict]):
        src = self.sourceModel()
        if src is not None:
            src.set_items(items)
