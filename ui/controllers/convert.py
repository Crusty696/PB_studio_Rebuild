"""ConvertController — Refactored from ConvertMixin."""

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap
from database import VideoClip, TimelineEntry, get_active_project_id, nullpool_session
from services.task_manager import TaskManagerProxy
from workers import BatchConvertWorker, FrameExtractWorker
from ui.base_component import PBComponent

logger = logging.getLogger(__name__)
task_manager = TaskManagerProxy()

# Dedizierter Thread fuer DB-Queries — kein Main-Thread-Blocking
_db_pool: ThreadPoolExecutor | None = None
_db_pool_lock = threading.Lock()


def submit_convert_db_job(fn):
    """Submit a convert DB job via a lazily-created single-worker pool."""
    global _db_pool
    with _db_pool_lock:
        if _db_pool is None:
            _db_pool = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="convert_db",
            )
        return _db_pool.submit(fn)


def shutdown_convert_db_pool(timeout: float = 2.0) -> bool:
    """Stop the convert DB executor so app shutdown does not leak convert_db_0."""
    global _db_pool
    with _db_pool_lock:
        pool = _db_pool
        _db_pool = None
    if pool is None:
        return True
    pool.shutdown(wait=True, cancel_futures=True)
    return not any(t.name.startswith("convert_db") for t in threading.enumerate())

