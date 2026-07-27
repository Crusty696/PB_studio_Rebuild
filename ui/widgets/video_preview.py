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

    # B-710-Follow-up: Die Stream-Generation reist im Signal mit, statt in
    # einer Lambda-Closure im Widget zu haengen. Grund: PySide6 trennt
    # Verbindungen zu GEBUNDENEN METHODEN automatisch, sobald das
    # Empfaenger-C++-Objekt zerstoert wird — bei freien Lambdas nicht. Ein
    # Lambda auf ``frame_ready`` (15 Frames/s) haette nach der Zerstoerung
    # des QLabel weiter gefeuert und "RuntimeError: Internal C++ object
    # (QLabel) already deleted" geworfen.
    frame_ready = Signal(bytes, int)   # (Rohframe _W*_H*3 Bytes, Generation)
    finished = Signal()                # Stream-Ende (EOF oder stop())
    error = Signal(str, int)           # (Meldung, Generation)
    # ``QThread.finished`` traegt selbst keine Generation. Der Worker kennt
    # sie und reicht sie weiter, damit auch dieser Widget-Slot eine gebundene
    # Methode bleiben kann.
    thread_finished = Signal(int)      # (Generation)

    def __init__(self, file_path: str, start_sec: float, generation: int = 0):
        super().__init__()
        self._file_path = file_path
        self._start_sec = max(0.0, float(start_sec))
        self._proc: subprocess.Popen | None = None
        self._stop_requested = False
        self.generation = int(generation)

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
                self.frame_ready.emit(data, self.generation)
        except Exception as e:  # noqa: BLE001 — Wiedergabe darf App nie reissen
            if not self._stop_requested:
                logger.error("PreviewStream fehlgeschlagen: %s", e)
                self.error.emit(str(e), self.generation)
        finally:
            self._kill_proc()
            self.finished.emit()

    def notify_thread_finished(self):
        """Slot fuer ``QThread.finished`` — haengt die Generation an.

        Laeuft im Worker-Thread (finished wird dort emittiert); das daraus
        emittierte ``thread_finished`` erreicht das Widget wie zuvor per
        Queued Connection im GUI-Thread.
        """
        self.thread_finished.emit(self.generation)

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
        # B-710: Generation des aktuell gueltigen Wiedergabe-Streams. Jeder
        # Teardown erhoeht sie. Signale eines abgeloesten Streams, die noch in
        # der Event-Queue liegen, tragen die alte Generation und werden in den
        # Slots verworfen.
        self._stream_generation: int = 0
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

        # B-710: _teardown_stream() hat die Generation gerade erhoeht — dieser
        # Stream bindet seine Slots an genau diesen Wert.
        # B-710-Follow-up: Die Generation wandert in den Worker, alle drei
        # Widget-Slots sind gebundene Methoden (kein freies Lambda) — damit
        # trennt PySide6 sie automatisch, wenn das QLabel zerstoert wird.
        generation = self._stream_generation
        worker = _PreviewStreamWorker(
            self._current_path, self._current_time, generation
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.frame_ready.connect(self._on_stream_frame)
        worker.error.connect(self._on_stream_error)
        worker.finished.connect(thread.quit)
        # DirectConnection: der Worker haengt per moveToThread am Stream-Thread.
        # Ohne sie waere diese Verbindung queued auf einen Thread, dessen
        # Event-Loop beim finished-Signal gerade endet — die Generation kaeme
        # nie an. Der Slot emittiert nur weiter, das ist thread-sicher; das
        # Weiter-Signal an das Widget bleibt wie zuvor queued in den GUI-Thread.
        thread.finished.connect(
            worker.notify_thread_finished, Qt.ConnectionType.DirectConnection
        )
        worker.thread_finished.connect(self._on_stream_thread_finished)
        self._stream_worker = worker
        self._stream_thread = thread
        thread.start()

    def stop(self):
        self._teardown_stream()
        self._is_playing = False
        self.playback_state_changed.emit(False)
        self.position_changed.emit(self._current_time, self._duration)

    def _teardown_stream(self):
        """Beendet den Wiedergabe-Stream B-652-sicher (kein Referenz-Drop).

        B-710: Die Lebenszyklus-Logik (Referenz-Parken der sterbenden Threads)
        bleibt unveraendert — sie ist der B-652-Crash-Schutz. Ergaenzt wird nur
        die Generation: ab hier gehoert kein noch in der Queue liegendes Signal
        des alten Streams mehr zum aktuellen Zustand.
        """
        self._stream_generation += 1
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

    def _on_stream_frame(self, raw_data: bytes, generation: int):
        if generation != self._stream_generation:
            # B-710: Frame eines abgeloesten Streams (z.B. nach Seek) — darf
            # weder angezeigt werden noch die Position weiterzaehlen.
            return
        if self._stream_worker is None or not self._is_playing:
            return  # spaeter Frame eines bereits gestoppten Streams
        self._stream_frames += 1
        self._current_time = self._stream_start_sec + self._stream_frames / _PREVIEW_FPS
        img = QImage(raw_data, _PREVIEW_W, _PREVIEW_H, _PREVIEW_W * 3,
                     QImage.Format.Format_RGB888).copy()
        self.setPixmap(QPixmap.fromImage(img))
        self.position_changed.emit(self._current_time, self._duration)

    def _on_stream_error(self, msg: str, generation: int):
        """Fehler des Wiedergabe-Streams — nur der AKTUELLE darf ans Widget.

        B-710-Follow-up: ``error`` war als einziges der drei Stream-Signale
        ungegated. ``run()`` unterdrueckt zwar Fehler NACH ``stop()``, aber
        ein VOR dem Seek emittierter Fehler liegt danach noch in der
        Qt-Queue. Ohne Generations-Pruefung rief er ``_on_frame_error`` ->
        ``setText()`` und loeschte damit die Pixmap des bereits laufenden
        NEUEN Streams, waehrend ``_is_playing`` True blieb.
        """
        if generation != self._stream_generation:
            return
        self._on_frame_error(msg)

    def _on_stream_thread_finished(self, generation: int):
        """Stream-Ende (EOF/Fehler/Stop): Play-Status zuruecksetzen."""
        if generation != self._stream_generation:
            # B-710: finished des abgeloesten Streams. Sein Teardown ist
            # bereits gelaufen; hier weiterzumachen wuerde den inzwischen
            # gestarteten neuen Stream stoppen.
            return
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
