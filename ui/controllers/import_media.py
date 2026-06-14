"""ImportMediaController — Refactored from ImportMediaMixin."""

import logging
import os
from pathlib import Path
from PySide6.QtCore import Qt, QObject, QSettings, Signal
from PySide6.QtWidgets import QFileDialog
from services.ingest_service import (
    delete_all_media, delete_selected_media, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS,
)
from workers import FolderImportWorker, BrainV3HashingWorker
from ui.base_component import PBComponent

logger = logging.getLogger(__name__)


def _last_import_dir(kind: str) -> str:
    """Liefert letztes Import-Verzeichnis pro Medien-Typ.

    Default-Dir setzen reduziert FileDialog-Oeffnungszeit drastisch — Native
    QFileDialog scannt sonst alle Drives + Shell-Extensions (OneDrive, Cloud)
    beim ersten Oeffnen. 35-Sek-Freezes wurden beobachtet (B-Crash 2026-05-11).
    """
    s = QSettings("PB Studio", "Rebuild")
    val = s.value(f"import/last_dir_{kind}", "", type=str)
    if val and os.path.isdir(val):
        return val
    fallback = {
        "video": str(Path.home() / "Videos"),
        "audio": str(Path.home() / "Music"),
        "folder": str(Path.home()),
    }.get(kind, str(Path.home()))
    return fallback if os.path.isdir(fallback) else str(Path.home())


def _save_import_dir(kind: str, file_path: str) -> None:
    if not file_path:
        return
    d = os.path.dirname(file_path)
    if d and os.path.isdir(d):
        QSettings("PB Studio", "Rebuild").setValue(f"import/last_dir_{kind}", d)


def _fast_dialog_options():
    """Use Qt dialog to avoid Windows shell-extension stalls on first open."""
    return QFileDialog.Option.DontUseNativeDialog


# B-248: Aus dem Inline-Pattern extrahiert — Module-Level-Klasse hat
# klareren Lifecycle, kein Closure-Capture-Risiko, einfacher zu debuggen.
class _PartialDeleteWorker(QObject):
    """Worker fuer asynchrones Loeschen ausgewaehlter Medien.

    Wird von ``ImportMediaController._delete_selected_media`` instanziiert
    und an den ``GlobalTaskManager`` uebergeben. Strong-Ref via
    ``task.worker`` im TaskManager-Dict (siehe ``task_manager.py:362``).
    """
    finished = Signal(int)
    error = Signal(str)

    def __init__(self, video_ids: list[int], audio_ids: list[int], parent=None):
        super().__init__(parent)
        self._video_ids = list(video_ids)
        self._audio_ids = list(audio_ids)

    def run(self):
        try:
            count = delete_selected_media(self._video_ids, self._audio_ids)
            self.finished.emit(count)
        except Exception as e:  # broad catch intentional — Error via Signal ans UI propagiert
            logger.exception("PartialDeleteWorker.run failed")
            self.error.emit(str(e))


