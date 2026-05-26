"""VideoAnalysisController — Refactored to Model/View (Fix F-006)."""

import logging
from PySide6.QtCore import Qt
from services.task_manager import TaskManagerProxy
from workers import (
    VideoBatchAnalysisWorker, VideoAnalysisPipelineWorker,
    ProxyCreationWorker,
)
from ui.base_component import PBComponent

logger = logging.getLogger(__name__)

# L-38 Fix: Lazy initialization instead of module-level instantiation
_task_manager = None

def _get_task_manager():
    """Get or create TaskManagerProxy singleton (lazy init)."""
    global _task_manager
    if _task_manager is None:
        _task_manager = TaskManagerProxy()
    return _task_manager

class VideoAnalysisController(PBComponent):
    """Video analysis methods for PBWindow.
    
    Fully refactored to use MediaTableModel (Fix F-006).
    """

    def _on_video_pool_selected(self, row, col, prev_row, prev_col):
        """Selection sync logic (Fix F-006)."""
        # Legacy media_table sync removed. 
        # Future: update detail cards here.
        pass

    def _analyze_selected_video(self):
        """Startet Metadaten-Analyse + Proxy für ausgewählte Videos."""
        view = self.window.video_pool_table
        model = view.model()
        if not model: return

        # 1. Batch aus angehakten IDs
        checked_ids = model.get_checked_ids()
        batch = []
        
        if checked_ids:
            for cid in checked_ids:
                batch.append((cid, f"Clip {cid}"))
        else:
            # 2. Falls nichts angehakt, aktuelle Selektion
            indexes = view.selectionModel().selectedRows()
            if indexes:
                row = indexes[0].row()
                cid = model.index(row, 1).data()
                title = model.index(row, 2).data()
                if cid:
                    batch.append((int(cid), str(title)))

        if not batch:
            self.window.console_text.append("[Warnung] Keine Zeile im Video Pool ausgewaehlt oder angehakt.")
            return

        self.window.btn_analyze_video.setEnabled(False)
        self.window.progress_bar.setVisible(True)
        self.window.progress_bar.setRange(0, len(batch))
        self.window.progress_bar.setValue(0)
        self.window.btn_analyze_video.setText(f"Analyse 0/{len(batch)}...")
        self.window.console_text.append(
            f"[Video] Batch-Analyse gestartet: {len(batch)} Videos (sequentiell)"
        )

        task = _get_task_manager().create_task(
            f"Video-Batch ({len(batch)})", "Metadaten + Proxy"
        )

        worker = VideoBatchAnalysisWorker(batch)
        worker.task_id = task.task_id
        worker.item_done.connect(self._on_video_batch_item_done, Qt.ConnectionType.QueuedConnection)
        worker.item_error.connect(self._on_video_batch_item_error, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(
            lambda done, errors: self._on_video_batch_finished(done, errors, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda err: (
                self.window.console_text.append(f"[Video-Batch] Kritischer Fehler: {err}"),
                self._on_video_batch_finished(0, 1, task.task_id),
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        self._video_batch_total = len(batch)
        self._video_batch_done = 0
        self._video_batch_errors = 0
        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_video_batch_item_done(self, clip_id: int, info: str):
        self._video_batch_done += 1
        self.window.progress_bar.setValue(self._video_batch_done)
        self.window.btn_analyze_video.setText(
            f"Analyse {self._video_batch_done}/{self._video_batch_total}..."
        )
        self.window.status_bar.showMessage(
            f"Video-Analyse: {self._video_batch_done}/{self._video_batch_total} — {info}"
        )

    def _on_video_batch_item_error(self, clip_id: int, error_msg: str):
        self._video_batch_errors += 1
        self._video_batch_done += 1
        self.window.progress_bar.setValue(self._video_batch_done)
        self.window.btn_analyze_video.setText(
            f"Analyse {self._video_batch_done}/{self._video_batch_total}..."
        )
        self.window.console_text.append(
            f"[Fehler] Video ID {clip_id}: {error_msg}"
        )

    def _on_video_batch_finished(self, done: int, errors: int, task_id: str):
        self.window.btn_analyze_video.setEnabled(True)
        self.window.btn_analyze_video.setText("Video analysieren")
        self.window.progress_bar.setVisible(False)
        self.window.media_table_controller._refresh_media_table_debounced()
        errors_info = f" ({errors} Fehler)" if errors else ""
        self.window.console_text.append(
            f"[Video] Batch-Analyse abgeschlossen: {done}/{self._video_batch_total}{errors_info}"
        )
        self.window.status_bar.showMessage(
            f"Alle {self._video_batch_total} Video-Analysen abgeschlossen | System bereit"
        )
        if task_id:
            status = "finished" if errors == 0 else "error"
            _get_task_manager().finish_task(task_id, status, f"{done} fertig{errors_info}")

    def _start_video_pipeline(self):
        """Startet die 3-Schritt Video-Analyse-Pipeline (Fix F-006: Model/View)."""
        view = self.window.video_pool_table
        model = view.model()
        if not model: return

        # IDs sammeln (angehakt oder selektiert)
        checked_ids = model.get_checked_ids()
        batch = []
        
        if checked_ids:
            for cid in checked_ids:
                batch.append((cid, f"Clip {cid}"))
        else:
            indexes = view.selectionModel().selectedRows()
            for idx in indexes:
                cid = model.index(idx.row(), 1).data()
                title = model.index(idx.row(), 2).data()
                if cid:
                    batch.append((int(cid), str(title)))

        if not batch:
            self.window.console_text.append("[Warnung] Keine gültigen Videos in der Auswahl.")
            return

        count = len(batch)
        label = batch[0][1] if count == 1 else f"{count} Videos"
        task = _get_task_manager().create_task(
            f"Pipeline: {label}",
            f"Batch-Analyse: {count} Video(s) — Szenen + Motion + SigLIP"
        )

        self.window.btn_video_pipeline.setEnabled(False)
        self.window.btn_video_pipeline.setText(f"Pipeline laeuft ({count})...")
        self.window.progress_bar.setVisible(True)

        titles_str = ", ".join(t for _, t in batch[:3])
        if count > 3:
            titles_str += f" (+{count - 3} weitere)"
        self.window.console_text.append(
            f"[Pipeline] Starte Batch-Analyse fuer {count} Video(s): {titles_str} "
            f"(SceneDetect → Keyframes → SigLIP)..."
        )

        worker = VideoAnalysisPipelineWorker(batch=batch)
        worker.task_id = task.task_id
        worker.progress.connect(
            lambda pct, msg: self._on_pipeline_progress(pct, msg, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda cid, r: self._on_pipeline_finished(cid, r, label, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda cid, err: self._on_pipeline_error(cid, err, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )

        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_pipeline_progress(self, pct: int, msg: str, task_id: str):
        # B-288: progress_bar live binden — vorher schrieb der Slot nur in
        # die Konsole, Bar blieb auf 0%.
        self.window.progress_bar.setRange(0, 100)
        self.window.progress_bar.setValue(int(pct))
        # Format zeigt %p%% sowie kurze Stage-Beschreibung.
        self.window.progress_bar.setFormat(f"%p%% — {msg[:60]}")
        # Bug C-Throttle bleibt erhalten (Console-Spam).
        last_pct = getattr(self, '_pipeline_last_pct', -10)
        if abs(pct - last_pct) >= 10 or "wird analysiert" in msg:
            self.window._console_append(f"[Pipeline] {msg} ({pct}%)")
            self._pipeline_last_pct = pct

    def _on_pipeline_finished(self, clip_id: int, result: dict, title: str, task_id: str):
        if not result:
            self.window.btn_video_pipeline.setEnabled(True)
            self.window.btn_video_pipeline.setText("Video-Pipeline (Szenen + KI)")
            self.window.progress_bar.setVisible(False)
            if task_id:
                _get_task_manager().finish_task(task_id, "error", "Leeres Ergebnis")
            return
        scenes = result.get("scenes", 0)
        embeddings = result.get("embeddings", 0)
        videos_done = result.get("videos_processed", 1)
        self.window.console_text.append(
            f"[Pipeline] Fertig: {title} — {videos_done} Video(s), "
            f"{scenes} Szenen, {embeddings} Embeddings in VectorDB"
        )
        self.window.btn_video_pipeline.setEnabled(True)
        self.window.btn_video_pipeline.setText("Video-Pipeline (Szenen + KI)")
        self.window.progress_bar.setVisible(False)
        self.window.status_bar.showMessage(
            f"Pipeline fertig: {title} | {videos_done} Video(s), "
            f"{scenes} Szenen, {embeddings} Embeddings"
        )
        self.window.media_table_controller._refresh_media_table_debounced()
        if task_id:
            _get_task_manager().finish_task(
                task_id, "finished",
                f"{videos_done} Video(s), {scenes} Szenen, {embeddings} Embeddings"
            )

    def _on_pipeline_error(self, clip_id: int, error_msg: str, task_id: str):
        self.window.console_text.append(f"[Pipeline-Fehler] VideoClip {clip_id}: {error_msg}")
        self.window.btn_video_pipeline.setEnabled(True)
        self.window.btn_video_pipeline.setText("Video-Pipeline (Szenen + KI)")
        self.window.progress_bar.setVisible(False)
        self.window.status_bar.showMessage("Pipeline-Fehler | System bereit")
        if task_id:
            _get_task_manager().finish_task(task_id, "error", error_msg)

    def _start_proxy_creation(self, clip_id: int, video_path: str, title: str):
        task = _get_task_manager().create_task(
            f"Proxy: {title}", "NVENC 540p Edit-Proxy"
        )
        self.window.console_text.append(f"[Proxy] Erstelle Edit-Proxy fuer '{title}'...")

        worker = ProxyCreationWorker(clip_id, video_path)
        worker.task_id = task.task_id
        worker.finished.connect(
            lambda cid, path: self._on_proxy_finished(cid, path, title, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda cid, err: self._on_proxy_error(cid, err, title, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )

        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_proxy_finished(self, clip_id: int, proxy_path: str, title: str, task_id: str):
        if not proxy_path:
            task_manager = _get_task_manager()
            task = task_manager.get_task(task_id) if task_id else None
            if getattr(task, "status", None) == "cancelled":
                return
            task_manager.finish_task(task_id, "error", "Leerer Proxy-Pfad")
            return
        self.window.console_text.append(f"[Proxy] Fertig: '{title}' → {proxy_path}")
        self.window.media_table_controller._refresh_media_table_debounced()
        _get_task_manager().finish_task(task_id, "finished", proxy_path)

    def _on_proxy_error(self, clip_id: int, error_msg: str, title: str, task_id: str):
        self.window.console_text.append(f"[Proxy-Fehler] '{title}': {error_msg}")
        _get_task_manager().finish_task(task_id, "error", error_msg)
