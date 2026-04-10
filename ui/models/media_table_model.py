"""QAbstractTableModel for efficient Media Pool rendering (Fix F-006)."""

from __future__ import annotations
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex
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

    def setData(self, index: QModelIndex, value: any, role: int = Qt.ItemDataRole.EditRole) -> bool:
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
        return list(self._checked_ids)

    def toggle_all(self):
        """Alle sichtbaren Zeilen toggeln."""
        if len(self._checked_ids) == len(self._items):
            self._checked_ids.clear()
        else:
            self._checked_ids = {i["id"] for i in self._items}
        self.layoutChanged.emit()