class ImportMediaController(PBComponent):
    """Media import methods for PBWindow."""

    def _open_trash(self):
        """Oeffnet den Papierkorb-Dialog (B-462 Stage 2 / Task 12).

        Zeigt soft-geloeschte Medien des aktiven Projekts; Restore und der
        endgueltige Purge laufen synchron im Dialog. Nach dem Schliessen wird
        die Media-Tabelle aktualisiert (ein Restore bringt Rows zurueck).
        """
        from ui.dialogs.trash_dialog import TrashDialog
        logger.info("ImportMedia._open_trash: Klick angekommen, oeffne Papierkorb")
        dialog = TrashDialog(project_id=None, parent=self.window)
        dialog.exec()
        try:
            self.window.media_table_controller._refresh_media_table_debounced()
        except (AttributeError, RuntimeError):
            logger.debug("ImportMedia._open_trash: Media-Refresh uebersprungen")

    def _import_video(self):
        logger.info("ImportMedia._import_video: Klick angekommen, oeffne FileDialog")
        ext_filter = "Video-Dateien (" + " ".join(f"*{e}" for e in VIDEO_EXTENSIONS) + ")"
        self._open_media_file_dialog("video", "Videos importieren", ext_filter, "video")

    def _import_audio(self):
        logger.info("ImportMedia._import_audio: Klick angekommen, oeffne FileDialog")
        ext_filter = "Audio-Dateien (" + " ".join(f"*{e}" for e in AUDIO_EXTENSIONS) + ")"
        self._open_media_file_dialog("audio", "Audio importieren", ext_filter, "audio")

    def _open_media_file_dialog(self, kind: str, title: str, ext_filter: str, media_type: str) -> None:
        dialog = QFileDialog(self.window, title, _last_import_dir(kind), ext_filter)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dialog.setOption(_fast_dialog_options(), True)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._active_import_dialog = dialog

        def _finish(result: int) -> None:
            paths = dialog.selectedFiles() if result == QFileDialog.DialogCode.Accepted else []
            logger.info(
                "ImportMedia._import_%s: FileDialog geschlossen, %d Dateien gewaehlt",
                media_type,
                len(paths),
            )
            if paths:
                _save_import_dir(kind, paths[0])
            self._process_imports(paths, media_type)
            self._active_import_dialog = None

        dialog.finished.connect(_finish)
        dialog.open()

    def _process_imports(self, paths: list[str], media_type: str):
        """Imports laufen im Hintergrund-Thread."""
        if not paths:
            return
        paths_audio = paths if media_type == "audio" else []
        paths_video = paths if media_type == "video" else []

        self.window.console_text.append(f"[Import] {len(paths)} {media_type.capitalize()}-Datei(en) werden importiert ...")
        self.window.status_bar.showMessage(f"Importiere {len(paths)} Datei(en) ...")

        worker = FolderImportWorker(paths_audio, paths_video)
        worker.file_imported.connect(self.window.console_text.append, Qt.ConnectionType.QueuedConnection)
        worker.progress.connect(
            lambda pct, msg: self.window.status_bar.showMessage(f"[Import] {pct}% — {msg}"),
            Qt.ConnectionType.QueuedConnection,
        )

        def _on_finish(added: int, new_video_clips: list):
            if added:
                self.window.media_table_controller._refresh_media_table_debounced()
                for clip_id, video_path, title in new_video_clips:
                    self.window.video_analysis._start_proxy_creation(clip_id, video_path, title)
                self.window._mark_dirty()
            reuse_message = self._notify_cross_project_reuse(paths, media_type, worker.project_id)
            if reuse_message is None:
                self.window.status_bar.showMessage(f"{added} Datei(en) importiert | System bereit")
            # Phase-1 App-Sync: Hash-Hook nach erfolgreichem Import.
            # Idempotent — Re-Import liefert is_new=False / Cache-Hit-Log.
            self._spawn_brain_v3_hash_worker(paths_audio, paths_video)

        def _on_error(msg: str):
            self.window.console_text.append(f"[Fehler] Import abgebrochen: {msg}")
            self.window.status_bar.showMessage("Import fehlgeschlagen | System bereit")

        self.window.worker_dispatcher._start_worker_thread(worker, on_finish=_on_finish, on_error=_on_error)

    def _spawn_brain_v3_hash_worker(self, paths_audio: list[str], paths_video: list[str]):
        """Phase-1+2-App-Sync (06_PHASES.md Z.82-191): Hash registrieren +
        Embedding-Job-Push.

        Hash-Worker laeuft in eigenem QThread. Pro neu registriertem Hash
        (is_new=True) wird via Signal `hash_registered` der EmbeddingScheduler
        getriggert (Cache-Hit-Skip findet im Scheduler statt). Fehler im
        Hash- oder Embedding-Pfad killen NIE den Import.
        """
        if not paths_audio and not paths_video:
            return
        hash_worker = BrainV3HashingWorker(paths_audio, paths_video)
        hash_worker.file_imported = hash_worker.file_hashed  # alias fuer console
        hash_worker.file_hashed.connect(
            self.window.console_text.append,
            Qt.ConnectionType.QueuedConnection,
        )
        hash_worker.hash_registered.connect(
            self._on_hash_registered_for_embedding,
            Qt.ConnectionType.QueuedConnection,
        )

        def _hash_done(n_new: int, n_known: int):
            self.window.console_text.append(
                f"[Brain V3] Hash-Lauf fertig: {n_new} neu, {n_known} bekannt"
            )

        def _hash_err(msg: str):
            self.window.console_text.append(f"[Brain V3] Hash-Worker-Fehler: {msg}")

        self.window.worker_dispatcher._start_worker_thread(
            hash_worker, on_finish=_hash_done, on_error=_hash_err,
        )

    def _on_hash_registered_for_embedding(
        self, media_hash: str, source_path: str, media_type: str,
    ) -> None:
        """Phase-2-App-Sync: pusht Embedding-Job an den EmbeddingScheduler.

        Laeuft im UI-Thread (QueuedConnection). Scheduler ist im PBWindow
        gestartet (siehe main.py PBWindow.__init__). Bei nicht-laufendem
        Scheduler (z.B. erst-Import vor Boot-Hook) wird leise geskippt
        und in Konsole gemeldet.
        """
        scheduler = getattr(self.window, "_brain_v3_scheduler", None)
        if scheduler is None or not scheduler.is_running():
            self.window.console_text.append(
                f"[Brain V3] Scheduler nicht aktiv — Embedding skip ({media_hash[:8]}...)"
            )
            return
        try:
            job_id = scheduler.submit_path(media_hash, source_path, media_type)
        except Exception as exc:
            self.window.console_text.append(
                f"[Brain V3] Embedding-Submit fehlgeschlagen ({media_hash[:8]}...): {exc}"
            )
            return
        if job_id is None:
            self.window.console_text.append(
                f"[Brain V3] Embedding-Cache-Hit ({media_hash[:8]}...)"
            )
        else:
            self.window.console_text.append(
                f"[Brain V3] Embedding-Job submitted ({media_hash[:8]}..., id={job_id})"
            )

    def _import_folder(self):
        """Importiert alle unterstuetzten Medien aus einem Ordner.

        B-058: Der ``os.walk``-Scan laeuft jetzt im FolderImportWorker-
        Background-Thread (``walk_root``-Parameter). Vorher fror der
        Main-Thread bei grossen Ordnerbaeumen (NAS / 1000+ Files)
        mehrere Sekunden ein.
        """
        logger.info("ImportMedia._import_folder: Klick angekommen, oeffne Folder-Dialog")
        dialog = QFileDialog(self.window, "Ordner importieren", _last_import_dir("folder"))
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(_fast_dialog_options(), True)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._active_import_dialog = dialog

        def _finish(result: int) -> None:
            folders = dialog.selectedFiles() if result == QFileDialog.DialogCode.Accepted else []
            folder = folders[0] if folders else ""
            if not folder:
                logger.info("ImportMedia._import_folder: User hat Folder-Dialog abgebrochen")
                self._active_import_dialog = None
                return
            QSettings("PB Studio", "Rebuild").setValue("import/last_dir_folder", folder)
            logger.info("ImportMedia._import_folder: Ordner gewaehlt: %s", folder)
            self.window.console_text.append(f"[Ordner] Scanne {folder} ...")
            self.window.status_bar.showMessage(f"Scanne Ordner {folder} ...")

            # B-058: walk_root setzen — Worker macht den os.walk-Scan im
            # eigenen Thread und ergaenzt paths_audio/paths_video selbst.
            worker = FolderImportWorker([], [], walk_root=folder)
            worker.file_imported.connect(self.window.console_text.append, Qt.ConnectionType.QueuedConnection)
            worker.progress.connect(
                lambda pct, msg: self.window.status_bar.showMessage(f"[Import] {pct}% — {msg}"),
                Qt.ConnectionType.QueuedConnection,
            )

            def _on_finish(added: int, new_video_clips: list):
                if added:
                    self.window.media_table_controller._refresh_media_table_debounced()
                    for clip_id, video_path, title in new_video_clips:
                        self.window.video_analysis._start_proxy_creation(clip_id, video_path, title)
                    self.window._mark_dirty()
                reuse_message = self._notify_cross_project_reuse(
                    list(worker.paths_audio), "audio", worker.project_id
                )
                if reuse_message is None:
                    reuse_message = self._notify_cross_project_reuse(
                        list(worker.paths_video), "video", worker.project_id
                    )
                if reuse_message is None:
                    self.window.status_bar.showMessage(f"{added} Datei(en) aus Ordner importiert | System bereit")
                # Phase-1 App-Sync: paths_audio/paths_video wurden vom Worker
                # waehrend des Walks befuellt — jetzt verfuegbar.
                self._spawn_brain_v3_hash_worker(
                    list(worker.paths_audio), list(worker.paths_video),
                )

            def _on_error(msg: str):
                self.window.console_text.append(f"[Fehler] Ordner-Import abgebrochen: {msg}")
                self.window.status_bar.showMessage("Import fehlgeschlagen | System bereit")

            self.window.worker_dispatcher._start_worker_thread(worker, on_finish=_on_finish, on_error=_on_error)
            self._active_import_dialog = None

        dialog.finished.connect(_finish)
        dialog.open()

    def _notify_cross_project_reuse(
        self,
        paths: list[str],
        media_type: str,
        project_id: int | None,
    ) -> str | None:
        if not paths or project_id is None:
            return None
        settings = QSettings("PB Studio", "Rebuild")
        mute_key = f"reuse_notifications/muted_project_{int(project_id)}"
        if settings.value(mute_key, False, type=bool):
            return None
        try:
            from database import nullpool_session
            from database.models import AnalysisStatus, AudioTrack, VideoClip

            media_model = AudioTrack if media_type == "audio" else VideoClip
            resolved_paths = {str(Path(path).resolve()) for path in paths}
            messages: list[str] = []
            with nullpool_session() as session:
                media_rows = (
                    session.query(media_model)
                    .filter(
                        media_model.project_id == int(project_id),
                        media_model.file_path.in_(resolved_paths),
                    )
                    .all()
                )
                for row in media_rows:
                    statuses = (
                        session.query(AnalysisStatus)
                        .filter_by(media_type=media_type, media_id=row.id, status="done")
                        .all()
                    )
                    for status in statuses:
                        summary = status.value_summary or {}
                        project_name = summary.get("reuse_source_project") if isinstance(summary, dict) else None
                        if not project_name:
                            continue
                        messages.append(
                            f"Datei wurde bereits in Projekt {project_name} analysiert. "
                            "Ergebnisse werden mitverwendet."
                        )
                        break
        except Exception as exc:
            logger.warning("OTK-021 reuse notification failed: %s", exc)
            return None

        if not messages:
            return None
        message = messages[0]
        self.window.console_text.append(f"[Reuse] {message}")
        if len(messages) > 1:
            self.window.console_text.append(f"[Reuse] {len(messages)} Dateien mit wiederverwendeten Ergebnissen.")
        self.window.status_bar.showMessage(message, 10_000)
        self._show_cross_project_reuse_notice(message, mute_key)
        return message

    def _show_cross_project_reuse_notice(self, message: str, mute_key: str) -> None:
        try:
            from PySide6.QtWidgets import QCheckBox, QMessageBox

            box = QMessageBox(self.window)
            box.setWindowTitle("Analyse-Ergebnisse wiederverwendet")
            box.setText(message)
            box.setIcon(QMessageBox.Icon.Information)
            box.setStandardButtons(QMessageBox.StandardButton.Ok)
            box.setWindowModality(Qt.WindowModality.NonModal)
            checkbox = QCheckBox("Nicht mehr fragen")
            box.setCheckBox(checkbox)

            def _store_mute(checked: bool) -> None:
                QSettings("PB Studio", "Rebuild").setValue(mute_key, checked)

            checkbox.toggled.connect(_store_mute)
            box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
            self._active_reuse_notice = box
            box.finished.connect(lambda _result: setattr(self, "_active_reuse_notice", None))
            box.show()
        except Exception as exc:
            logger.warning("OTK-021 reuse notice failed: %s", exc)

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
            worker.finished.connect(_on_done, Qt.ConnectionType.QueuedConnection)

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
        """Loescht alle angehakten Medien asynchron (Fix F-045).

        B-248: Re-Entrancy-Guard + Button-Disable verhindern den nativen
        Access-Violation-Crash bei Doppelklick. on_finish wird jetzt
        explizit verbunden — vorher wurde _on_done nie gerufen
        (MediaTable bleibt stale + Re-Lock-Pfad fehlte).
        """
        logger.info(
            "ImportMedia._delete_selected_media: Klick angekommen, pool=%s, "
            "delete_in_progress=%s",
            pool,
            getattr(self, "_delete_in_progress", False),
        )
        from PySide6.QtWidgets import QMessageBox

        # B-248: Re-Entrancy-Guard — zweiten Klick waehrend laufendem Loeschen
        # ignorieren, sonst spawnen 2 parallele Worker und race im SQLite/
        # VectorDB/TableModel-Cleanup -> native access violation.
        if getattr(self, "_delete_in_progress", False):
            QMessageBox.information(
                self.window, "Loeschvorgang laeuft",
                "Es wird gerade geloescht. Bitte warte bis der aktuelle Vorgang fertig ist.",
            )
            return

        # SOFORT sperren, bevor _irgendeine_ QMessageBox das Event-Loop oeffnet!
        self._delete_in_progress = True

        video_ids: list[int] = []
        audio_ids: list[int] = []

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
            self._delete_in_progress = False
            QMessageBox.information(self.window, "Nichts ausgewaehlt", "Bitte setze zuerst die Checkboxen im Media Pool.")
            return

        reply = QMessageBox.question(
            self.window, "Medien loeschen",
            f"{total} Medium/Medien aus der Datenbank entfernen?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            self._delete_in_progress = False
            return

        # B-248: Buttons deaktivieren
        disabled_buttons: list = []
        for btn_attr in ("btn_delete_selected_video", "btn_delete_selected_audio"):
            btn = getattr(self.window, btn_attr, None)
            if btn is not None:
                try:
                    btn.setEnabled(False)
                    disabled_buttons.append(btn)
                except RuntimeError:
                    pass  # Widget bereits geloescht

        def _release_lock():
            self._delete_in_progress = False
            for btn in disabled_buttons:
                try:
                    btn.setEnabled(True)
                except RuntimeError:
                    pass  # Widget inzwischen geloescht

        worker = _PartialDeleteWorker(video_ids, audio_ids)

        def _on_done(count: int):
            try:
                self.window.media_table_controller._refresh_media_table_debounced()
                self.window._mark_dirty()
                self.window.console_text.append(f"[System] {count} Medien-Eintraege geloescht.")
                self.window.status_bar.showMessage(f"{count} Medien geloescht")
            finally:
                _release_lock()

        # B-060: on_error-Handler analog zu _clear_all_media.
        def _on_error(err_msg: str) -> None:
            try:
                if self.window:
                    self.window.console_text.append(f"[Fehler] Medien loeschen: {err_msg}")
                    self.window.status_bar.showMessage(f"Medien-Loeschen fehlgeschlagen: {err_msg}", 10_000)
                    QMessageBox.critical(self.window, "Medien loeschen fehlgeschlagen", err_msg)
            finally:
                _release_lock()

        from services.task_manager import GlobalTaskManager
        GlobalTaskManager.instance().start_task(
            name="Medien loeschen",
            worker=worker,
            on_finish=_on_done,           # B-248: war vorher nicht verbunden — _on_done wurde nie gerufen
            on_error=_on_error,
            description=f"Entfernt {total} ausgewaehlte Medien"
        )
