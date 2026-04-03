"""Video frame preview widget with timer-based playback."""

from pathlib import Path

from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QPixmap, QImage

from workers.video import FrameExtractWorker


class VideoPreviewWidget(QLabel):
    # Emitted with (current_sec, total_sec) whenever playback position advances
    position_changed = Signal(float, float)
    # Emitted when playback starts (True) or stops/pauses (False)
    playback_state_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("video_preview")
        self.setMinimumSize(100, 100)
        self.setMaximumHeight(400)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("Keine Vorschau")
        self.setScaledContents(False)
        self.setToolTip("Video-Vorschau: Zeigt den aktuell ausgewaehlten Clip als Einzelbild an")

        self._current_path: str | None = None
        self._current_time: float = 0.0
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(100)
        self._play_timer.timeout.connect(self._advance_frame)
        self._is_playing = False
        self._duration: float = 0.0
        self._frame_thread: QThread | None = None
        self._frame_worker: FrameExtractWorker | None = None

    def load_video(self, file_path: str, duration: float = 0.0):
        self._current_path = file_path
        self._current_time = 0.0
        self._duration = duration
        self.position_changed.emit(0.0, self._duration)
        self._extract_and_show_frame(0.0)

    def play_from(self, time_sec: float):
        if not self._current_path:
            return
        self._current_time = time_sec
        self._is_playing = True
        self.playback_state_changed.emit(True)
        self._play_timer.start()

    def stop(self):
        self._play_timer.stop()
        self._is_playing = False
        self.playback_state_changed.emit(False)
        self.position_changed.emit(self._current_time, self._duration)

    def toggle_play(self):
        if self._is_playing:
            self.stop()
        else:
            self.play_from(self._current_time)

    @property
    def duration(self) -> float:
        """Total duration of the currently loaded video (seconds)."""
        return self._duration

    def seek_to(self, time_sec: float):
        """Seek to an absolute time position."""
        if not self._current_path:
            return
        self._current_time = max(0.0, min(time_sec, self._duration) if self._duration > 0 else time_sec)
        self.position_changed.emit(self._current_time, self._duration)
        self._extract_and_show_frame(self._current_time)

    def seek_relative(self, delta_sec: float):
        """Seek forward (positive) or backward (negative) by delta seconds."""
        self.seek_to(self._current_time + delta_sec)

    def _advance_frame(self):
        self._current_time += 1.0 / 10.0
        if self._duration > 0 and self._current_time >= self._duration:
            self._current_time = 0.0
            self.stop()
            return
        self.position_changed.emit(self._current_time, self._duration)
        self._extract_and_show_frame(self._current_time)

    def _extract_and_show_frame(self, time_sec: float, vf_extra: str = ""):
        if not self._current_path or not Path(self._current_path).exists():
            self.setText("Datei nicht gefunden")
            return
        if self._frame_thread is not None and self._frame_thread.isRunning():
            # Alte Referenzen sichern bevor sie ueberschrieben werden
            old_thread = self._frame_thread
            old_worker = self._frame_worker
            try:
                old_worker.frame_ready.disconnect(self._on_frame_ready)
                old_worker.error.disconnect(self._on_frame_error)
                old_thread.finished.disconnect(self._on_frame_thread_finished)
            except (RuntimeError, TypeError):
                pass
            old_thread.quit()
            old_thread.wait(500)
            if old_worker is not None:
                old_worker.deleteLater()
            old_thread.deleteLater()
            self._frame_thread = None
            self._frame_worker = None

        worker = FrameExtractWorker(self._current_path, time_sec, 320, 180, vf_extra)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.frame_ready.connect(self._on_frame_ready)
        worker.error.connect(self._on_frame_error)
        worker.frame_ready.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(self._on_frame_thread_finished)

        self._frame_thread = thread
        self._frame_worker = worker
        thread.start()

    def _on_frame_thread_finished(self):
        """Cleanup nach Frame-Extraction — Referenzen freigeben."""
        if self._frame_worker is not None:
            self._frame_worker.deleteLater()
            self._frame_worker = None
        if self._frame_thread is not None:
            self._frame_thread.deleteLater()
            self._frame_thread = None

    def _on_frame_ready(self, raw_data: bytes, width: int, height: int):
        img = QImage(raw_data, width, height, width * 3, QImage.Format.Format_RGB888)
        self.setPixmap(QPixmap.fromImage(img))

    def _on_frame_error(self, msg: str):
        self.setText(msg)

    def hideEvent(self, event) -> None:
        self._play_timer.stop()
        if self._frame_thread is not None and self._frame_thread.isRunning():
            self._frame_thread.quit()
            self._frame_thread.wait(500)
        super().hideEvent(event)
