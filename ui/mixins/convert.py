"""Convert Mixin fuer PBWindow."""

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage, QPixmap

from database import engine, VideoClip, TimelineEntry, get_active_project_id
from sqlalchemy.orm import Session as DBSession

from services.task_manager import TaskManagerProxy

from workers import BatchConvertWorker, FrameExtractWorker

task_manager = TaskManagerProxy()


class ConvertMixin:
    """Convert workspace methods for PBWindow."""

    def _refresh_effects_combos(self):
        self.effects_clip_combo.clear()
        self.effects_clip_combo.addItem("-- Clip waehlen --", None)
        with DBSession(engine) as session:
            entries = (
                session.query(TimelineEntry)
                .filter_by(project_id=get_active_project_id(), track="video")
                .order_by(TimelineEntry.start_time)
                .all()
            )
            # Bug-19 Fix: Bulk-Load VideoClips — verhindert N+1 (1 SELECT statt N)
            _eids = [e.media_id for e in entries]
            _clips = (
                {c.id: c for c in session.query(VideoClip).filter(
                    VideoClip.id.in_(_eids)).all()}
                if _eids else {}
            )
            for entry in entries:
                clip = _clips.get(entry.media_id)
                if clip:
                    name = Path(clip.file_path).stem[:30]
                    label = f"[{entry.id}] {name} ({entry.start_time:.1f}s-{(entry.end_time or 0):.1f}s)"
                    self.effects_clip_combo.addItem(label, entry.id)

    def _on_effects_clip_changed(self, index: int):
        entry_id = self.effects_clip_combo.currentData()
        if entry_id is None:
            return
        with DBSession(engine) as session:
            entry = session.get(TimelineEntry, entry_id)
            if entry:
                self.brightness_slider.setValue(int((entry.brightness or 0.0) * 100))
                self.contrast_slider.setValue(int((entry.contrast or 1.0) * 100))
                self.crossfade_slider.setValue(int((entry.crossfade_duration or 0.0) * 10))

    def _apply_effects(self):
        entry_id = self.effects_clip_combo.currentData()
        if entry_id is None:
            self.console_text.append("[Effects] Kein Clip ausgewaehlt.")
            return

        brightness = self.brightness_slider.value() / 100.0
        contrast = self.contrast_slider.value() / 100.0
        crossfade = self.crossfade_slider.value() / 10.0

        with DBSession(engine) as session:
            entry = session.get(TimelineEntry, entry_id)
            if entry:
                entry.brightness = brightness
                entry.contrast = contrast
                entry.crossfade_duration = crossfade
                session.commit()

        self.console_text.append(
            f"[Effects] Clip {entry_id}: Helligkeit={brightness:.2f}, "
            f"Kontrast={contrast:.2f}, Crossfade={crossfade:.1f}s"
        )
        self._show_effect_preview(entry_id, brightness, contrast)

    def _show_effect_preview(self, entry_id: int, brightness: float, contrast: float):
        with DBSession(engine) as session:
            entry = session.get(TimelineEntry, entry_id)
            if not entry:
                return
            clip = session.get(VideoClip, entry.media_id)
            if not clip:
                return
            file_path = clip.file_path

        # Validate and clamp float values to prevent FFmpeg filter injection
        b = max(-1.0, min(1.0, float(brightness if brightness is not None else 0.0)))
        c = max(0.0, min(3.0, float(contrast if contrast is not None else 1.0)))
        vf_extra = f"eq=brightness={b}:contrast={c}"
        worker = FrameExtractWorker(file_path, 1.0, 320, 180, vf_extra)
        worker.frame_ready.connect(self._on_effect_frame_ready)
        worker.error.connect(lambda msg: self.effects_preview.setText(msg))
        # Kurzlebiger Task (Frame-Extraktion) — ueber Task-Engine
        self._start_worker_thread(worker)

    def _on_effect_frame_ready(self, raw_data: bytes, width: int, height: int):
        img = QImage(raw_data, width, height, width * 3, QImage.Format.Format_RGB888)
        self.effects_preview.setPixmap(QPixmap.fromImage(img))

    def _standardize_all_videos(self):
        """Konvertiert alle Videos im Video Pool ins gewaehlte Format per ffmpeg (im Worker-Thread)."""
        from services.ingest_service import get_all_video
        videos = get_all_video()
        if not videos:
            self.convert_log.append("[Convert] Keine Videos im Pool.")
            return

        # Parse settings
        res_text = self.convert_resolution.currentText()
        resolution = res_text.split(" ")[0]  # e.g. "1920x1080"

        fps_text = self.convert_fps.currentText()
        fps = fps_text.split(" ")[0]  # e.g. "30"

        fmt_text = self.convert_format.currentText()
        if "H.265" in fmt_text or "HEVC" in fmt_text:
            vcodec, ext = "libx265", ".mp4"
        elif "ProRes" in fmt_text:
            vcodec, ext = "prores_ks", ".mov"
        elif "mkv" in fmt_text:
            vcodec, ext = "libx264", ".mkv"
        else:
            vcodec, ext = "libx264", ".mp4"

        self.convert_progress.setVisible(True)
        self.convert_progress.setRange(0, len(videos))
        self.convert_progress.setValue(0)

        task = task_manager.create_task("Video Convert", f"{len(videos)} Videos -> {resolution} {fps}fps")

        worker = BatchConvertWorker(videos, resolution, fps, vcodec, ext)
        worker.task_id = task.task_id
        worker.progress.connect(lambda pct, msg: QTimer.singleShot(0, lambda: (
            self.convert_log.append(msg),
            self.convert_progress.setValue(pct),
        )))
        worker.finished.connect(lambda converted, total: self._on_batch_convert_finished(
            converted, total, task.task_id
        ))
        worker.error.connect(lambda err: self._on_batch_convert_error(err, task.task_id))

        self._start_worker_thread(worker)

    def _on_batch_convert_finished(self, converted: int, total: int, task_id: str):
        if converted == 0 and total == 0:
            # Empty-result fallback (finally block): hide progress and close task.
            self.convert_progress.setVisible(False)
            task_manager.finish_task(task_id, "error", "Leeres Ergebnis")
            return
        self.convert_progress.setVisible(False)
        task_manager.finish_task(task_id, message=f"{converted}/{total} konvertiert")
        self.convert_log.append(f"[Convert] Fertig: {converted}/{total} Videos konvertiert.")

    def _on_batch_convert_error(self, error_msg: str, task_id: str):
        self.convert_progress.setVisible(False)
        self.convert_log.append(f"[Convert-Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)
