"""Video frame preview widget.

Einzelbild/Scrubbing: FrameExtractWorker (ffmpeg, 1 Frame pro Aufruf).
Wiedergabe (User 2026-07-17): persistenter ffmpeg-Stream statt Prozess-pro-
Frame — EIN ffmpeg dekodiert mit Echtzeit-Pacing (-re) rawvideo in eine
Pipe, ein Leser-Thread liefert fertige Frames. Vorher stotterte Play, weil
pro 100ms-Tick ein neuer ffmpeg-Prozess (Spawn+Seek+Decode ~50-200ms)
gestartet wurde.
"""

import logging
import subprocess
from pathlib import Path

from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt, QObject, QThread, QTimer, Signal
from PySide6.QtGui import QPixmap, QImage

from services.ffmpeg_utils import subprocess_kwargs
from services.startup_checks import get_ffmpeg_bin
from workers.video import FrameExtractWorker

logger = logging.getLogger(__name__)

_PREVIEW_W = 320
_PREVIEW_H = 180
_PREVIEW_FPS = 15.0


class _PreviewStreamWorker(QObject):
    """Liest einen kontinuierlichen rawvideo-Stream aus EINEM ffmpeg-Prozess.

    ffmpeg laeuft mit ``-re`` (Echtzeit-Pacing) — der blockierende
    ``stdout.read`` liefert die Frames dadurch im Video-Takt, ohne dass der
    GUI-Thread irgendetwas takten muss.
    """

    frame_ready = Signal(bytes)   # genau _PREVIEW_W*_PREVIEW_H*3 Bytes
    finished = Signal()           # Stream-Ende (EOF oder stop())
    error = Signal(str)

    def __init__(self, file_path: str, start_sec: float):
        super().__init__()
        self._file_path = file_path
        self._start_sec = max(0.0, float(start_sec))
        self._proc: subprocess.Popen | None = None
        self._stop_requested = False

    def run(self):
        frame_size = _PREVIEW_W * _PREVIEW_H * 3
        try:
            cmd = [
                get_ffmpeg_bin(),
                "-re",                      # Echtzeit-Pacing der Ausgabe
                "-ss", str(self._start_sec),
                "-i", self._file_path,
                "-vf", f"fps={_PREVIEW_FPS},scale={_PREVIEW_W}:{_PREVIEW_H}",
                "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-an", "-v", "error", "pipe:1",
            ]
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                **subprocess_kwargs(),
            )
            stdout = self._proc.stdout
            while not self._stop_requested:
                data = stdout.read(frame_size) if stdout else b""
                if len(data) < frame_size:
                    break  # EOF (Dateiende) oder Prozess beendet
                self.frame_ready.emit(data)
        except Exception as e:  # noqa: BLE001 — Wiedergabe darf App nie reissen
            if not self._stop_requested:
                logger.error("PreviewStream fehlgeschlagen: %s", e)
                self.error.emit(str(e))
        finally:
            self._kill_proc()
            self.finished.emit()

    def stop(self):
        """Thread-safe: beendet den Stream (kill unblockt den read)."""
        self._stop_requested = True
        self._kill_proc()

    def _kill_proc(self):
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass


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
        self._is_playing = False
        self._duration: float = 0.0
        self._frame_thread: QThread | None = None
        self._frame_worker: FrameExtractWorker | None = None
        self._pending_frame_request: tuple[float, str] | None = None
        # B-387: Pfad, fuer den der aktuell laufende Worker erzeugt wurde.
        # Spaet eintreffende Frames eines frueheren Videos werden verworfen.
        self._active_request_path: str | None = None
        # Persistenter Wiedergabe-Stream (User 2026-07-17)
        self._stream_worker: _PreviewStreamWorker | None = None
        self._stream_thread: QThread | None = None
        self._stream_start_sec: float = 0.0
        self._stream_frames: int = 0
        # B-652-Schutz: gestoppte Stream-Threads bis finished referenzieren —
        # niemals die letzte Referenz auf einen laufenden QThread fallen lassen.
        self._dying_stream_threads: list[QThread] = []

    def load_video(self, file_path: str, duration: float = 0.0):
        if self._is_playing:
            self.stop()
        self._current_path = file_path
        self._current_time = 0.0
        self._duration = duration
        self.position_changed.emit(0.0, self._duration)
        self._extract_and_show_frame(0.0)

    def play_from(self, time_sec: float):
        if not self._current_path:
            return
        self._teardown_stream()
        self._current_time = max(0.0, float(time_sec))
        self._stream_start_sec = self._current_time
        self._stream_frames = 0
        self._is_playing = True
        self.playback_state_changed.emit(True)

        worker = _PreviewStreamWorker(self._current_path, self._current_time)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.frame_ready.connect(self._on_stream_frame)
        worker.error.connect(self._on_frame_error)
        worker.finished.connect(thread.quit)
        thread.finished.connect(self._on_stream_thread_finished)
        self._stream_worker = worker
        self._stream_thread = thread
        thread.start()

    def stop(self):
        self._teardown_stream()
        self._is_playing = False
        self.playback_state_changed.emit(False)
        self.position_changed.emit(self._current_time, self._duration)

    def _teardown_stream(self):
        """Beendet den Wiedergabe-Stream B-652-sicher (kein Referenz-Drop)."""
        worker = self._stream_worker
        thread = self._stream_thread
        self._stream_worker = None
        self._stream_thread = None
        if worker is not None:
            worker.stop()  # killt ffmpeg -> read unblockt -> run() endet
        if thread is not None:
            if thread.isRunning():
                thread.quit()
                self._dying_stream_threads.append(thread)
                thread.finished.connect(
                    lambda t=thread: self._dying_stream_threads.remove(t)
                    if t in self._dying_stream_threads else None
                )
            thread.finished.connect(thread.deleteLater)
        if worker is not None:
            if thread is not None and thread.isRunning():
                thread.finished.connect(worker.deleteLater)
            else:
                worker.deleteLater()

    def _on_stream_frame(self, raw_data: bytes):
        if self._stream_worker is None or not self._is_playing:
            return  # spaeter Frame eines bereits gestoppten Streams
        self._stream_frames += 1
        self._current_time = self._stream_start_sec + self._stream_frames / _PREVIEW_FPS
        img = QImage(raw_data, _PREVIEW_W, _PREVIEW_H, _PREVIEW_W * 3,
                     QImage.Format.Format_RGB888).copy()
        self.setPixmap(QPixmap.fromImage(img))
        self.position_changed.emit(self._current_time, self._duration)

    def _on_stream_thread_finished(self):
        """Stream-Ende (EOF/Fehler/Stop): Play-Status zuruecksetzen."""
        if self._stream_thread is not None and self._is_playing:
            # EOF vom ffmpeg (Dateiende) — nicht durch stop() ausgeloest
            self._teardown_stream()
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
        if self._is_playing:
            # Laufende Wiedergabe: Stream an neuer Position neu aufsetzen.
            self.play_from(self._current_time)
            return
        self.position_changed.emit(self._current_time, self._duration)
        self._extract_and_show_frame(self._current_time)

    def seek_relative(self, delta_sec: float):
        """Seek forward (positive) or backward (negative) by delta seconds."""
        self.seek_to(self._current_time + delta_sec)

    def _extract_and_show_frame(self, time_sec: float, vf_extra: str = ""):
        if not self._current_path or not Path(self._current_path).exists():
            self.setText("Datei nicht gefunden")
            return
        if self._frame_thread is not None and self._frame_thread.isRunning():
            self._pending_frame_request = (float(time_sec), vf_extra)
            return

        self._active_request_path = self._current_path
        worker = FrameExtractWorker(self._current_path, time_sec, 320, 180, vf_extra)
        thread = QThread(self)
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
        pending = self._pending_frame_request
        self._pending_frame_request = None
        if pending is not None and self._current_path:
            QTimer.singleShot(0, lambda: self._extract_and_show_frame(*pending))

    def _on_frame_ready(self, raw_data: bytes, width: int, height: int):
        # B-387: Frame nur anzeigen, wenn es zum aktuell geladenen Video gehoert.
        # Ein spaet eintreffendes Frame eines frueheren load_video()-Pfads wird verworfen.
        if self._active_request_path != self._current_path:
            return
        img = QImage(raw_data, width, height, width * 3, QImage.Format.Format_RGB888).copy()
        self.setPixmap(QPixmap.fromImage(img))

    def _on_frame_error(self, msg: str):
        self.setText(msg)

    def hideEvent(self, event) -> None:
        if self._is_playing:
            self.stop()
        if self._frame_thread is not None and self._frame_thread.isRunning():
            self._frame_thread.quit()
            # Nicht blockierend warten — deleteLater raeumt async auf.
            # wait(500) blockierte Main-Thread beim Tab-Wechsel.
            self._frame_thread.finished.connect(self._frame_thread.deleteLater)
        super().hideEvent(event)