class ConvertController(PBComponent):
    """Convert workspace methods for PBWindow."""

    def _refresh_effects_combos(self):
        """Laedt Effects-Combo-Daten im Hintergrund-Thread, aktualisiert UI im Main-Thread."""
        self.window.effects_clip_combo.clear()
        self.window.effects_clip_combo.addItem("-- Clip waehlen --", None)

        project_id = get_active_project_id()

        def _fetch():
            items = []
            try:
                with nullpool_session() as session:
                    entries = (
                        session.query(TimelineEntry)
                        .filter_by(project_id=project_id, track="video")
                        .order_by(TimelineEntry.start_time)
                        .all()
                    )
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
                            items.append((label, entry.id))
            except Exception as e:
                logger.warning("[ConvertController] _refresh_effects_combos DB-Fehler: %s", e)
            QTimer.singleShot(0, lambda: self._populate_effects_combo(items))

        submit_convert_db_job(_fetch)

    def _populate_effects_combo(self, items: list[tuple[str, int]]):
        """Befuellt die Combo-Box im Main-Thread mit vorgeladenen Daten."""
        for label, entry_id in items:
            self.window.effects_clip_combo.addItem(label, entry_id)

    def _on_effects_clip_changed(self, index: int):
        entry_id = self.window.effects_clip_combo.currentData()
        if entry_id is None:
            return

        def _fetch():
            try:
                with nullpool_session() as session:
                    entry = session.get(TimelineEntry, entry_id)
                    if entry:
                        vals = (
                            int((entry.brightness or 0.0) * 100),
                            int((entry.contrast or 1.0) * 100),
                            int((entry.crossfade_duration or 0.0) * 10),
                        )
                        QTimer.singleShot(0, lambda: self._apply_clip_values(*vals))
            except Exception as e:
                logger.warning("[ConvertController] _on_effects_clip_changed DB-Fehler: %s", e)

        submit_convert_db_job(_fetch)

    def _apply_clip_values(self, brightness: int, contrast: int, crossfade: int):
        """Setzt Slider-Werte im Main-Thread."""
        self.window.brightness_slider.setValue(brightness)
        self.window.contrast_slider.setValue(contrast)
        self.window.crossfade_slider.setValue(crossfade)

    def _apply_effects(self):
        entry_id = self.window.effects_clip_combo.currentData()
        if entry_id is None:
            self.window.console_text.append("[Effects] Kein Clip ausgewaehlt.")
            return

        brightness = self.window.brightness_slider.value() / 100.0
        contrast = self.window.contrast_slider.value() / 100.0
        crossfade = self.window.crossfade_slider.value() / 10.0

        def _save():
            try:
                with nullpool_session() as session:
                    entry = session.get(TimelineEntry, entry_id)
                    if entry:
                        entry.brightness = brightness
                        entry.contrast = contrast
                        entry.crossfade_duration = crossfade
                        session.commit()
            except Exception as e:
                logger.warning("[ConvertController] _apply_effects DB-Fehler: %s", e)

        submit_convert_db_job(_save)

        self.window.console_text.append(
            f"[Effects] Clip {entry_id}: Helligkeit={brightness:.2f}, "
            f"Kontrast={contrast:.2f}, Crossfade={crossfade:.1f}s"
        )
        self._show_effect_preview(entry_id, brightness, contrast)

    def _show_effect_preview(self, entry_id: int, brightness: float, contrast: float):
        b = max(-1.0, min(1.0, float(brightness)))
        c = max(0.0, min(3.0, float(contrast)))

        def _fetch_and_preview():
            try:
                with nullpool_session() as session:
                    entry = session.get(TimelineEntry, entry_id)
                    if not entry:
                        return
                    clip = session.get(VideoClip, entry.media_id)
                    if not clip:
                        return
                    file_path = clip.file_path

                vf_extra = f"eq=brightness={b}:contrast={c}"
                QTimer.singleShot(0, lambda: self._start_effect_worker(file_path, vf_extra))
            except Exception as e:
                logger.warning("[ConvertController] _show_effect_preview DB-Fehler: %s", e)

        submit_convert_db_job(_fetch_and_preview)

    def _start_effect_worker(self, file_path: str, vf_extra: str):
        """Startet FrameExtractWorker im Main-Thread (Worker-Erstellung muss im Main-Thread sein)."""
        # B-390: monotone Request-Sequenz. Ein spaeter fertig werdender aelterer
        # Worker darf die Vorschau des juengsten Requests nicht ueberschreiben.
        req_id = getattr(self, "_effect_request_seq", 0) + 1
        self._effect_request_seq = req_id
        worker = FrameExtractWorker(file_path, 1.0, 320, 180, vf_extra)
        worker.frame_ready.connect(
            lambda raw, w, h, rid=req_id: self._on_effect_frame_ready(raw, w, h, rid),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda msg: QTimer.singleShot(0, lambda: self.window.effects_preview.setText(msg)),
            Qt.ConnectionType.QueuedConnection,
        )
        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_effect_frame_ready(self, raw_data: bytes, width: int, height: int, req_id: int | None = None):
        # B-390: nur das Frame des juengsten Requests setzt die UI.
        if req_id is not None and req_id != getattr(self, "_effect_request_seq", req_id):
            return
        img = QImage(raw_data, width, height, width * 3, QImage.Format.Format_RGB888)
        self.window.effects_preview.setPixmap(QPixmap.fromImage(img))

    def _standardize_all_videos(self):
        """Konvertiert alle Videos im Video Pool ins gewaehlte Format."""
        from services.ingest_service import get_all_video
        videos = get_all_video()
        if not videos:
            self.window.convert_log.append("[Convert] Keine Videos im Pool.")
            return

        res_text = self.window.convert_resolution.currentText()
        resolution = res_text.split(" ")[0]
        fps_text = self.window.convert_fps.currentText()
        fps = fps_text.split(" ")[0]
        fmt_text = self.window.convert_format.currentText()
        if "H.265" in fmt_text or "HEVC" in fmt_text:
            vcodec, ext = "hevc_nvenc", ".mp4"
        elif "ProRes" in fmt_text:
            vcodec, ext = "prores_ks", ".mov"
        elif "mkv" in fmt_text:
            vcodec, ext = "libx264", ".mkv"
        else:
            vcodec, ext = "libx264", ".mp4"

        self.window.convert_progress.setVisible(True)
        self.window.convert_progress.setRange(0, 100)
        self.window.convert_progress.setValue(0)

        task = task_manager.create_task("Video Convert", f"{len(videos)} Videos -> {resolution} {fps}fps")
        worker = BatchConvertWorker(videos, resolution, fps, vcodec, ext)
        worker.task_id = task.task_id
        worker.progress.connect(
            lambda pct, msg: QTimer.singleShot(0, lambda: (
                self.window.convert_log.append(msg),
                self.window.convert_progress.setValue(pct),
            )),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.finished.connect(
            lambda converted, total: self._on_batch_convert_finished(
                converted, total, task.task_id
            ),
            Qt.ConnectionType.QueuedConnection,
        )
        worker.error.connect(
            lambda err: self._on_batch_convert_error(err, task.task_id),
            Qt.ConnectionType.QueuedConnection,
        )
        self.window.worker_dispatcher._start_worker_thread(worker)

    def _on_batch_convert_finished(self, converted: int, total: int, task_id: str):
        self.window.convert_progress.setVisible(False)
        task_manager.finish_task(task_id, message=f"{converted}/{total} konvertiert")
        self.window.convert_log.append(f"[Convert] Fertig: {converted}/{total} Videos konvertiert.")

    def _on_batch_convert_error(self, error_msg: str, task_id: str):
        self.window.convert_progress.setVisible(False)
        self.window.convert_log.append(f"[Convert-Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)
