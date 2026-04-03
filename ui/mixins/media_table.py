"""MediaTableMixin — extrahiert aus main.py (AUD-44).

Kapselt:
  - _refresh_director_combos()  — Audio/Video-Combos im EDIT-Workspace befuellen
  - _toggle_all_checkboxes()    — Alle Checkboxen in einer Tabelle toggeln
  - _refresh_media_table()      — Video/Audio Pool + Proxy-Tabelle aktualisieren
"""

from PySide6.QtWidgets import QTableWidgetItem
from PySide6.QtCore import Qt

from services.ingest_service import get_all_audio, get_all_video


class MediaTableMixin:
    """Mixin fuer MainWindow: Media-Tabellen und Director-Combos."""

    def _refresh_director_combos(self):
        from services.ingest_service import get_all_media
        media = get_all_media()
        self.audio_combo.clear()
        self.video_combo.clear()
        self.audio_combo.addItem("-- kein Audio --", None)
        self.video_combo.addItem("-- kein Video --", None)
        for item in media:
            label = f"[{item['id']}] {item['title']}"
            if item["type"] == "Audio":
                bpm = item.get("bpm")
                if bpm:
                    label += f" ({bpm} BPM)"
                self.audio_combo.addItem(label, item["id"])
            elif item["type"] == "Video":
                self.video_combo.addItem(label, item["id"])

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
        self.video_pool_table.setRowCount(len(videos))
        for row, item in enumerate(videos):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.video_pool_table.setItem(row, 0, chk)
            self.video_pool_table.setItem(row, 1, QTableWidgetItem(str(item["id"])))
            self.video_pool_table.setItem(row, 2, QTableWidgetItem(item["title"]))
            self.video_pool_table.setItem(row, 3, QTableWidgetItem(item.get("resolution") or "-"))
            fps_str = str(item.get("fps", "")) if item.get("fps") else "-"
            self.video_pool_table.setItem(row, 4, QTableWidgetItem(fps_str))
            self.video_pool_table.setItem(row, 5, QTableWidgetItem("-"))
            self.video_pool_table.setItem(row, 6, QTableWidgetItem(item["file_path"]))

        # Audio Pool
        self.audio_pool_table.setRowCount(len(audios))
        for row, item in enumerate(audios):
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            chk.setCheckState(Qt.CheckState.Unchecked)
            self.audio_pool_table.setItem(row, 0, chk)
            self.audio_pool_table.setItem(row, 1, QTableWidgetItem(str(item["id"])))
            self.audio_pool_table.setItem(row, 2, QTableWidgetItem(item["title"]))
            bpm_str = str(item["bpm"]) if item.get("bpm") else "-"
            self.audio_pool_table.setItem(row, 3, QTableWidgetItem(bpm_str))
            self.audio_pool_table.setItem(row, 4, QTableWidgetItem("-"))
            self.audio_pool_table.setItem(row, 5, QTableWidgetItem(item.get("stems", "-")))
            self.audio_pool_table.setItem(row, 6, QTableWidgetItem(item["file_path"]))

        # Grid views (AUD-72) — update if they exist on self
        if hasattr(self, "video_grid"):
            self.video_grid.set_items(videos)
        if hasattr(self, "audio_grid"):
            self.audio_grid.set_items(audios)

        # Hidden proxy table — aus bereits geladenen Daten zusammenbauen
        media = [dict(m, type="Audio") for m in audios] + [dict(m, type="Video") for m in videos]
        self.media_table.setRowCount(len(media))
        for row, item in enumerate(media):
            self.media_table.setItem(row, 0, QTableWidgetItem(str(item["id"])))
            self.media_table.setItem(row, 1, QTableWidgetItem(item["type"]))
            self.media_table.setItem(row, 2, QTableWidgetItem(item["title"]))
            bpm_str = str(item["bpm"]) if item.get("bpm") else "-"
            self.media_table.setItem(row, 3, QTableWidgetItem(bpm_str))
            res = item.get("resolution", "-")
            self.media_table.setItem(row, 4, QTableWidgetItem(res or "-"))
            fps_str = str(item.get("fps", "")) if item.get("fps") else "-"
            self.media_table.setItem(row, 5, QTableWidgetItem(fps_str))
            stems = item.get("stems", "-")
            self.media_table.setItem(row, 6, QTableWidgetItem(stems))
            self.media_table.setItem(row, 7, QTableWidgetItem(item["file_path"]))

        # Director-Combos gleich mit aktualisieren (spart redundante DB-Abfrage)
        if _also_combos:
            self.audio_combo.clear()
            self.video_combo.clear()
            self.audio_combo.addItem("-- kein Audio --", None)
            self.video_combo.addItem("-- kein Video --", None)
            for item in media:
                label = f"[{item['id']}] {item['title']}"
                if item["type"] == "Audio":
                    bpm = item.get("bpm")
                    if bpm:
                        label += f" ({bpm} BPM)"
                    self.audio_combo.addItem(label, item["id"])
                elif item["type"] == "Video":
                    self.video_combo.addItem(label, item["id"])
