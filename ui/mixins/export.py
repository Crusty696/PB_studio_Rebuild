"""Export Mixin fuer PBWindow — inkl. Preview-Export (erste 10 Sekunden)."""

import logging

from database import get_active_project_id
from services.task_manager import TaskManagerProxy
from services.export_service import get_timeline_summary, estimate_render_time
from workers import ExportWorker, PreviewExportWorker

logger = logging.getLogger(__name__)
task_manager = TaskManagerProxy()


class ExportMixin:
    """Export / Deliver methods for PBWindow."""

    def _refresh_production_info(self):
        summary = get_timeline_summary(get_active_project_id())
        self.production_info.setText(
            f"Video-Clips: {summary['video_clips']} | "
            f"Audio-Tracks: {summary['audio_tracks']} | "
            f"Gesamt-Eintraege: {summary['total_entries']} | "
            f"Geschaetzte Dauer: {summary['estimated_duration']:.1f}s"
        )
        self._update_render_estimate()

    def _update_render_estimate(self):
        """Aktualisiert die geschaetzte Renderzeit basierend auf aktuellen Settings."""
        try:
            resolution = self.resolution_combo.currentText()
            fps = float(self.fps_combo.currentText())
            estimate = estimate_render_time(
                get_active_project_id(), resolution, fps
            )
            preset_name = self.preset_combo.currentText()
            self.render_estimate_label.setText(
                f"Geschaetzte Renderzeit: {estimate['estimated_label']} | "
                f"Dauer: {estimate['total_duration']:.1f}s | "
                f"{estimate['segment_count']} Clips | "
                f"Preset: {preset_name}"
            )
        except (OSError, RuntimeError, ValueError) as e:
            logger.debug("Render-Schaetzung fehlgeschlagen: %s", e)
            self.render_estimate_label.setText("Geschaetzte Renderzeit: —")

    # ── Full Export ──────────────────────────────────────────────

    def _start_export(self):
        summary = get_timeline_summary(get_active_project_id())
        if summary["total_entries"] == 0:
            self.export_log.append("[Fehler] Keine Clips auf der Timeline!")
            return

        output_name = self.export_name_input.text().strip() or "output.mp4"
        if not output_name.endswith(".mp4"):
            output_name += ".mp4"

        resolution = self.resolution_combo.currentText()
        fps = float(self.fps_combo.currentText())

        task = task_manager.create_task(f"Export: {output_name}", "Video-Rendering")

        self.btn_export.setEnabled(False)
        self.btn_export.setText("Exportiere...")
        self.export_progress.setVisible(True)
        self.export_progress.setRange(0, 0)
        self.export_log.append(f"[Export] Starte Export: {output_name} ({resolution} @ {fps}fps)")

        worker = ExportWorker(project_id=get_active_project_id(), output_name=output_name,
                              resolution=resolution, fps=fps)
        worker.task_id = task.task_id
        worker.progress.connect(self._on_export_progress)
        worker.finished.connect(lambda p: self._on_export_finished(p, task.task_id))
        worker.error.connect(lambda err: self._on_export_error(err, task.task_id))

        self._start_worker_thread(worker)

    def _on_export_progress(self, pct: int, message: str):
        self.export_progress.setRange(0, 100)
        self.export_progress.setValue(pct)
        self.export_log.append(f"[Export] {message} ({pct}%)")

    def _on_export_finished(self, output_path: str, task_id: str = ""):
        if not output_path:
            self.btn_export.setEnabled(True)
            self.btn_export.setText("Video exportieren")
            self.export_progress.setVisible(False)
            if task_id:
                task_manager.finish_task(task_id, "error", "Leerer Export-Pfad")
            return
        self.btn_export.setEnabled(True)
        self.btn_export.setText("Video exportieren")
        self.export_progress.setVisible(False)
        self.export_log.append(f"[Export] FERTIG: {output_path}")
        self.console_text.append(f"[Export] Video exportiert: {output_path}")
        self.status_bar.showMessage(f"Export fertig: {output_path}")
        if task_id:
            task_manager.finish_task(task_id, "finished", output_path)

    def _on_export_error(self, error_msg: str, task_id: str = ""):
        self.btn_export.setEnabled(True)
        self.btn_export.setText("Video exportieren")
        self.export_progress.setVisible(False)
        self.export_log.append(f"[FEHLER] Export fehlgeschlagen: {error_msg}")
        self.console_text.append(f"[Fehler] Export: {error_msg}")
        if task_id:
            task_manager.finish_task(task_id, "error", error_msg)

    # ── Preview Export (erste 10 Sekunden) ───────────────────────

    def _start_preview_export(self):
        """Rendert die ersten 10 Sekunden der Timeline als Vorschau."""
        summary = get_timeline_summary(get_active_project_id())
        if summary["total_entries"] == 0:
            self.export_log.append("[Preview] Keine Clips auf der Timeline!")
            return

        resolution = self.resolution_combo.currentText()
        fps = float(self.fps_combo.currentText())

        self.btn_preview.setEnabled(False)
        self.btn_preview.setText("Rendere Vorschau...")
        self.export_progress.setVisible(True)
        self.export_progress.setRange(0, 0)
        self.export_log.append(
            f"[Preview] Starte Quick-Preview (10s) — {resolution} @ {fps}fps"
        )

        worker = PreviewExportWorker(
            project_id=get_active_project_id(),
            resolution=resolution,
            fps=fps,
            duration_limit=10.0,
        )
        worker.progress.connect(self._on_preview_progress)
        worker.finished.connect(self._on_preview_finished)
        worker.error.connect(self._on_preview_error)

        self._start_worker_thread(worker)

    def _on_preview_progress(self, pct: int, message: str):
        self.export_progress.setRange(0, 100)
        self.export_progress.setValue(pct)

    def _on_preview_finished(self, preview_path: str):
        self.btn_preview.setEnabled(True)
        self.btn_preview.setText("Quick-Preview (10s)")
        self.export_progress.setVisible(False)

        if not preview_path:
            self.export_log.append("[Preview] Vorschau fehlgeschlagen (leerer Pfad)")
            return

        self.export_log.append(f"[Preview] Vorschau fertig: {preview_path}")
        self.console_text.append(f"[Preview] Vorschau gerendert: {preview_path}")

        # Preview in das VideoPreviewWidget der Deliver-Workspace laden
        from pathlib import Path
        if Path(preview_path).exists():
            self._preview_path = preview_path
            self._deliver_ws.preview_video_label.setText("Vorschau geladen")
            self._deliver_ws.preview_video_label.setStyleSheet(
                "background-color: #1a1a2e; color: #22c55e; "
                "border: 1px solid #22c55e; border-radius: 4px;"
            )
            self._deliver_ws.btn_preview_play.setEnabled(True)
            self._deliver_ws.btn_preview_stop.setEnabled(True)

            # VideoPreviewWidget laden (wenn vorhanden in edit_workspace)
            if hasattr(self, 'video_preview'):
                self.video_preview.load_video(preview_path, 10.0)
                self.export_log.append("[Preview] Video-Player geladen — druecke Play")
        else:
            self.export_log.append("[Preview] Vorschau-Datei nicht gefunden")

    def _on_preview_error(self, error_msg: str):
        self.btn_preview.setEnabled(True)
        self.btn_preview.setText("Quick-Preview (10s)")
        self.export_progress.setVisible(False)
        self.export_log.append(f"[FEHLER] Vorschau fehlgeschlagen: {error_msg}")
        self.console_text.append(f"[Fehler] Preview: {error_msg}")

    def _play_preview(self):
        """Spielt die gerenderte Vorschau ab."""
        if hasattr(self, '_preview_path') and hasattr(self, 'video_preview'):
            from pathlib import Path
            if Path(self._preview_path).exists():
                self.video_preview.load_video(self._preview_path, 10.0)
                self.video_preview.play_from(0.0)

    def _stop_preview(self):
        """Stoppt die Vorschau-Wiedergabe."""
        if hasattr(self, 'video_preview'):
            self.video_preview.stop()
