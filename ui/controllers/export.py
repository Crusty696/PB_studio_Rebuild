"""ExportController — Refactored from ExportMixin."""

import logging
from PySide6.QtCore import Qt, QThread, QObject, Signal
from database import get_active_project_id
from services.task_manager import TaskManagerProxy
from services.export_service import get_timeline_summary, estimate_render_time
from workers import ExportWorker, PreviewExportWorker
from ui.base_component import PBComponent

logger = logging.getLogger(__name__)
task_manager = TaskManagerProxy()


class _ProductionInfoWorker(QObject):
    """FREEZE-Fix 2026-07-10: get_timeline_summary + estimate_render_time
    liefen beim EXPORT-Workspace-Wechsel SYNCHRON im Main-Thread. Bei busy DB
    (Hintergrund-Writer + busy_timeout) fror der Klick die UI 20-60s ein
    (freeze_stacks-Watchdog-Beweis: Query.all in get_all_audio). Beide
    DB-Reads laufen jetzt hier im Hintergrund-Thread."""

    done = Signal(dict, object)  # (summary, estimate|None)

    def __init__(self, project_id, resolution: str, fps: float):
        super().__init__()
        self._project_id = project_id
        self._resolution = resolution
        self._fps = fps

    def run(self):
        try:
            summary = get_timeline_summary(self._project_id)
        except Exception as e:  # noqa: BLE001 — Label-Refresh darf nie crashen
            logger.debug("ProductionInfo summary fehlgeschlagen: %s", e)
            self.done.emit({}, None)
            return
        estimate = None
        try:
            # virt-M4-Fix: summary weiterreichen — vorher lief derselbe
            # Timeline-Scan pro EXPORT-Klick doppelt (get_timeline_summary
            # intern nochmal in estimate_render_time).
            estimate = estimate_render_time(
                self._project_id, self._resolution, self._fps, summary=summary
            )
        except (OSError, RuntimeError, ValueError) as e:
            logger.debug("Render-Schaetzung fehlgeschlagen: %s", e)
        self.done.emit(summary, estimate)


