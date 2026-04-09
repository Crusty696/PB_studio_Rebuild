"""ImportMediaController — Refactored from ImportMediaMixin."""

import logging
import os
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog
from services.ingest_service import (
    delete_all_media, delete_selected_media, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS,
)
from workers import FolderImportWorker
from ui.base_component import PBComponent

logger = logging.getLogger(__name__)

class ImportMediaController(PBComponent):
    """Media import methods for PBWindow."""

    def _import_video(self):
        ext_filter = "Video-Dateien (" + " ".join(f"*{e}" for e in VIDEO_EXTENSIONS) + ")"
        paths, _ = QFileDialog.getOpenFileNames(self.window, "Videos importieren", "", ext_filter)
        self._process_imports(paths, "video")

    def _import_audio(self):
        ext_filter = "Audio-Dateien (" + " ".join(f"*{e}" for e in AUDIO_EXTENSIONS) + ")"
        paths, _ = QFileDialog.getOpenFileNames(self.window, "Audio importieren", "", ext_filter)
        self._process_imports(paths, "audio")

    def _process_imports(self, paths: list[str], media_type: str):
        """Imports laufen im Hintergrund-Thread."""
        if not paths:
            return
        paths_audio = paths if media_type == "audio" else []
        paths_video = paths if media_type == "video" else []

        self.window.console_text.append(f"[Import] {len(paths)} {media_type.capitalize()}-Datei(en) werden importiert ...")
        self.window.status_bar.showMessage(f"Importiere {len(paths)} Datei(en) ...")

        worker = FolderImportWorker(paths_audio, paths_video)
        worker.file_imported.connect(self.window.console_text.append)
        worker.progress.connect(
            lambda pct, msg: self.window.status_bar.showMessage(f"[Import] {pct}% — {msg}")
        )

        def _on_finish(added: int, new_video_clips: list):
            if added:
                self.window.media_table_controller._refresh_media_table()
                for clip_id, video_path, title in new_video_clips:
                    self.window.video_analysis._start_proxy_creation(clip_id, video_path, title)
                self.window._mark_dirty()
            self.window.status_bar.showMessage(f"{added} Datei(en) importiert | System bereit")

        def _on_error(msg: str):
            self.window.console_text.append(f"[Fehler] Import abgebrochen: {msg}")
            self.window.status_bar.showMessage("Import fehlgeschlagen | System bereit")

        self.window.worker_dispatcher._start_worker_thread(worker, on_finish=_on_finish, on_error=_on_error)

    def _import_folder(self):
        """Importiert alle unterstuetzten Medien aus einem Ordner."""
        folder = QFileDialog.getExistingDirectory(self.window, "Ordner importieren")
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
            self.window.console_text.append(f"[Warnung] Keine unterstuetzten Medien in: {folder}")
            return
        self.window.console_text.append(f"[Ordner] {total} Dateien gefunden in: {folder}")
        self.window.status_bar.showMessage(f"Importiere {total} Dateien aus Ordner ...")

        worker = FolderImportWorker(paths_audio, paths_video)
        worker.file_imported.connect(self.window.console_text.append)
        worker.progress.connect(
            lambda pct, msg: self.window.status_bar.showMessage(f"[Import] {pct}% — {msg}")
        )

        def _on_finish(added: int, new_video_clips: list):
            if added:
                self.window.media_table_controller._refresh_media_table()
                for clip_id, video_path, title in new_video_clips:
                    self.window.video_analysis._start_proxy_creation(clip_id, video_path, title)
                self.window._mark_dirty()
            self.window.status_bar.showMessage(f"{added} Datei(en) aus Ordner importiert | System bereit")

        def _on_error(msg: str):
            self.window.console_text.append(f"[Fehler] Ordner-Import abgebrochen: {msg}")
            self.window.status_bar.showMessage("Import fehlgeschlagen | System bereit")

        self.window.worker_dispatcher._start_worker_thread(worker, on_finish=_on_finish, on_error=_on_error)

    def _clear_all_media(self):
        """Loescht alle Medien asynchron aus Datenbank und UI (Fix F-045)."""
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self.window, "Sammlung bereinigen",
            "Alle Medien aus der Datenbank entfernen?\nDie Original-Dateien bleiben erhalten.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            from PySide6.QtCore import QObject, Signal
            class DeleteWorker(QObject):
                finished = Signal(int)
                def run(self):
                    count = delete_all_media()
                    self.finished.emit(count)

            worker = DeleteWorker()
            def _on_done(count):
                self.window.media_table_controller._refresh_media_table()
                self.window._mark_dirty()
                self.window.console_text.append(f"[System] {count} Medien-Eintraege geloescht.")
                self.window.status_bar.showMessage(f"Sammlung bereinigt ({count} Eintraege)")

            from services.task_manager import GlobalTaskManager
            GlobalTaskManager.instance().start_task(
                name="Datenbank bereinigen",
                worker=worker,
                description="Entfernt alle Medien-Eintraege"
            )

    def _delete_selected_media(self, pool: str):
        """Loescht alle angehakten Medien asynchron (Fix F-045)."""
        from PySide6.QtWidgets import QMessageBox
        video_ids = []
        audio_ids = []
        
        if pool in ("video", "both"):
            v_model = self.window.video_pool_table.model()
            if v_model:
                video_ids = v_model.get_checked_ids()
                
        if pool in ("audio", "both"):
            a_model = self.window.audio_pool_table.model()
            if a_model:
                audio_ids = a_model.get_checked_ids()

        total = len(video_ids) + len(audio_ids)
        if total == 0:
            QMessageBox.information(self.window, "Nichts ausgewaehlt", "Bitte setze zuerst die Checkboxen im Media Pool.")
            return

        reply = QMessageBox.question(
            self.window, "Medien loeschen",
            f"{total} Medium/Medien aus der Datenbank entfernen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            from PySide6.QtCore import QObject, Signal
            class PartialDeleteWorker(QObject):
                finished = Signal(int)
                def run(self):
                    count = delete_selected_media(video_ids, audio_ids)
                    self.finished.emit(count)

            worker = PartialDeleteWorker()
            def _on_done(count):
                self.window.media_table_controller._refresh_media_table()
                self.window._mark_dirty()
                self.window.console_text.append(f"[System] {count} Medien-Eintraege geloescht.")
                self.window.status_bar.showMessage(f"{count} Medien geloescht")

            from services.task_manager import GlobalTaskManager
            GlobalTaskManager.instance().start_task(
                name="Medien loeschen",
                worker=worker,
                description=f"Entfernt {total} ausgewaehlte Medien"
            )
