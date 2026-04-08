"""MediaTableController — Refactored from MediaTableMixin."""

import logging
from PySide6.QtWidgets import QTableWidgetItem
from PySide6.QtCore import Qt, QTimer
from services.ingest_service import get_all_audio, get_all_video
from ui.base_component import PBComponent

logger = logging.getLogger(__name__)

class MediaTableController(PBComponent):
    """Controller for Media Tables and Director Combos in PBWindow."""

    def _refresh_director_combos(self):
        from services.ingest_service import get_all_media
        media = get_all_media()
        self.window.audio_combo.clear()
        self.window.video_combo.clear()
        self.window.audio_combo.addItem("-- kein Audio --", None)
        self.window.video_combo.addItem("-- kein Video --", None)
        for item in media:
            label = f"[{item['id']}] {item['title']}"
            if item["type"] == "Audio":
                bpm = item.get("bpm")
                if bpm:
                    label += f" ({bpm} BPM)"
                self.window.audio_combo.addItem(label, item["id"])
            elif item["type"] == "Video":
                self.window.video_combo.addItem(label, item["id"])

    def _toggle_all_checkboxes(self, table):
        """Alle Checkboxen in Spalte 0 toggeln (Alle an / Alle aus)."""
        all_checked = True
        for row in range(table.rowCount()):
            chk = table.item(row, 0)
            if chk and chk.checkState() != Qt.CheckState.Checked:
                all_checked = False
                break
        new_state = Qt.CheckState.Unchecked if all_checked else Qt.CheckState.Checked
        for row in range(table.rowCount()):
            chk = table.item(row, 0)
            if chk:
                chk.setCheckState(new_state)

    def _refresh_media_table(self, _also_combos: bool = True):
        # Einmal laden, ueberall verwenden (statt 4-6 DB-Sessions)
        videos = get_all_video()
        audios = get_all_audio()

        # Video Pool
        self.window.video_pool_table.setRowCount(len(videos))
        for row, item in enumerate(videos):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.window.video_pool_table.setItem(row, 0, chk)
            self.window.video_pool_table.setItem(row, 1, QTableWidgetItem(str(item["id"])))
            self.window.video_pool_table.setItem(row, 2, QTableWidgetItem(item["title"]))
            self.window.video_pool_table.setItem(row, 3, QTableWidgetItem(item.get("resolution") or "-"))
            fps_str = str(item.get("fps", "")) if item.get("fps") else "-"
            self.window.video_pool_table.setItem(row, 4, QTableWidgetItem(fps_str))
            self.window.video_pool_table.setItem(row, 5, QTableWidgetItem(item.get("codec") or "-"))
            self.window.video_pool_table.setItem(row, 6, QTableWidgetItem(item["file_path"]))

        # Audio Pool
        self.window.audio_pool_table.setRowCount(len(audios))
        for row, item in enumerate(audios):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.window.audio_pool_table.setItem(row, 0, chk)
            self.window.audio_pool_table.setItem(row, 1, QTableWidgetItem(str(item["id"])))
            self.window.audio_pool_table.setItem(row, 2, QTableWidgetItem(item["title"]))
            bpm_str = str(item["bpm"]) if item.get("bpm") else "-"
            self.window.audio_pool_table.setItem(row, 3, QTableWidgetItem(bpm_str))
            self.window.audio_pool_table.setItem(row, 4, QTableWidgetItem(item.get("key") or "-"))
            self.window.audio_pool_table.setItem(row, 5, QTableWidgetItem(item.get("stems", "-")))
            self.window.audio_pool_table.setItem(row, 6, QTableWidgetItem(item["file_path"]))

        # Grid views (AUD-72) — update if they exist on window
        if hasattr(self.window, "video_grid"):
            self.window.video_grid.set_items(videos)
        if hasattr(self.window, "audio_grid"):
            self.window.audio_grid.set_items(audios)

        # Hidden proxy table — aus bereits geladenen Daten zusammenbauen
        media = [dict(m, type="Audio") for m in audios] + [dict(m, type="Video") for m in videos]
        self.window.media_table.setRowCount(len(media))
        for row, item in enumerate(media):
            self.window.media_table.setItem(row, 0, QTableWidgetItem(str(item["id"])))
            self.window.media_table.setItem(row, 1, QTableWidgetItem(item["type"]))
            self.window.media_table.setItem(row, 2, QTableWidgetItem(item["title"]))
            bpm_str = str(item["bpm"]) if item.get("bpm") else "-"
            self.window.media_table.setItem(row, 3, QTableWidgetItem(bpm_str))
            res = item.get("resolution", "-")
            self.window.media_table.setItem(row, 4, QTableWidgetItem(res or "-"))
            fps_str = str(item.get("fps", "")) if item.get("fps") else "-"
            self.window.media_table.setItem(row, 5, QTableWidgetItem(fps_str))
            stems = item.get("stems", "-")
            self.window.media_table.setItem(row, 6, QTableWidgetItem(stems))
            self.window.media_table.setItem(row, 7, QTableWidgetItem(item["file_path"]))

        # Director-Combos gleich mit aktualisieren (spart redundante DB-Abfrage)
        if _also_combos:
            self.window.audio_combo.clear()
            self.window.video_combo.clear()
            self.window.audio_combo.addItem("-- kein Audio --", None)
            self.window.video_combo.addItem("-- kein Video --", None)
            for item in media:
                label = f"[{item['id']}] {item['title']}"
                if item["type"] == "Audio":
                    bpm = item.get("bpm")
                    if bpm:
                        label += f" ({bpm} BPM)"
                    self.window.audio_combo.addItem(label, item["id"])
                elif item["type"] == "Video":
                    self.window.video_combo.addItem(label, item["id"])

    def _refresh_media_table_debounced(self) -> None:
        """Debounced media table refresh — coalesces rapid calls."""
        if self.window._refresh_pending:
            return
        self.window._refresh_pending = True
        QTimer.singleShot(200, self._do_refresh_media_table)

    def _do_refresh_media_table(self) -> None:
        """Fuehrt die verzoegerte Aktualisierung der Media-Tabelle aus."""
        self.window._refresh_pending = False
        self._refresh_media_table()
