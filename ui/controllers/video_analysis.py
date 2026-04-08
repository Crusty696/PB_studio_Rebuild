"""VideoAnalysisController — Refactored from VideoAnalysisMixin."""

from PySide6.QtCore import Qt
from services.task_manager import TaskManagerProxy
from workers import (
    VideoBatchAnalysisWorker, VideoAnalysisPipelineWorker,
    ProxyCreationWorker,
)
from ui.base_component import PBComponent

task_manager = TaskManagerProxy()

class VideoAnalysisController(PBComponent):
    """Video analysis methods for PBWindow."""

    def _on_video_pool_selected(self, row, col, prev_row, prev_col):
        """Sync video pool selection to hidden media_table."""
        if row < 0:
            return
        vid_id_item = self.window.video_pool_table.item(row, 1)
        if not vid_id_item:
            return
        vid_id = vid_id_item.text()
        for r in range(self.window.media_table.rowCount()):
            item = self.window.media_table.item(r, 0)
            type_item = self.window.media_table.item(r, 1)
            if item and type_item and item.text() == vid_id and type_item.text() == "Video":
                self.window.media_table.setCurrentCell(r, 0)
                break

    def _analyze_selected_video(self):
        # Batch: Alle angehakten Zeilen im Video Pool auslesen
        checked_rows = []
        for row in range(self.window.video_pool_table.rowCount()):
            chk_item = self.window.video_pool_table.item(row, 0)
            if chk_item and chk_item.checkState() == Qt.CheckState.Checked:
                checked_rows.append(row)

        if not checked_rows:
            row = self.window.video_pool_table.currentRow()
            if row >= 0:
                checked_rows.append(row)

        if not checked_rows:
            self.window.console_text.append("[Warnung] Keine Zeile im Video Pool ausgewaehlt oder angehakt.")
            return

        batch = []
        for row in checked_rows:
            id_item = self.window.video_pool_table.item(row, 1)
            title_item = self.window.video_pool_table.item(row, 2)
            if not id_item:
                continue
            clip_id = int(id_item.text())
            title = title_item.text() if title_item else f"Clip {clip_id}"
            batch.append((clip_id, title))

        if not batch:
            return

        self.window.btn_analyze_video.setEnabled(False)
        self.window.progress_bar.setVisible(True)
        self.window.progress_bar.setRange(0, len(batch))
        self.window.progress_bar.setValue(0)
        self.window.btn_analyze_video.setText(f"Analyse 0/{len(batch)}...")
        self.window.console_text.append(
            f"[Video] Batch-Analyse gestartet: {len(batch)} Videos (sequentiell)"
        )

        task = task_manager.create_task(
            f"Video-Batch ({len(batch)})", "Metadaten + Proxy"
        )

        worker = VideoBatchAnalysisWorker(batch)
        worker.task_id = task.task_id
        worker.item_done.connect(self._on_video_batch_item_done)
        worker.item_error.connect(self._on_video_batch_item_error)
        worker.finished.connect(
            lambda done, errors: self._on_video_batch_finished(done, errors, task.task_id)
        )
        worker.error.connect(lambda err: (
            self.window.console_text.append(f"[Video-Batch] Kritischer Fehler: {err}"),
            self._on_video_batch_finished(0, 1, task.task_id),
        ))
        self._video_batch_total = len(batch)
        self._video_batch_done = 0
        self._video_batch_errors = 0
        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_video_batch_item_done(self, clip_id: int, info: str):
        """Ein einzelnes Video im Batch ist fertig."""
        self._video_batch_done += 1
        self.window.progress_bar.setValue(self._video_batch_done)
        self.window.btn_analyze_video.setText(
            f"Analyse {self._video_batch_done}/{self._video_batch_total}..."
        )
        self.window.status_bar.showMessage(
            f"Video-Analyse: {self._video_batch_done}/{self._video_batch_total} — {info}"
        )

    def _on_video_batch_item_error(self, clip_id: int, error_msg: str):
        """Ein einzelnes Video im Batch ist fehlgeschlagen."""
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
        """Gesamter Batch ist fertig."""
        self.window.btn_analyze_video.setEnabled(True)
        self.window.btn_analyze_video.setText("Video analysieren")
        self.window.progress_bar.setVisible(False)
        self.window.media_table_controller._refresh_media_table()
        errors_info = f" ({errors} Fehler)" if errors else ""
        self.window.console_text.append(
            f"[Video] Batch-Analyse abgeschlossen: {done}/{self._video_batch_total}{errors_info}"
        )
        self.window.status_bar.showMessage(
            f"Alle {self._video_batch_total} Video-Analysen abgeschlossen | System bereit"
        )
        if task_id:
            status = "finished" if errors == 0 else "error"
            task_manager.finish_task(task_id, status, f"{done} fertig{errors_info}")

    def _start_video_pipeline(self):
        """Startet die 3-Schritt Video-Analyse-Pipeline für ALLE ausgewählten Videos."""
        selected_rows = set()
        for row in range(self.window.video_pool_table.rowCount()):
            chk_item = self.window.video_pool_table.item(row, 0)
            if chk_item and chk_item.checkState() == Qt.CheckState.Checked:
                selected_rows.add(row)
        if not selected_rows:
            for index in self.window.video_pool_table.selectionModel().selectedRows():
                selected_rows.add(index.row())
        if not selected_rows:
            row = self.window.video_pool_table.currentRow()
            if row >= 0:
                selected_rows.add(row)
        if not selected_rows:
            self.window.console_text.append("[Warnung] Keine Zeile im Video Pool ausgewaehlt oder angehakt.")
            return

        batch = []
        for row in sorted(selected_rows):
            id_item = self.window.video_pool_table.item(row, 1)
            title_item = self.window.video_pool_table.item(row, 2)
            if not id_item:
                continue
            clip_id = int(id_item.text())
            title = title_item.text() if title_item else f"Clip {clip_id}"
            batch.append((clip_id, title))

        if not batch:
            self.window.console_text.append("[Warnung] Keine gültigen Videos in der Auswahl.")
            return

        count = len(batch)
        label = batch[0][1] if count == 1 else f"{count} Videos"
        task = task_manager.create_task(
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
            lambda pct, msg: self._on_pipeline_progress(pct, msg, task.task_id)
        )
        worker.finished.connect(
            lambda cid, r: self._on_pipeline_finished(cid, r, label, task.task_id)
        )
        worker.error.connect(
            lambda cid, err: self._on_pipeline_error(cid, err, task.task_id)
        )

        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_pipeline_progress(self, pct: int, msg: str, task_id: str):
        last_pct = getattr(self, '_pipeline_last_pct', -10)
        if abs(pct - last_pct) >= 10 or "wird analysiert" in msg:
            self.window.console_text.append(f"[Pipeline] {msg} ({pct}%)")
            self._pipeline_last_pct = pct

    def _on_pipeline_finished(self, clip_id: int, result: dict, title: str, task_id: str):
        if not result:
            self.window.btn_video_pipeline.setEnabled(True)
            self.window.btn_video_pipeline.setText("Video-Pipeline (Szenen + KI)")
            self.window.progress_bar.setVisible(False)
            if task_id:
                task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
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
        self.window.media_table_controller._refresh_media_table()
        if task_id:
            task_manager.finish_task(
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
            task_manager.finish_task(task_id, "error", error_msg)

    def _start_proxy_creation(self, clip_id: int, video_path: str, title: str):
        """Startet NVENC Proxy-Erstellung im Hintergrund."""
        task = task_manager.create_task(
            f"Proxy: {title}", "NVENC 540p Edit-Proxy"
        )
        self.window.console_text.append(f"[Proxy] Erstelle Edit-Proxy fuer '{title}'...")

        worker = ProxyCreationWorker(clip_id, video_path)
        worker.task_id = task.task_id
        worker.finished.connect(
            lambda cid, path: self._on_proxy_finished(cid, path, title, task.task_id)
        )
        worker.error.connect(
            lambda cid, err: self._on_proxy_error(cid, err, title, task.task_id)
        )

        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_proxy_finished(self, clip_id: int, proxy_path: str, title: str, task_id: str):
        if not proxy_path:
            task_manager.finish_task(task_id, "error", "Leerer Proxy-Pfad")
            return
        self.window.console_text.append(f"[Proxy] Fertig: '{title}' → {proxy_path}")
        self.window.media_table_controller._refresh_media_table()
        task_manager.finish_task(task_id, "finished", proxy_path)

    def _on_proxy_error(self, clip_id: int, error_msg: str, title: str, task_id: str):
        self.window.console_text.append(f"[Proxy-Fehler] '{title}': {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)
