"""MediaTableController — Refactored to Model/View (Fix F-006)."""

import logging
from PySide6.QtCore import Qt, QTimer, QObject, Signal
from services.ingest_service import get_all_audio, get_all_video
from ui.base_component import PBComponent

logger = logging.getLogger(__name__)

class MediaTableController(PBComponent):
    """Controller for Media Tables and Director Combos in PBWindow.
    
    Uses MediaTableModel for efficient rendering.
    """

    def _refresh_director_combos(self):
        # P8-FREEZE-FIX: Lightweight-Query ohne energy_curve/analysis_percent.
        # Vorher blockierte get_all_media() den Main-Thread beim Boot
        # mehrere Sekunden (grosse JSON-Blobs + N+1 Status-Queries).
        from services.ingest_service import get_combo_items
        media = get_combo_items()
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

    def _toggle_all_checkboxes(self, table_view):
        """Alle Checkboxen im Model toggeln."""
        model = table_view.model()
        if hasattr(model, "toggle_all"):
            model.toggle_all()

    def _refresh_media_table(self, _also_combos: bool = True):
        """Aktualisiert die Medien-Listen asynchron (Fix F-028)."""
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
            lambda v, a: self._apply_refreshed_data(v, a, _also_combos),
            Qt.ConnectionType.QueuedConnection,
        )
        
        # Starte via TaskEngine (Hintergrund)
        from services.task_manager import GlobalTaskManager
        GlobalTaskManager.instance().start_task(
            name="Medien-DB laden",
            worker=worker,
            description="Lade Clip-Metadaten aus SQLite"
        )

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
            self.window.audio_combo.clear()
            self.window.video_combo.clear()
            self.window.audio_combo.addItem("-- kein Audio --", None)
            self.window.video_combo.addItem("-- kein Video --", None)
            
            for item in audios:
                bpm = item.get("bpm")
                label = f"[{item['id']}] {item['title']}" + (f" ({bpm} BPM)" if bpm else "")
                self.window.audio_combo.addItem(label, item["id"])
            
            for item in videos:
                label = f"[{item['id']}] {item['title']}"
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