class ExportController(PBComponent):
    """Export / Deliver methods for PBWindow."""

    def _refresh_production_info(self):
        """Startet den async Refresh der Produktions-Infos (nicht-blockierend).

        UI-Werte (Combos) werden VOR dem Worker-Start im Main-Thread gelesen;
        die DB-Reads laufen im Worker; die Labels setzt der done-Slot (queued,
        Main-Thread). Doppelstart-Guard: laeuft bereits ein Refresh, wird der
        Klick ignoriert (der laufende liefert gleich frische Werte).
        """
        if getattr(self, "_pinfo_thread", None) is not None and self._pinfo_thread.isRunning():
            return
        try:
            resolution = self.window.resolution_combo.currentText()
            fps = float(self.window.fps_combo.currentText())
        except (AttributeError, ValueError):
            resolution, fps = "1920x1080", 30.0
        self.window.production_info.setText("Lade Produktions-Infos…")

        worker = _ProductionInfoWorker(get_active_project_id(), resolution, fps)
        thread = QThread(self.window)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self._on_production_info_ready, Qt.ConnectionType.QueuedConnection)
        worker.done.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        # Controller lebt app-lang -> Referenzen hier sind GC-sicher (B-605-Lektion).
        self._pinfo_worker = worker
        self._pinfo_thread = thread
        thread.start()

    def _on_production_info_ready(self, summary: dict, estimate) -> None:
        self._pinfo_worker = None
        self._pinfo_thread = None
        if not summary:
            self.window.production_info.setText("Produktions-Infos nicht verfuegbar.")
            self.window.render_estimate_label.setText("Geschaetzte Renderzeit: —")
            return
        self.window.production_info.setText(
            f"Video-Clips: {summary['video_clips']} | "
            f"Audio-Tracks: {summary['audio_tracks']} | "
            f"Gesamt-Eintraege: {summary['total_entries']} | "
            f"Geschaetzte Dauer: {summary['estimated_duration']:.1f}s"
        )
        if estimate is None:
            self.window.render_estimate_label.setText("Geschaetzte Renderzeit: —")
            return
        preset_name = self.window.preset_combo.currentText()
        self.window.render_estimate_label.setText(
            f"Geschaetzte Renderzeit: {estimate['estimated_label']} | "
            f"Dauer: {estimate['total_duration']:.1f}s | "
            f"{estimate['segment_count']} Clips | "
            f"Preset: {preset_name}"
        )

    def _update_render_estimate(self):
        """Aktualisiert die Render-Schaetzung — delegiert an den async Refresh
        (FREEZE-Fix 2026-07-10: vorher synchrone DB-Reads im Main-Thread)."""
        self._refresh_production_info()

    def _start_export(self):
        summary = get_timeline_summary(get_active_project_id())
        if summary["total_entries"] == 0:
            self.window.export_log.append("[Fehler] Keine Clips auf der Timeline!")
            return

        output_name = self.window.export_name_input.text().strip() or "output.mp4"
        if not output_name.endswith(".mp4"):
            output_name += ".mp4"

        resolution = self.window.resolution_combo.currentText()
        fps = float(self.window.fps_combo.currentText())

        task = task_manager.create_task(f"Export: {output_name}", "Video-Rendering")
        self.window.btn_export.setEnabled(False)
        self.window.btn_export.setText("Exportiere...")
        self.window.export_progress.setVisible(True)
        self.window.export_progress.setRange(0, 0)
        self.window.export_log.append(f"[Export] Starte Export: {output_name} ({resolution} @ {fps}fps)")

        worker = ExportWorker(project_id=get_active_project_id(), output_name=output_name,
                              resolution=resolution, fps=fps)
        worker.task_id = task.task_id
        worker.progress.connect(self._on_export_progress, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(
            lambda p: self._on_export_finished(p, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda err: self._on_export_error(err, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_export_progress(self, pct: int, message: str):
        self.window.export_progress.setRange(0, 100)
        self.window.export_progress.setValue(pct)
        self.window.export_log.append(f"[Export] {message} ({pct}%)")

    def _on_export_finished(self, output_path: str, task_id: str = ""):
        self.window.btn_export.setEnabled(True)
        self.window.btn_export.setText("Video exportieren")
        self.window.export_progress.setVisible(False)
        if not output_path:
            if task_id:
                task_manager.finish_task(task_id, "error", "Leerer Export-Pfad")
            return
        self.window.export_log.append(f"[Export] FERTIG: {output_path}")
        self.window.console_text.append(f"[Export] Video exportiert: {output_path}")
        self.window.status_bar.showMessage(f"Export fertig: {output_path}")
        if task_id:
            task_manager.finish_task(task_id, "finished", output_path)

    def _on_export_error(self, error_msg: str, task_id: str = ""):
        self.window.btn_export.setEnabled(True)
        self.window.btn_export.setText("Video exportieren")
        self.window.export_progress.setVisible(False)
        self.window.export_log.append(f"[FEHLER] Export fehlgeschlagen: {error_msg}")
        self.window.console_text.append(f"[Fehler] Export: {error_msg}")
        if task_id:
            task_manager.finish_task(task_id, "error", error_msg)

    def _start_preview_export(self):
        """Rendert die ersten 10 Sekunden der Timeline als Vorschau."""
        summary = get_timeline_summary(get_active_project_id())
        if summary["total_entries"] == 0:
            self.window.export_log.append("[Preview] Keine Clips auf der Timeline!")
            return

        resolution = self.window.resolution_combo.currentText()
        fps = float(self.window.fps_combo.currentText())

        self.window.btn_preview.setEnabled(False)
        self.window.btn_preview.setText("Rendere Vorschau...")
        self.window.export_progress.setVisible(True)
        self.window.export_progress.setRange(0, 0)
        self.window.export_log.append(
            f"[Preview] Starte Quick-Preview (10s) — {resolution} @ {fps}fps"
        )

        worker = PreviewExportWorker(
            project_id=get_active_project_id(),
            resolution=resolution,
            fps=fps,
            duration_limit=10.0,
        )
        worker.progress.connect(self._on_preview_progress, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(self._on_preview_finished, Qt.ConnectionType.QueuedConnection)
        worker.error.connect(self._on_preview_error, Qt.ConnectionType.QueuedConnection)
        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_preview_progress(self, pct: int, message: str):
        self.window.export_progress.setRange(0, 100)
        self.window.export_progress.setValue(pct)

    def _on_preview_finished(self, preview_path: str):
        self.window.btn_preview.setEnabled(True)
        self.window.btn_preview.setText("Quick-Preview (10s)")
        self.window.export_progress.setVisible(False)

        if not preview_path:
            self.window.export_log.append("[Preview] Vorschau fehlgeschlagen (leerer Pfad)")
            return

        self.window.export_log.append(f"[Preview] Vorschau fertig: {preview_path}")
        self.window.console_text.append(f"[Preview] Vorschau gerendert: {preview_path}")

        from pathlib import Path
        if Path(preview_path).exists():
            self.window._preview_path = preview_path
            self.window._deliver_ws.preview_video_label.setText("Vorschau geladen")
            self.window._deliver_ws.preview_video_label.setStyleSheet(
                "background-color: #1a1a2e; color: #22c55e; "
                "border: 1px solid #22c55e; border-radius: 4px;"
            )
            self.window._deliver_ws.btn_preview_play.setEnabled(True)
            self.window._deliver_ws.btn_preview_stop.setEnabled(True)
            if hasattr(self.window, 'video_preview'):
                self.window.video_preview.load_video(preview_path, 10.0)
                self.window.export_log.append("[Preview] Video-Player geladen — druecke Play")
        else:
            self.window.export_log.append("[Preview] Vorschau-Datei nicht gefunden")

    def _on_preview_error(self, error_msg: str):
        self.window.btn_preview.setEnabled(True)
        self.window.btn_preview.setText("Quick-Preview (10s)")
        self.window.export_progress.setVisible(False)
        self.window.export_log.append(f"[FEHLER] Vorschau fehlgeschlagen: {error_msg}")
        self.window.console_text.append(f"[Fehler] Preview: {error_msg}")

    def _play_preview(self):
        """Spielt die gerenderte Vorschau ab."""
        if hasattr(self.window, '_preview_path') and hasattr(self.window, 'video_preview'):
            from pathlib import Path
            if Path(self.window._preview_path).exists():
                self.window.video_preview.load_video(self.window._preview_path, 10.0)
                self.window.video_preview.play_from(0.0)

    def _stop_preview(self):
        """Stoppt die Vorschau-Wiedergabe."""
        if hasattr(self.window, 'video_preview'):
            self.window.video_preview.stop()
