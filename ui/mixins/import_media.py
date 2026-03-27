"""Import-Media Mixin fuer PBWindow."""

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog

from services.ingest_service import (
    delete_all_media, delete_selected_media, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS,
)
from workers import FolderImportWorker


class ImportMediaMixin:
    """Media import methods for PBWindow."""

    def _import_video(self):
        ext_filter = "Video-Dateien (" + " ".join(f"*{e}" for e in VIDEO_EXTENSIONS) + ")"
        paths, _ = QFileDialog.getOpenFileNames(self, "Videos importieren", "", ext_filter)
        self._process_imports(paths, "video")

    def _import_audio(self):
        ext_filter = "Audio-Dateien (" + " ".join(f"*{e}" for e in AUDIO_EXTENSIONS) + ")"
        paths, _ = QFileDialog.getOpenFileNames(self, "Audio importieren", "", ext_filter)
        self._process_imports(paths, "audio")

    def _process_imports(self, paths: list[str], media_type: str):
        """F-004 Fix: Imports laufen im Hintergrund-Thread (FolderImportWorker) statt synchron."""
        if not paths:
            return
        paths_audio = paths if media_type == "audio" else []
        paths_video = paths if media_type == "video" else []

        self.console_text.append(f"[Import] {len(paths)} {media_type.capitalize()}-Datei(en) werden importiert ...")
        self.status_bar.showMessage(f"Importiere {len(paths)} Datei(en) ...")

        worker = FolderImportWorker(paths_audio, paths_video)
        worker.file_imported.connect(self.console_text.append)
        worker.progress.connect(
            lambda pct, msg: self.status_bar.showMessage(f"[Import] {pct}% — {msg}")
        )

        def _on_finish(added: int, new_video_clips: list):
            if added:
                self._refresh_media_table()
                for clip_id, video_path, title in new_video_clips:
                    self._start_proxy_creation(clip_id, video_path, title)
            self.status_bar.showMessage(f"{added} Datei(en) importiert | System bereit")

        def _on_error(msg: str):
            self.console_text.append(f"[Fehler] Import abgebrochen: {msg}")
            self.status_bar.showMessage("Import fehlgeschlagen | System bereit")

        self._start_worker_thread(worker, on_finish=_on_finish, on_error=_on_error)

    def _import_folder(self):
        """Importiert alle unterstuetzten Medien aus einem Ordner (rekursiv, Hintergrund-Thread)."""
        folder = QFileDialog.getExistingDirectory(self, "Ordner importieren")
        if not folder:
            return
        paths_audio: list[str] = []
        paths_video: list[str] = []
        for root, _dirs, files in os.walk(folder):
            for f in files:
                ext = Path(f).suffix.lower()
                full = os.path.join(root, f)
                if ext in AUDIO_EXTENSIONS:
                    paths_audio.append(full)
                elif ext in VIDEO_EXTENSIONS:
                    paths_video.append(full)
        total = len(paths_audio) + len(paths_video)
        if total == 0:
            self.console_text.append(f"[Warnung] Keine unterstuetzten Medien in: {folder}")
            return
        self.console_text.append(f"[Ordner] {total} Dateien gefunden in: {folder}")
        self.status_bar.showMessage(f"Importiere {total} Dateien aus Ordner ...")

        worker = FolderImportWorker(paths_audio, paths_video)

        worker.file_imported.connect(self.console_text.append)
        worker.progress.connect(
            lambda pct, msg: self.status_bar.showMessage(f"[Import] {pct}% — {msg}")
        )

        def _on_finish(added: int, new_video_clips: list):
            if added:
                self._refresh_media_table()
                for clip_id, video_path, title in new_video_clips:
                    self._start_proxy_creation(clip_id, video_path, title)
            self.status_bar.showMessage(
                f"{added} Datei(en) aus Ordner importiert | System bereit"
            )

        def _on_error(msg: str):
            self.console_text.append(f"[Fehler] Ordner-Import abgebrochen: {msg}")
            self.status_bar.showMessage("Import fehlgeschlagen | System bereit")

        self._start_worker_thread(worker, on_finish=_on_finish, on_error=_on_error)

    def _clear_all_media(self):
        """Loescht alle Medien aus Datenbank und UI."""
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Sammlung bereinigen",
            "Alle Medien aus der Datenbank entfernen?\nDie Original-Dateien bleiben erhalten.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            count = delete_all_media()
            self._refresh_media_table()
            self.console_text.append(f"[System] {count} Medien-Eintraege geloescht.")
            self.status_bar.showMessage(f"Sammlung bereinigt ({count} Eintraege) | System bereit")

    def _delete_selected_media(self, pool: str):
        """Loescht alle angehakten Medien (Checkboxen) aus Video oder Audio Pool."""
        from PySide6.QtWidgets import QMessageBox

        video_ids = []
        audio_ids = []

        if pool in ("video", "both"):
            for row in range(self.video_pool_table.rowCount()):
                chk = self.video_pool_table.item(row, 0)
                id_item = self.video_pool_table.item(row, 1)
                if chk and id_item and chk.checkState() == Qt.CheckState.Checked:
                    try:
                        video_ids.append(int(id_item.text()))
                    except ValueError:
                        pass

        if pool in ("audio", "both"):
            for row in range(self.audio_pool_table.rowCount()):
                chk = self.audio_pool_table.item(row, 0)
                id_item = self.audio_pool_table.item(row, 1)
                if chk and id_item and chk.checkState() == Qt.CheckState.Checked:
                    try:
                        audio_ids.append(int(id_item.text()))
                    except ValueError:
                        pass

        total = len(video_ids) + len(audio_ids)
        if total == 0:
            QMessageBox.information(
                self, "Nichts ausgewaehlt",
                "Bitte setze zuerst die Checkboxen der zu loeschenden Medien.",
            )
            return

        reply = QMessageBox.question(
            self, "Medien loeschen",
            f"{total} Medium/Medien aus der Datenbank entfernen?\n"
            "Die Original-Dateien bleiben erhalten.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            count = delete_selected_media(video_ids, audio_ids)
            self._refresh_media_table()
            self.console_text.append(f"[System] {count} Medien-Eintraege geloescht.")
            self.status_bar.showMessage(f"{count} Medien geloescht | System bereit")
