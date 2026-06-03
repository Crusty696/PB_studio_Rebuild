"""MediaTableController — Refactored to Model/View (Fix F-006)."""

import logging
from PySide6.QtCore import Qt, QTimer, QObject, Signal
from ui.base_component import PBComponent

logger = logging.getLogger(__name__)

class MediaTableController(PBComponent):
    """Controller for Media Tables and Director Combos in PBWindow.
    
    Uses MediaTableModel for efficient rendering.
    """

    def _refresh_director_combos(
        self,
        project_id: int | None = None,
        *,
        allow_active_fallback: bool = True,
    ):
        # P8-FREEZE-FIX: Lightweight-Query ohne energy_curve/analysis_percent.
        # Vorher blockierte get_all_media() den Main-Thread beim Boot
        # mehrere Sekunden (grosse JSON-Blobs + N+1 Status-Queries).
        from services.ingest_service import get_combo_items
        from database import get_active_project_id
        if project_id is None and allow_active_fallback:
            _pid_now = get_active_project_id()
        else:
            _pid_now = project_id
        media = get_combo_items(_pid_now) if _pid_now is not None else []
        # B-285 diagnostic, kept at debug level to avoid normal log noise.
        _audio_n = sum(1 for m in media if m.get("type") == "Audio")
        _video_n = sum(1 for m in media if m.get("type") == "Video")
        logger.debug(
            "[B-285] _refresh_director_combos: active_pid=%s -> %d audio + %d video items",
            _pid_now, _audio_n, _video_n,
        )
        audio_blocked = self.window.audio_combo.blockSignals(True)
        video_blocked = self.window.video_combo.blockSignals(True)
        try:
            self.window.audio_combo.clear()
            self.window.video_combo.clear()
            self.window.audio_combo.addItem("-- kein Audio --", None)
            self.window.video_combo.addItem("-- kein Video --", None)
            first_audio_index = None
            preferred_audio_index = None
            for item in media:
                label = f"[{item['id']}] {item['title']}"
                if item["type"] == "Audio":
                    bpm = item.get("bpm")
                    if bpm:
                        label += f" ({bpm} BPM)"
                    combo_index = self.window.audio_combo.count()
                    self.window.audio_combo.addItem(label, item["id"])
                    if first_audio_index is None:
                        first_audio_index = combo_index
                    if preferred_audio_index is None and self._audio_item_has_analysis(item):
                        preferred_audio_index = combo_index
                elif item["type"] == "Video":
                    self.window.video_combo.addItem(label, item["id"])
            if preferred_audio_index is not None:
                self.window.audio_combo.setCurrentIndex(preferred_audio_index)
            elif first_audio_index is not None:
                self.window.audio_combo.setCurrentIndex(first_audio_index)
            if self.window.video_combo.count() > 1:
                self.window.video_combo.setCurrentIndex(1)
        finally:
            self.window.audio_combo.blockSignals(audio_blocked)
            self.window.video_combo.blockSignals(video_blocked)
        self._sync_schnitt_audio_selection()

    def _toggle_all_checkboxes(self, table_view):
        """Alle Checkboxen im Model toggeln."""
        model = table_view.model()
        if hasattr(model, "toggle_all"):
            model.toggle_all()

    def _refresh_media_table(self, _also_combos: bool = True):
        """Aktualisiert die Medien-Listen asynchron (Fix F-028).

        B-469 Gap-2 (single-flight): startet keinen zweiten "Medien-DB laden"-
        Worker waehrend bereits einer laeuft. Concurrent calls werden zu EINEM
        In-Flight-Task gebuendelt; treffen waehrend des Laufs weitere Aufrufe
        ein, wird genau EIN nachgelagerter Reload nach Abschluss ausgefuehrt
        (dirty-Flag). Reduziert das Task-Pile-up aus B-469.
        """
        if getattr(self, "_reload_inflight", False):
            self._reload_dirty = True
            # Merke ob irgendein wartender Aufruf die Combos mit aktualisieren will.
            self._reload_dirty_combos = getattr(self, "_reload_dirty_combos", False) or _also_combos
            return
        self._reload_inflight = True

        class DBFetchWorker(QObject):
            finished = Signal(list, list)
            error = Signal(str)
            def run(self):
                try:
                    from services.ingest_service import get_all_audio, get_all_video
                    v = get_all_video()
                    a = get_all_audio()
                    self.finished.emit(v, a)
                except Exception as e:
                    logger.error("Fehler beim asynchronen DB-Fetch: %s", e)
                    self.error.emit(str(e))

        worker = DBFetchWorker()
        worker.finished.connect(
            lambda v, a, _c=_also_combos: self._on_media_reload_done(v, a, _c),
            Qt.ConnectionType.QueuedConnection,
        )
        # B-469: Error-Pfad muss den In-Flight-Status loesen, sonst bleibt der
        # Reload fuer immer blockiert (vorher war error unverbunden).
        worker.error.connect(
            lambda _msg: self._on_media_reload_failed(),
            Qt.ConnectionType.QueuedConnection,
        )

        # Starte via TaskEngine (Hintergrund)
        from services.task_manager import GlobalTaskManager
        GlobalTaskManager.instance().start_task(
            name="Medien-DB laden",
            worker=worker,
            description="Lade Clip-Metadaten aus SQLite"
        )

    def _on_media_reload_done(self, videos: list, audios: list, also_combos: bool):
        """Finished-Slot: wendet Daten an und loest dann den In-Flight-Status."""
        try:
            self._apply_refreshed_data(videos, audios, also_combos)
        finally:
            self._reload_finished_cleanup()

    def _on_media_reload_failed(self):
        """Error-Slot: kein Daten-Apply, aber In-Flight-Status loesen."""
        self._reload_finished_cleanup()

    def _reload_finished_cleanup(self):
        """Markiert den Reload als beendet; faehrt genau einen nachgelagerten
        Reload nach, falls waehrend des Laufs weitere Aufrufe kamen (dirty)."""
        self._reload_inflight = False
        if getattr(self, "_reload_dirty", False):
            self._reload_dirty = False
            combos = getattr(self, "_reload_dirty_combos", False)
            self._reload_dirty_combos = False
            self._refresh_media_table(combos)

    def _apply_refreshed_data(self, videos: list, audios: list, also_combos: bool):
        """Wendet die im Hintergrund geladenen Daten auf die UI an."""
        # Models aktualisieren
        if hasattr(self.window, "video_pool_model"):
            self.window.video_pool_model.set_items(videos)
        
        if hasattr(self.window, "audio_pool_model"):
            self.window.audio_pool_model.set_items(audios)

        # Grid views (AUD-72)
        if hasattr(self.window, "video_grid"):
            self.window.video_grid.set_items(videos)
        if hasattr(self.window, "audio_grid"):
            self.window.audio_grid.set_items(audios)

        # Director-Combos
        if also_combos:
            # B-285 diagnostic, kept at debug level to avoid normal log noise.
            from database import get_active_project_id
            _pid_now = get_active_project_id()
            logger.debug(
                "[B-285] _apply_refreshed_data combos: active_pid=%s -> %d audio + %d video (async overwrite)",
                _pid_now, len(audios), len(videos),
            )
            audio_blocked = self.window.audio_combo.blockSignals(True)
            video_blocked = self.window.video_combo.blockSignals(True)
            try:
                self.window.audio_combo.clear()
                self.window.video_combo.clear()
                self.window.audio_combo.addItem("-- kein Audio --", None)
                self.window.video_combo.addItem("-- kein Video --", None)

                first_audio_index = None
                preferred_audio_index = None
                for item in audios:
                    bpm = item.get("bpm")
                    label = f"[{item['id']}] {item['title']}" + (f" ({bpm} BPM)" if bpm else "")
                    combo_index = self.window.audio_combo.count()
                    self.window.audio_combo.addItem(label, item["id"])
                    if first_audio_index is None:
                        first_audio_index = combo_index
                    if preferred_audio_index is None and self._audio_item_has_analysis(item):
                        preferred_audio_index = combo_index

                for item in videos:
                    label = f"[{item['id']}] {item['title']}"
                    self.window.video_combo.addItem(label, item["id"])
                if preferred_audio_index is not None:
                    self.window.audio_combo.setCurrentIndex(preferred_audio_index)
                elif first_audio_index is not None:
                    self.window.audio_combo.setCurrentIndex(first_audio_index)
                if self.window.video_combo.count() > 1:
                    self.window.video_combo.setCurrentIndex(1)
            finally:
                self.window.audio_combo.blockSignals(audio_blocked)
                self.window.video_combo.blockSignals(video_blocked)
            self._sync_schnitt_audio_selection()

    def _sync_schnitt_audio_selection(self) -> None:
        """Propagate blocked combo selection to SCHNITT audio binders."""
        audio_id = self.window.audio_combo.currentData()
        coordinator = getattr(self.window, "_schnitt_coordinator", None)
        if coordinator is not None:
            coordinator.refresh_audio(audio_id)
        stems = getattr(self.window, "stems", None)
        if stems is not None and audio_id is not None:
            stems._update_stem_workspace(audio_id)

    @staticmethod
    def _audio_item_has_analysis(item: dict) -> bool:
        return bool(item.get("bpm") or item.get("key") or item.get("lufs"))

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
