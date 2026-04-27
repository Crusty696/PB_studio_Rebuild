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
                self.window.media_table_controller._refresh_media_table_debounced()
                for clip_id, video_path, title in new_video_clips:
                    self.window.video_analysis._start_proxy_creation(clip_id, video_path, title)
                self.window._mark_dirty()
            self.window.status_bar.showMessage(f"{added} Datei(en) importiert | System bereit")

        def _on_error(msg: str):
            self.window.console_text.append(f"[Fehler] Import abgebrochen: {msg}")
            self.window.status_bar.showMessage("Import fehlgeschlagen | System bereit")

        self.window.worker_dispatcher._start_worker_thread(worker, on_finish=_on_finish, on_error=_on_error)

    def _import_folder(self):
        """Importiert alle unterstuetzten Medien aus einem Ordner.

        B-058: Der ``os.walk``-Scan laeuft jetzt im FolderImportWorker-
        Background-Thread (``walk_root``-Parameter). Vorher fror der
        Main-Thread bei grossen Ordnerbaeumen (NAS / 1000+ Files)
        mehrere Sekunden ein.
        """
        folder = QFileDialog.getExistingDirectory(self.window, "Ordner importieren")
        if not folder:
            return
        self.window.console_text.append(f"[Ordner] Scanne {folder} ...")
        self.window.status_bar.showMessage(f"Scanne Ordner {folder} ...")

        # B-058: walk_root setzen — Worker macht den os.walk-Scan im
        # eigenen Thread und ergaenzt paths_audio/paths_video selbst.
        worker = FolderImportWorker([], [], walk_root=folder)
        worker.file_imported.connect(self.window.console_text.append)
        worker.progress.connect(
            lambda pct, msg: self.window.status_bar.showMessage(f"[Import] {pct}% — {msg}")
        )

        def _on_finish(added: int, new_video_clips: list):
            if added:
                self.window.media_table_controller._refresh_media_table_debounced()
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
                error = Signal(str)
                def run(self):
                    try:
                        count = delete_all_media()
                        self.finished.emit(count)
                    except Exception as e:
                        self.error.emit(str(e))

            worker = DeleteWorker()
            def _on_done(count):
                self.window.media_table_controller._refresh_media_table_debounced()
                self.window._mark_dirty()
                self.window.console_text.append(f"[System] {count} Medien-Eintraege geloescht.")
                self.window.status_bar.showMessage(f"Sammlung bereinigt ({count} Eintraege)")

            # H-36 FIX: Connect the on_finish callback to worker.finished signal
            worker.finished.connect(_on_done)

            # B-060: on_error-Handler — vorher landete Fehler nur im Task-Dock
            # ohne sichtbare User-Meldung.
            def _on_error(err_msg: str) -> None:
                if not self.window:
                    return
                from PySide6.QtWidgets import QMessageBox
                self.window.console_text.append(f"[Fehler] Sammlung bereinigen: {err_msg}")
                self.window.status_bar.showMessage(f"Sammlung-Bereinigen fehlgeschlagen: {err_msg}", 10_000)
                QMessageBox.critical(self.window, "Sammlung bereinigen fehlgeschlagen", err_msg)

            from services.task_manager import GlobalTaskManager
            GlobalTaskManager.instance().start_task(
                name="Datenbank bereinigen",
                worker=worker,
                on_error=_on_error,
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
                error = Signal(str)
                def run(self):
                    try:
                        count = delete_selected_media(video_ids, audio_ids)
                        self.finished.emit(count)
                    except Exception as e:
                        self.error.emit(str(e))

            worker = PartialDeleteWorker()
            def _on_done(count):
                self.window.media_table_controller._refresh_media_table_debounced()
                self.window._mark_dirty()
                self.window.console_text.append(f"[System] {count} Medien-Eintraege geloescht.")
                self.window.status_bar.showMessage(f"{count} Medien geloescht")

            # B-060: on_error-Handler analog zu _clear_all_media.
            def _on_error(err_msg: str) -> None:
                if not self.window:
                    return
                from PySide6.QtWidgets import QMessageBox
                self.window.console_text.append(f"[Fehler] Medien loeschen: {err_msg}")
                self.window.status_bar.showMessage(f"Medien-Loeschen fehlgeschlagen: {err_msg}", 10_000)
                QMessageBox.critical(self.window, "Medien loeschen fehlgeschlagen", err_msg)

            from services.task_manager import GlobalTaskManager
            GlobalTaskManager.instance().start_task(
                name="Medien loeschen",
                worker=worker,
                on_error=_on_error,
                description=f"Entfernt {total} ausgewaehlte Medien"
            )
