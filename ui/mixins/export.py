"""Export Mixin fuer PBWindow."""

from services.task_manager import GlobalTaskManager
from services.export_service import get_timeline_summary
from workers import ExportWorker


# task_manager Proxy — gleiche Logik wie in main.py
class _TaskManagerProxy:
    def __getattr__(self, name):
        return getattr(GlobalTaskManager.instance(), name)

task_manager = _TaskManagerProxy()


class ExportMixin:
    """Export / Deliver methods for PBWindow."""

    def _refresh_production_info(self):
        summary = get_timeline_summary()
        self.production_info.setText(
            f"Video-Clips: {summary['video_clips']} | "
            f"Audio-Tracks: {summary['audio_tracks']} | "
            f"Gesamt-Eintraege: {summary['total_entries']} | "
            f"Geschaetzte Dauer: {summary['estimated_duration']:.1f}s"
        )

    def _start_export(self):
        summary = get_timeline_summary()
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

        worker = ExportWorker(project_id=1, output_name=output_name,
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
            # Empty-result fallback (finally block): re-enable UI and close task.
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
