"""
PB_studio v0.4.0 — DaVinci Resolve Style UI Rebuild
=====================================================
4 Arbeitsbereiche: MEDIA | EDIT | CONVERT | DELIVER
Bottom-Navigationsleiste wie DaVinci Resolve.
Optimierte Timeline mit Caching.
"""

from dotenv import load_dotenv
load_dotenv()

import sys
import subprocess
import time
import logging
import traceback
import uuid
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QStatusBar, QDockWidget, QTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QSplitter, QFileDialog, QHeaderView,
    QProgressBar, QLabel, QLineEdit, QSlider, QGroupBox,
    QComboBox, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsTextItem, QGraphicsLineItem, QDialog, QFrame,
    QTreeWidget, QTreeWidgetItem, QCheckBox, QStackedWidget,
    QSizePolicy, QSpacerItem, QMenu, QGraphicsPolygonItem, QSpinBox,
    QScrollArea,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QRectF, QPointF, QTimer
from PySide6.QtGui import QPainter, QPainterPath, QColor, QFont, QBrush, QPen, QPixmap, QImage, QPolygonF, QAction

APP_VERSION = "0.4.0"

# Globale Thread-Registry: hält Referenzen auf aktive QThread/Worker-Paare,
# damit sie nicht vorzeitig garbage-collected werden.
_GLOBAL_ACTIVE_THREADS: list[tuple] = []
STYLE_DIR = Path(__file__).parent / "styles"
RESOURCE_DIR = Path(__file__).parent / "resources"

from database import init_db, engine, AudioTrack, VideoClip, TimelineEntry, Beatgrid, WaveformData, ClipAnchor
from sqlalchemy.orm import Session as DBSession
import json as _json
from services.ingest_service import (
    ingest_audio, ingest_video, get_all_media, get_all_audio, get_all_video,
    delete_all_media, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS,
)
import os
from services.audio_service import AudioAnalyzer
from services.video_service import VideoAnalyzer
from services.pacing_service import (
    PacingSettings, calculate_cut_points, CutPoint, auto_edit_to_beats,
    AdvancedPacingSettings, auto_edit_phase3, TimelineSegment,
    generate_keyframe_strings_for_project,
)
from services.export_service import export_timeline, get_timeline_summary
from services.timeline_service import TimelineService, PB_NS
from ui.chat_dock import ChatDock
from ui.waveform_item import WaveformGraphicsItem
from ui.widgets.stem_workspace import StemWorkspace
from services.stem_player import StemPlayer


# ======================================================================
# Phase 5: Zentrale Task-Engine (besitzt Threads + Worker)
# ======================================================================

class TaskInfo:
    """Beschreibt einen laufenden Hintergrund-Task."""
    def __init__(self, task_id: str, name: str, description: str = ""):
        self.task_id = task_id
        self.name = name
        self.description = description
        self.status = "running"
        self.progress = 0
        self.total = 100
        self.message = ""
        self.start_time = time.time()
        # Referenzen auf Thread und Worker — GC-Schutz!
        self.thread: QThread | None = None
        self.worker: QObject | None = None

    @property
    def elapsed(self) -> float:
        return round(time.time() - self.start_time, 1)


class GlobalTaskManager(QObject):
    """Zentrale Task-Engine: Erstellt, verwaltet und besitzt ALLE
    Hintergrund-Threads und Worker. Singleton.

    Jeder Hintergrund-Job MUSS über start_task() laufen.
    Das TaskManagerDock hört ausschliesslich auf diese Signale.

    CROSS-THREAD SAFE: start_task() kann aus jedem Thread aufgerufen
    werden. Worker-Ownership wird korrekt an den Main-Thread uebergeben,
    bevor QThread-Erstellung und Signal-Verbindungen stattfinden.

    COMMAND PATTERN: Agenten-Tools senden nur noch
    agent_command_signal.emit(action_name, kwargs). Der Main-Thread
    instanziiert Worker und QThread selbst — keine Qt-Objekte im
    Agent-Thread!
    """
    task_added = Signal(str)
    task_updated = Signal(str)
    task_finished = Signal(str)

    # Cross-Thread Request: task_id, name, description, worker, on_finish, on_error
    _cross_thread_request = Signal(str, str, str, object, object, object)

    # ── Command Pattern: Agenten emittieren nur noch dieses Signal ──
    agent_command_signal = Signal(str, dict)  # action_name, kwargs

    _instance: "GlobalTaskManager | None" = None

    @classmethod
    def instance(cls) -> "GlobalTaskManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__(QApplication.instance())
        self._tasks: dict[str, TaskInfo] = {}
        self._counter = 0
        # Cross-Thread-Signal: QueuedConnection erzwingt Ausfuehrung im Main-Thread
        self._cross_thread_request.connect(
            self._start_in_main_thread, Qt.ConnectionType.QueuedConnection
        )
        # Command Pattern: QueuedConnection → Main-Thread instanziiert Worker
        self.agent_command_signal.connect(
            self._build_and_execute_task, Qt.ConnectionType.QueuedConnection
        )

    # ------------------------------------------------------------------
    # Command Pattern: Worker-Registry + Main-Thread Factory
    # ------------------------------------------------------------------

    # Registry: action_name → (WorkerClass, task_display_name_template, kwargs→worker_kwargs mapper)
    _WORKER_REGISTRY: dict[str, tuple] = {}

    @classmethod
    def register_worker(cls, action_name: str, worker_class, display_name: str,
                        mapper=None):
        """Registriert eine Worker-Klasse fuer das Command Pattern.

        Args:
            action_name: Eindeutiger Name (z.B. 'separate_stems').
            worker_class: QObject mit run() und finished-Signal.
            display_name: Template fuer Task-Anzeige, darf {kwargs} nutzen.
            mapper: Optional. Funktion(kwargs) → dict mit Worker-Konstruktor-Kwargs.
                    Default: kwargs werden 1:1 weitergereicht.
        """
        cls._WORKER_REGISTRY[action_name] = (worker_class, display_name, mapper)

    def _build_and_execute_task(self, action_name: str, kwargs: dict):
        """Laeuft IMMER im Main-Thread (via QueuedConnection).

        Holt die Worker-Klasse aus der Registry, instanziiert Worker + QThread,
        fuehrt moveToThread aus, verbindet Signale und startet den Thread.
        """
        entry = self._WORKER_REGISTRY.get(action_name)
        if entry is None:
            logging.error(
                "[CommandPattern] Unbekannte Action '%s' — kein Worker registriert. "
                "kwargs=%s", action_name, kwargs
            )
            return

        worker_class, display_template, mapper = entry

        # Worker-kwargs vorbereiten
        worker_kwargs = mapper(kwargs) if mapper else kwargs

        # Display-Name
        try:
            display_name = display_template.format(**kwargs)
        except (KeyError, IndexError):
            display_name = f"{action_name} ({kwargs})"

        logging.info(
            "[CommandPattern] Main-Thread baut Worker: %s → %s",
            action_name, display_name,
        )

        # 1. Worker im Main-Thread instanziieren
        worker = worker_class(**worker_kwargs)

        # 2. start_task kuemmert sich um QThread, moveToThread, Signale, Start
        self.start_task(
            name=display_name,
            worker=worker,
            description=f"Command Pattern: {action_name}",
        )

        # 3. TaskManagerDock erzwingen
        app = QApplication.instance()
        if app:
            for w in app.topLevelWidgets():
                dock = w.findChild(QDockWidget, "task_manager_dock")
                if dock:
                    dock.show()
                    break

    # ------------------------------------------------------------------
    # Neues API: Worker + Thread in einem Aufruf starten
    # THREAD-SAFE: Kann aus Main-Thread UND Background-Threads aufgerufen werden
    # ------------------------------------------------------------------

    def start_task(
        self,
        name: str,
        worker: QObject,
        description: str = "",
        on_finish=None,
        on_error=None,
    ) -> "TaskInfo | str":
        """Erstellt Task, Thread, moveToThread, startet alles.

        Der Worker MUSS eine run()-Methode und ein finished-Signal haben.
        Optional: progress(int, str), error-Signal.

        Returns:
            - TaskInfo wenn aus Main-Thread aufgerufen (sofortige Ausfuehrung)
            - task_id (str) wenn aus Background-Thread (asynchrone Ausfuehrung)
        """
        task_id = f"task_{uuid.uuid4().hex[:12]}"

        app = QApplication.instance()
        is_bg_thread = app is not None and QThread.currentThread() != app.thread()

        if is_bg_thread:
            # ============================================================
            # CRITICAL FIX: Cross-Thread Task Routing
            # Worker wurde im BG-Thread erstellt → Ownership an Main-Thread
            # uebergeben BEVOR wir das Signal senden.
            # ============================================================
            logging.info(
                "[TaskEngine] Cross-Thread-Request: %s (task_id=%s) — "
                "routing to main thread", name, task_id
            )
            worker.moveToThread(app.thread())
            self._cross_thread_request.emit(
                task_id, name, description, worker, on_finish, on_error
            )
            return task_id
        else:
            # Main-Thread: direkt ausfuehren
            return self._start_in_main_thread(
                task_id, name, description, worker, on_finish, on_error
            )

    def _start_in_main_thread(
        self,
        task_id: str,
        name: str,
        description: str,
        worker: QObject,
        on_finish=None,
        on_error=None,
    ) -> TaskInfo:
        """Tatsaechliche Thread-Erstellung — laeuft IMMER im Main-Thread.

        Wird direkt aufgerufen (Main-Thread) oder via QueuedConnection
        (Cross-Thread-Signal).
        """
        task = TaskInfo(task_id, name, description)

        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        # Task-ID am Worker speichern fuer Cancel-Lookup
        worker.task_id = task_id

        # Progress-Signal → update_task (falls Worker eins hat)
        if hasattr(worker, "progress"):
            worker.progress.connect(
                lambda pct, msg, _tid=task_id: self.update_task(_tid, pct, message=msg)
            )

        # Finish-Guard: skip on_finish wenn Worker im Error-Pfad ist
        if on_finish:
            def _guarded_finish(*args, _w=worker, _cb=on_finish):
                if not getattr(_w, '_errored', False):
                    _cb(*args)
            worker.finished.connect(_guarded_finish)

        # Error-Signal: Fallback-Logger immer verbinden (stille Fehler verhindern).
        # Verbindet einen Default-Handler, der den Fehler loggt und den Task
        # als "error" markiert — auch wenn kein on_error-Callback uebergeben wurde.
        def _default_error_handler(*args, _tid=task_id, _name=name, _tm=self):
            err_msg = str(args[-1]) if args else "Unbekannter Fehler"
            logging.error(
                "[TaskEngine] Worker-Fehler '%s' (task_id=%s): %s",
                _name, _tid, err_msg,
            )
            _tm.finish_task(_tid, status="error", message=err_msg)
        worker.error.connect(_default_error_handler)
        if on_error:
            worker.error.connect(on_error)

        # Thread-Lifecycle: finished → quit → cleanup
        worker.finished.connect(thread.quit)
        thread.finished.connect(lambda _tid=task_id: self._on_thread_done(_tid))

        # Referenzen halten (GC-Schutz)
        task.thread = thread
        task.worker = worker
        self._tasks[task_id] = task

        self.task_added.emit(task_id)

        # TaskManagerDock sichtbar machen (falls vorhanden)
        app = QApplication.instance()
        if app:
            for w in app.topLevelWidgets():
                dock = w.findChild(QDockWidget, "task_manager_dock")
                if dock:
                    dock.show()
                    break

        thread.start()
        logging.info("[TaskEngine] Gestartet: %s (task_id=%s)", name, task_id)
        return task

    # ------------------------------------------------------------------
    # Legacy-kompatibles API (fuer register_actions.py etc.)
    # ------------------------------------------------------------------

    def create_task(self, name: str, description: str = "") -> TaskInfo:
        """Erstellt nur Metadaten-Task (ohne Thread).
        Fuer Aktionen die keinen Worker haben (z.B. synchrone Calls).
        """
        self._counter += 1
        task_id = f"task_{self._counter}"
        task = TaskInfo(task_id, name, description)
        self._tasks[task_id] = task
        self.task_added.emit(task_id)
        return task

    def update_task(self, task_id: str, progress: int = 0, total: int = 100,
                    message: str = ""):
        if task_id in self._tasks:
            t = self._tasks[task_id]
            t.progress = progress
            t.total = total
            t.message = message
            self.task_updated.emit(task_id)

    def finish_task(self, task_id: str, status: str = "finished", message: str = ""):
        if task_id in self._tasks:
            t = self._tasks[task_id]
            t.status = status
            t.message = message
            self.task_finished.emit(task_id)

    def cancel_task(self, task_id: str):
        """Bricht einen laufenden Task ab."""
        task = self._tasks.get(task_id)
        if not task or task.status != "running":
            return
        worker = task.worker
        if worker and hasattr(worker, "cancel"):
            worker.cancel()
        thread = task.thread
        if thread and thread.isRunning():
            thread.quit()
            if not thread.wait(2000):
                thread.terminate()
        self.finish_task(task_id, "cancelled", "Abgebrochen")
        logging.info("[TaskEngine] Abgebrochen: %s", task_id)

    def get_task(self, task_id: str) -> TaskInfo | None:
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[TaskInfo]:
        return list(self._tasks.values())

    def clear_finished(self):
        to_remove = []
        for k, v in self._tasks.items():
            if v.status != "running":
                to_remove.append(k)
        for k in to_remove:
            task = self._tasks.pop(k)
            if task.worker:
                task.worker.deleteLater()
            if task.thread:
                task.thread.deleteLater()

    # ------------------------------------------------------------------
    # Interner Cleanup
    # ------------------------------------------------------------------

    def _on_thread_done(self, task_id: str):
        """Wird aufgerufen wenn ein Thread fertig ist."""
        task = self._tasks.get(task_id)
        if task and task.status == "running":
            self.finish_task(task_id, "finished", "Fertig")


# Singleton-Instanz: Wird in main() an QApplication verankert.
# Zugriff ausschliesslich ueber QApplication.instance().task_manager
task_manager = None  # Lazy — wird in main() gesetzt


# ======================================================================
# Background Workers
# ======================================================================

class CancellableMixin:
    """Mixin for workers: adds a _cancelled flag checked via should_stop()."""
    _cancelled = False

    def cancel(self):
        self._cancelled = True

    def should_stop(self) -> bool:
        return self._cancelled


class AnalysisWorker(QObject, CancellableMixin):
    finished = Signal(int, dict)
    error = Signal(int, str)
    started = Signal(int, str)
    progress = Signal(int, str)

    def __init__(self, track_id: int, title: str):
        super().__init__()
        self._cancelled = False
        self.track_id = track_id
        self.title = title
        self.analyzer = AudioAnalyzer()

    def run(self):
        _ok = False
        self.started.emit(self.track_id, self.title)
        try:
            # Phase 1: Grundanalyse (BPM, Duration, Energy via librosa)
            self.progress.emit(10, "Grundanalyse (librosa)...")
            result = self.analyzer.analyze_and_store(self.track_id)

            # Phase 2: KI Beat-Analyse (Beatgrid mit Downbeats + Energy)
            # BeatAnalysisService ist der alleinige Beatgrid-Writer.
            if not self.should_stop():
                try:
                    self.progress.emit(50, "KI Beat-Analyse (beat_this)...")
                    from services.beat_analysis_service import BeatAnalysisService
                    beat_svc = BeatAnalysisService()
                    beat_result = beat_svc.analyze_and_store(self.track_id)
                    result["beat_positions"] = beat_result.get("beats", [])
                    result["downbeats"] = beat_result.get("downbeats", [])
                    self.progress.emit(90, "Beat-Analyse fertig")
                except Exception as e:
                    # Beat-Analyse ist optional — Grundanalyse reicht für den Betrieb
                    logging.warning("BeatAnalysis optional fehlgeschlagen: %s", e)
                    self.progress.emit(90, f"Beat-Analyse übersprungen: {e}")

            self.progress.emit(100, "Analyse komplett")
            self.finished.emit(self.track_id, result)
            _ok = True
        except Exception as e:
            logging.error("AnalysisWorker[%s] crashed: %s\n%s",
                          self.track_id, e, traceback.format_exc())
            self._errored = True
            self.error.emit(self.track_id, str(e))
        finally:
            if not _ok:
                self.finished.emit(self.track_id, {})


class VideoAnalysisWorker(QObject, CancellableMixin):
    finished = Signal(int, dict)
    error = Signal(int, str)
    started = Signal(int, str)
    progress = Signal(int, str)   # Echte Qt-Signale statt print()

    def __init__(self, clip_id: int, title: str):
        super().__init__()
        self.clip_id = clip_id
        self.title = title
        self.analyzer = VideoAnalyzer()

    def run(self):
        _ok = False
        self.started.emit(self.clip_id, self.title)
        self.progress.emit(0, f"Video-Analyse: {self.title}")
        try:
            self.progress.emit(10, f"ffprobe + Proxy fuer {self.title}...")
            result = self.analyzer.analyze_and_store(self.clip_id)
            self.progress.emit(100, f"Analyse fertig: {self.title}")
            self.finished.emit(self.clip_id, result)
            _ok = True
        except Exception as e:
            logging.error("VideoAnalysisWorker[%s] crashed: %s\n%s",
                          self.clip_id, e, traceback.format_exc())
            self._errored = True
            self.error.emit(self.clip_id, str(e))
        finally:
            if not _ok:
                self.finished.emit(self.clip_id, {})


class StemSeparationWorker(QObject, CancellableMixin):
    finished = Signal(int, dict)
    error = Signal(int, str)
    progress = Signal(int, str)

    def __init__(self, track_id: int):
        super().__init__()
        self.track_id = track_id

    def run(self):
        _ok = False
        try:
            from services.ai_audio_service import StemSeparator
            separator = StemSeparator()
            result = separator.separate_and_store(
                self.track_id,
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
            )
            self.finished.emit(self.track_id, result)
            _ok = True
        except Exception as e:
            logging.error("StemSeparationWorker[%s] crashed: %s\n%s",
                          self.track_id, e, traceback.format_exc())
            self._errored = True
            self.error.emit(self.track_id, str(e))
        finally:
            if not _ok:
                self.finished.emit(self.track_id, {})


class AutoDuckingWorker(QObject, CancellableMixin):
    finished = Signal(str)
    error = Signal(str)
    progress = Signal(int, str)

    def __init__(self, music_path: str, voice_path: str, output_path: str):
        super().__init__()
        self.music_path = music_path
        self.voice_path = voice_path
        self.output_path = output_path

    def run(self):
        _ok = False
        try:
            from services.ai_audio_service import AutoDucker
            ducker = AutoDucker()
            result = ducker.create_ducked_audio(
                self.music_path, self.voice_path, self.output_path,
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
            )
            self.finished.emit(result)
            _ok = True
        except Exception as e:
            logging.error("AutoDuckingWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(str(e))
        finally:
            if not _ok:
                self.finished.emit("")


class ExportWorker(QObject, CancellableMixin):
    finished = Signal(str)
    error = Signal(str)
    progress = Signal(int, str)

    def __init__(self, project_id: int, output_name: str,
                 resolution: str = "1920x1080", fps: float = 30.0):
        super().__init__()
        self.project_id = project_id
        self.output_name = output_name
        self.resolution = resolution
        self.fps = fps

    def run(self):
        _ok = False
        try:
            path = export_timeline(
                project_id=self.project_id,
                output_name=self.output_name,
                resolution=self.resolution,
                fps=self.fps,
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
            )
            self.finished.emit(path)
            _ok = True
        except Exception as e:
            logging.error("ExportWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(str(e))
        finally:
            if not _ok:
                self.finished.emit("")


class FrameExtractWorker(QObject):
    frame_ready = Signal(bytes, int, int)
    error = Signal(str)

    def __init__(self, file_path: str, time_sec: float, width: int = 320,
                 height: int = 180, vf_extra: str = ""):
        super().__init__()
        self.file_path = file_path
        self.time_sec = time_sec
        self.width = width
        self.height = height
        self.vf_extra = vf_extra

    def run(self):
        try:
            vf = f"scale={self.width}:{self.height}"
            if self.vf_extra:
                vf = f"{self.vf_extra},{vf}"
            cmd = [
                "ffmpeg", "-ss", str(self.time_sec), "-i", self.file_path,
                "-frames:v", "1", "-vf", vf,
                "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-v", "quiet", "-y", "pipe:1"
            ]
            result = subprocess.run(
                cmd, capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            expected = self.width * self.height * 3
            if result.returncode == 0 and len(result.stdout) == expected:
                self.frame_ready.emit(result.stdout, self.width, self.height)
            else:
                stderr_hint = result.stderr[:200].decode(errors="replace") if result.stderr else ""
                self.error.emit(f"Frame @ {self.time_sec:.1f}s nicht verfuegbar: {stderr_hint}")
        except Exception as e:
            logging.error("FrameExtractWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(str(e))


class AutoEditWorker(QObject, CancellableMixin):
    """Phase 3: Auto-Edit Worker mit AdvancedPacingSettings + OTIO."""
    finished = Signal(list, list)   # (segments_as_dicts, cut_points_as_dicts)
    error = Signal(str)

    def __init__(self, audio_id: int, video_ids: list[int],
                 settings: AdvancedPacingSettings):
        super().__init__()
        self.audio_id = audio_id
        self.video_ids = video_ids
        self.settings = settings

    def run(self):
        _ok = False
        try:
            segments, cut_points = auto_edit_phase3(
                self.audio_id, self.video_ids, self.settings,
            )
            # Serialize for signal transport
            seg_dicts = [
                {
                    "video_id": s.video_id, "video_path": s.video_path,
                    "start": s.start, "end": s.end,
                    "source_start": s.source_start, "source_end": s.source_end,
                    "is_anchor": s.is_anchor, "scene_id": s.scene_id,
                }
                for s in segments
            ]
            cp_dicts = [
                {"time": c.time, "source": c.source, "strength": c.strength}
                for c in cut_points
            ]
            self.finished.emit(seg_dicts, cp_dicts)
            _ok = True
        except Exception as e:
            logging.error("AutoEditWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(str(e))
        finally:
            if not _ok:
                self.finished.emit([], [])


class WaveformAnalysisWorker(QObject, CancellableMixin):
    """Background Worker: Rekordbox-Style Frequenzanalyse + Beatgrid."""
    finished = Signal(int, dict)   # track_id, result
    error = Signal(int, str)       # track_id, error_msg
    progress = Signal(int, str)    # percent, message

    def __init__(self, track_id: int):
        super().__init__()
        self.track_id = track_id

    def run(self):
        _ok = False
        try:
            from services.ai_audio_service import FrequencyAnalyzer
            analyzer = FrequencyAnalyzer()
            result = analyzer.analyze_and_store(
                self.track_id,
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
            )
            self.finished.emit(self.track_id, result)
            _ok = True
        except Exception as e:
            logging.error("WaveformAnalysisWorker[%s] crashed: %s\n%s",
                          self.track_id, e, traceback.format_exc())
            self._errored = True
            self.error.emit(self.track_id, str(e))
        finally:
            if not _ok:
                self.finished.emit(self.track_id, {})


# ======================================================================
# Phase 2: Video Analysis Pipeline Worker (SEKTOR 1)
# ======================================================================

class VideoAnalysisPipelineWorker(QObject, CancellableMixin):
    """Führt die 3-Schritt Video-Analyse-Pipeline im Hintergrund aus.

    Unterstützt Batch-Verarbeitung: Nimmt eine Liste von (clip_id, video_path)
    und arbeitet diese STRIKT SEQUENZIELL ab (6GB VRAM Limit).
    """
    finished = Signal(int, dict)   # last_clip_id, batch_result_dict
    error = Signal(int, str)       # clip_id, error_msg
    progress = Signal(int, str)    # percent, message

    def __init__(self, clip_id: int = 0, video_path: str = "",
                 batch: list | None = None):
        """Args:
            clip_id / video_path: Einzelnes Video (Rückwärtskompatibel).
            batch: Liste von (clip_id, video_path, title) Tupeln für Batch-Modus.
        """
        super().__init__()
        self._cancelled = False
        if batch:
            self._batch = batch
        else:
            self._batch = [(clip_id, video_path, "")]

    def run(self):
        _ok = False
        total_videos = len(self._batch)
        last_clip_id = self._batch[-1][0]
        try:
            from services.video_analysis_service import run_full_pipeline

            total_scenes = 0
            total_embeddings = 0
            idx = 0

            for idx, (clip_id, video_path, title) in enumerate(self._batch, start=1):
                if self.should_stop():
                    break

                label = title or Path(video_path).stem
                batch_base_pct = int((idx - 1) / total_videos * 100)
                batch_range = int(100 / total_videos)
                self.progress.emit(
                    batch_base_pct,
                    f"Video {idx}/{total_videos}: '{label}' wird analysiert..."
                )

                try:
                    result = run_full_pipeline(
                        video_path=video_path,
                        video_clip_id=clip_id,
                        progress_cb=lambda pct, msg, _base=batch_base_pct, _range=batch_range, _i=idx, _tv=total_videos: (
                            self.progress.emit(
                                min(99, _base + int(pct / 100 * _range)),
                                f"[{_i}/{_tv}] {msg}"
                            )
                        ),
                        should_stop=self.should_stop,
                    )
                    total_scenes += len(result.scenes)
                    total_embeddings += result.embeddings_stored

                except Exception as e:
                    logging.error("VideoAnalysisPipelineWorker[%s] video %d/%d '%s' crashed: %s\n%s",
                                  clip_id, idx, total_videos, label, e, traceback.format_exc())
                    self._errored = True
                    self.error.emit(clip_id, f"Video {idx}/{total_videos} '{label}': {e}")
                    return

            self.finished.emit(last_clip_id, {
                "scenes": total_scenes,
                "embeddings": total_embeddings,
                "videos_processed": idx if self.should_stop() else total_videos,
            })
            _ok = True
        except Exception as e:
            logging.error("VideoAnalysisPipelineWorker crashed (outer): %s\n%s",
                          e, traceback.format_exc())
            self._errored = True
            self.error.emit(last_clip_id, str(e))
        finally:
            if not _ok:
                self.finished.emit(last_clip_id, {})


# ======================================================================
# Phase 2: Proxy Creation Worker (SEKTOR 2)
# ======================================================================

class ProxyCreationWorker(QObject, CancellableMixin):
    """Erstellt NVENC 540p Edit-Proxy für ein Video."""
    finished = Signal(int, str)    # clip_id, proxy_path
    error = Signal(int, str)       # clip_id, error_msg
    progress = Signal(int, str)    # percent, status_text

    def __init__(self, clip_id: int, video_path: str):
        super().__init__()
        self._cancelled = False
        self.clip_id = clip_id
        self.video_path = video_path

    def run(self):
        _ok = False
        try:
            from services.convert_service import convert
            proxy_path = convert(
                self.video_path,
                preset_name="edit_proxy",
                progress_cb=lambda pct, msg: self.progress.emit(pct, msg),
            )
            # Proxy-Pfad in SQLite speichern
            with DBSession(engine) as session:
                clip = session.get(VideoClip, self.clip_id)
                if clip:
                    clip.proxy_path = proxy_path
                    session.commit()
            self.finished.emit(self.clip_id, proxy_path)
            _ok = True
        except Exception as e:
            logging.error("ProxyCreationWorker[%s] crashed: %s\n%s",
                          self.clip_id, e, traceback.format_exc())
            self._errored = True
            self.error.emit(self.clip_id, str(e))
        finally:
            if not _ok:
                self.finished.emit(self.clip_id, "")


# ======================================================================
# Phase 2: Semantic Search Worker (SEKTOR 3)
# ======================================================================

class SemanticSearchWorker(QObject):
    """SigLIP Text-zu-Video Suche im Hintergrund."""
    finished = Signal(list)   # list of result dicts
    error = Signal(str)

    def __init__(self, query: str, top_k: int = 20):
        super().__init__()
        self.query = query
        self.top_k = top_k

    def run(self):
        _ok = False
        try:
            from services.video_analysis_service import search_videos_by_text
            results = search_videos_by_text(self.query, top_k=self.top_k)
            self.finished.emit(results)
            _ok = True
        except Exception as e:
            logging.error("SemanticSearchWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(str(e))
        finally:
            if not _ok:
                self.finished.emit([])


# ======================================================================
# Batch Convert Worker (CRIT-02 Fix: Main-Thread-Blocking entfernt)
# ======================================================================

class BatchConvertWorker(QObject, CancellableMixin):
    """Konvertiert alle Videos im Hintergrund-Thread statt auf dem Main-Thread."""
    finished = Signal(int, int)      # (converted_count, total_count)
    error = Signal(str)
    progress = Signal(int, str)      # (percent, message)

    def __init__(self, videos: list, resolution: str, fps: str, vcodec: str, ext: str):
        super().__init__()
        self._cancelled = False
        self.videos = videos
        self.resolution = resolution
        self.fps = fps
        self.vcodec = vcodec
        self.ext = ext

    def run(self):
        _ok = False
        w_res, h_res = self.resolution.split("x")
        total = len(self.videos)
        converted = 0
        try:
            for i, v in enumerate(self.videos):
                if self.should_stop():
                    break

                src = v["file_path"]
                stem = Path(src).stem
                out_dir = Path(src).parent / "converted"
                out_dir.mkdir(exist_ok=True)
                dst = str(out_dir / f"{stem}_std{self.ext}")

                self.progress.emit(
                    int((i + 1) / total * 100),
                    f"[Convert] {i+1}/{total}: {Path(src).name} -> {self.resolution} @ {self.fps}fps"
                )

                cmd = [
                    "ffmpeg", "-y", "-i", src,
                    "-vf", f"scale={w_res}:{h_res}:force_original_aspect_ratio=decrease,"
                           f"pad={w_res}:{h_res}:(ow-iw)/2:(oh-ih)/2",
                    "-r", self.fps,
                    "-c:v", self.vcodec,
                    "-c:a", "aac",
                    "-preset", "medium",
                    "-v", "quiet",
                    dst,
                ]
                try:
                    result = subprocess.run(
                        cmd, capture_output=True, timeout=600,
                        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    )
                    if result.returncode == 0:
                        converted += 1
                        self.progress.emit(int((i + 1) / total * 100), f"  OK: {dst}")
                    else:
                        stderr = result.stderr.decode(errors="replace")[:200]
                        self.progress.emit(int((i + 1) / total * 100), f"  FEHLER: {stderr}")
                except subprocess.TimeoutExpired:
                    self.progress.emit(int((i + 1) / total * 100), f"  TIMEOUT: {Path(src).name}")
                except FileNotFoundError:
                    self._errored = True
                    self.error.emit("ffmpeg nicht gefunden!")
                    return

            self.finished.emit(converted, total)
            _ok = True
        except Exception as e:
            logging.error("BatchConvertWorker crashed: %s\n%s", e, traceback.format_exc())
            self._errored = True
            self.error.emit(str(e))
        finally:
            if not _ok:
                self.finished.emit(0, 0)


class DummyProgressWorker(QObject, CancellableMixin):
    """Test-Worker: Zaehlt 10 Sekunden hoch fuer UI-Test der Task-Engine."""
    finished = Signal(int, int)   # (done_steps, total_steps)
    error = Signal(str)
    progress = Signal(int, str)   # (percent, message)

    def __init__(self, steps: int = 10, interval_ms: int = 1000):
        super().__init__()
        self._cancelled = False
        self.steps = steps
        self.interval_s = interval_ms / 1000.0

    def run(self):
        _ok = False
        try:
            for i in range(1, self.steps + 1):
                if self.should_stop():
                    self.progress.emit(0, "Abgebrochen")
                    break
                pct = int(100 * i / self.steps)
                self.progress.emit(pct, f"Schritt {i}/{self.steps}")
                import time as _t
                _t.sleep(self.interval_s)
            self.finished.emit(self.steps, self.steps)
            _ok = True
        except Exception as e:
            self._errored = True
            self.error.emit(str(e))
        finally:
            if not _ok:
                self.finished.emit(0, 0)


# ======================================================================
# Command Pattern: Worker-Registry Registrierungen
# Agenten-Tools emittieren nur agent_command_signal → Main-Thread baut Worker
# ======================================================================

GlobalTaskManager.register_worker(
    "separate_stems",
    StemSeparationWorker,
    "Stem-Separation #{track_id}",
    mapper=lambda kw: {"track_id": kw["track_id"]},
)

GlobalTaskManager.register_worker(
    "analyze_audio",
    AnalysisWorker,
    "Audio-Analyse #{track_id}",
    mapper=lambda kw: {"track_id": kw["track_id"], "title": kw.get("title", f"Track #{kw['track_id']}")},
)

GlobalTaskManager.register_worker(
    "analyze_video",
    VideoAnalysisWorker,
    "Video-Analyse #{clip_id}",
    mapper=lambda kw: {"clip_id": kw["clip_id"], "title": kw.get("title", f"Clip #{kw['clip_id']}")},
)

GlobalTaskManager.register_worker(
    "create_proxy",
    ProxyCreationWorker,
    "Proxy #{clip_id}",
    mapper=lambda kw: {"clip_id": kw["clip_id"], "video_path": kw["video_path"]},
)

GlobalTaskManager.register_worker(
    "auto_edit",
    AutoEditWorker,
    "Auto-Edit",
    mapper=lambda kw: {
        "audio_id": kw["audio_id"],
        "video_ids": kw["video_ids"],
        "settings": kw.get("settings") or AdvancedPacingSettings(),
    },
)

GlobalTaskManager.register_worker(
    "export_timeline",
    ExportWorker,
    "Export: {output_name}",
    mapper=lambda kw: {
        "project_id": kw.get("project_id", 1),
        "output_name": kw.get("output_name", "output.mp4"),
        "resolution": kw.get("resolution", "1920x1080"),
        "fps": kw.get("fps", 30),
    },
)

GlobalTaskManager.register_worker(
    "teste_ladebalken",
    DummyProgressWorker,
    "Test-Ladebalken ({steps}s)",
    mapper=lambda kw: {"steps": kw.get("steps", 10), "interval_ms": kw.get("interval_ms", 1000)},
)


# ======================================================================
# Draggable Timeline Clip (QGraphicsRectItem)
# ======================================================================

class AnchorMarkerItem(QGraphicsPolygonItem):
    """Visueller Anker-Marker: Rotes Dreieck + vertikale Linie auf dem Clip."""

    def __init__(self, x_offset: float, height: float, anchor_id: int, parent=None):
        # Dreieck-Polygon (Pfeil nach unten)
        triangle = QPolygonF([
            QPointF(x_offset - 5, 0),
            QPointF(x_offset + 5, 0),
            QPointF(x_offset, 8),
        ])
        super().__init__(triangle, parent)
        self.anchor_id = anchor_id
        self.setBrush(QBrush(QColor(255, 50, 50, 230)))
        self.setPen(QPen(QColor(255, 100, 100), 1))
        self.setZValue(10)

        # Vertikale rote Linie durch den ganzen Clip
        self._line = QGraphicsLineItem(x_offset, 8, x_offset, height, parent)
        self._line.setPen(QPen(QColor(255, 50, 50, 180), 1, Qt.PenStyle.DashLine))
        self._line.setZValue(9)
        self.line_item = self._line

    def remove_from_scene(self):
        """Entfernt Dreieck und Linie."""
        if self.scene():
            self.scene().removeItem(self._line)
            self.scene().removeItem(self)


class TimelineClipItem(QGraphicsRectItem):
    # Audio-Clips: halbtransparent, damit Rekordbox-Wellenform durchscheint
    AUDIO_COLOR = QColor(30, 60, 120, 60)
    AUDIO_COLOR_NO_WAVEFORM = QColor(70, 130, 220, 200)
    VIDEO_COLOR = QColor(230, 140, 50, 200)

    def __init__(self, entry_id: int, media_id: int, track_type: str,
                 title: str, x: float, y: float, width: float, height: float,
                 on_moved=None, has_waveform: bool = False):
        super().__init__(QRectF(0, 0, width, height))
        self.entry_id = entry_id
        self.media_id = media_id
        self.track_type = track_type
        self.on_moved = on_moved
        self._clip_width = width
        self._clip_height = height

        self.setPos(x, y)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        if track_type == "audio":
            color = self.AUDIO_COLOR if has_waveform else self.AUDIO_COLOR_NO_WAVEFORM
        else:
            color = self.VIDEO_COLOR
        self.setBrush(QBrush(color))
        self.setPen(QPen(color.darker(150), 1))
        self.setZValue(2)  # Über der Wellenform

        label = QGraphicsTextItem(title[:30], self)
        label.setDefaultTextColor(QColor(255, 255, 255))
        label.setFont(QFont("Segoe UI", 8))
        label.setPos(4, 2)

        self._track_y = y
        self._anchor_markers: list[AnchorMarkerItem] = []
        self._load_anchors()

    def _load_anchors(self):
        """Laedt bestehende Anker aus der DB und zeichnet sie."""
        with DBSession(engine) as session:
            anchors = session.query(ClipAnchor).filter_by(
                timeline_entry_id=self.entry_id
            ).all()
            for anchor in anchors:
                x_px = anchor.time_offset * PIXELS_PER_SECOND
                if 0 <= x_px <= self._clip_width:
                    marker = AnchorMarkerItem(x_px, self._clip_height, anchor.id, parent=self)
                    self._anchor_markers.append(marker)

    def add_anchor_at(self, local_x: float) -> int | None:
        """Setzt einen neuen Anker an der lokalen X-Position (in Pixeln).
        Gibt die Anchor-ID zurueck oder None bei Fehler.
        """
        time_offset = local_x / PIXELS_PER_SECOND
        if time_offset < 0:
            time_offset = 0.0

        with DBSession(engine) as session:
            anchor = ClipAnchor(
                timeline_entry_id=self.entry_id,
                time_offset=round(time_offset, 4),
            )
            session.add(anchor)
            session.commit()
            anchor_id = anchor.id

        marker = AnchorMarkerItem(local_x, self._clip_height, anchor_id, parent=self)
        self._anchor_markers.append(marker)
        return anchor_id

    def remove_all_anchors(self):
        """Entfernt alle Anker dieses Clips."""
        with DBSession(engine) as session:
            session.query(ClipAnchor).filter_by(
                timeline_entry_id=self.entry_id
            ).delete()
            session.commit()
        for m in self._anchor_markers:
            if m.line_item.parentItem():
                # Kinder werden mit Parent entfernt
                pass
        self._anchor_markers.clear()

    def get_first_anchor_time(self) -> float | None:
        """Gibt den Zeitstempel des ersten Ankers zurueck (relativ zum Clip-Start)."""
        with DBSession(engine) as session:
            anchor = session.query(ClipAnchor).filter_by(
                timeline_entry_id=self.entry_id
            ).order_by(ClipAnchor.time_offset).first()
            if anchor:
                return anchor.time_offset
        return None

    def contextMenuEvent(self, event):
        """Rechtsklick-Kontextmenue mit Anker-Optionen."""
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background: #1A1A1A; color: #E0E0E0; border: 1px solid #333; }"
            "QMenu::item:selected { background: #00B4D8; color: white; }"
        )

        # Anker setzen an Mausposition
        local_x = event.pos().x()
        time_offset = local_x / PIXELS_PER_SECOND
        set_anchor_action = menu.addAction(f"Anker setzen ({time_offset:.2f}s)")
        set_anchor_action.triggered.connect(lambda: self.add_anchor_at(local_x))

        # Alle Anker entfernen
        if self._anchor_markers:
            remove_action = menu.addAction("Alle Anker entfernen")
            remove_action.triggered.connect(self.remove_all_anchors)

        menu.addSeparator()
        info_action = menu.addAction(f"Clip: {self.track_type} | ID: {self.media_id}")
        info_action.setEnabled(False)

        menu.exec(event.screenPos())

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.GraphicsItemChange.ItemPositionChange:
            new_pos = QPointF(max(0, value.x()), self._track_y)
            return new_pos
        if change == QGraphicsRectItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.on_moved:
                self.on_moved(self.entry_id, value.x())
        return super().itemChange(change, value)


# ======================================================================
# Interactive Timeline (QGraphicsView) — Performance Optimized
# ======================================================================

PIXELS_PER_SECOND = 20
TRACK_HEIGHT = 50
AUDIO_TRACK_Y = 10
VIDEO_TRACK_Y = AUDIO_TRACK_Y + TRACK_HEIGHT + 10
CUT_MARKERS_Y = VIDEO_TRACK_Y + TRACK_HEIGHT + 10
RULER_Y = CUT_MARKERS_Y + 30


class InteractiveTimeline(QGraphicsView):
    clip_moved = Signal(int, float)

    def __init__(self, console_log=None):
        super().__init__()
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumHeight(200)
        self.setStyleSheet("background-color: #0E0E0E; border: 1px solid #1E1E1E;")
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Sektor 2: Zoom zur Mausposition (Ableton Feel)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        # Performance: Caching und Optimierung (Sektor 3)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self.setOptimizationFlags(
            QGraphicsView.OptimizationFlag.DontSavePainterState
        )
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.SmartViewportUpdate
        )

        # Sektor 3: Hardware-beschleunigtes Rendering (OpenGL)
        try:
            from PySide6.QtOpenGLWidgets import QOpenGLWidget
            self.setViewport(QOpenGLWidget())
        except (ImportError, RuntimeError):
            pass  # Fallback: Software-Rendering mit Tile-Cache

        # Panning-State
        self._panning = False
        self._pan_start = QPointF()
        self._space_held = False

        self.console_log = console_log
        self.clip_items: list[TimelineClipItem] = []
        self.cut_lines: list[QGraphicsLineItem] = []
        self.waveform_items: list[WaveformGraphicsItem] = []

        self._draw_track_backgrounds()
        self._draw_labels()

    def _draw_track_backgrounds(self):
        audio_bg = self._scene.addRect(
            QRectF(0, AUDIO_TRACK_Y, 2000, TRACK_HEIGHT),
            QPen(Qt.PenStyle.NoPen), QBrush(QColor(14, 18, 24))
        )
        audio_bg.setZValue(-10)
        video_bg = self._scene.addRect(
            QRectF(0, VIDEO_TRACK_Y, 2000, TRACK_HEIGHT),
            QPen(Qt.PenStyle.NoPen), QBrush(QColor(24, 14, 14))
        )
        video_bg.setZValue(-10)

    def _draw_labels(self):
        for label_text, y in [("A1", AUDIO_TRACK_Y), ("V1", VIDEO_TRACK_Y)]:
            txt = self._scene.addText(label_text, QFont("Segoe UI", 9, QFont.Weight.Bold))
            txt.setDefaultTextColor(QColor(90, 90, 90))
            txt.setPos(-35, y + 15)
            txt.setZValue(10)

    def load_from_db(self, project_id: int = 1):
        for item in self.clip_items:
            self._scene.removeItem(item)
        self.clip_items.clear()
        for wf in self.waveform_items:
            self._scene.removeItem(wf)
        self.waveform_items.clear()

        with DBSession(engine) as session:
            entries = (
                session.query(TimelineEntry)
                .filter_by(project_id=project_id)
                .all()
            )
            # Bug-17 Fix: Bulk-Load AudioTracks und VideoClips — verhindert N+1
            # (vorher: 1 SELECT pro Eintrag → bei 200 Auto-Edit Segmenten = 200 Queries)
            _audio_ids = [e.media_id for e in entries if e.track == "audio"]
            _video_ids = [e.media_id for e in entries if e.track == "video"]
            _audio_map = (
                {t.id: t for t in session.query(AudioTrack).filter(
                    AudioTrack.id.in_(_audio_ids)).all()}
                if _audio_ids else {}
            )
            _video_map = (
                {c.id: c for c in session.query(VideoClip).filter(
                    VideoClip.id.in_(_video_ids)).all()}
                if _video_ids else {}
            )

            for entry in entries:
                has_waveform = False
                if entry.track == "audio":
                    track = _audio_map.get(entry.media_id)
                    title = track.title if track else "?"
                    dur = track.duration if track and track.duration else 30.0
                    y = AUDIO_TRACK_Y

                    # Rekordbox Waveform laden (falls vorhanden)
                    if track and track.waveform_data:
                        has_waveform = True
                        self._load_waveform_for_track(session, track, entry, dur, y)

                elif entry.track == "video":
                    clip = _video_map.get(entry.media_id)
                    title = Path(clip.file_path).stem if clip else "?"
                    dur = clip.duration if clip and clip.duration else 10.0
                    y = VIDEO_TRACK_Y
                else:
                    continue

                width = dur * PIXELS_PER_SECOND
                x = entry.start_time * PIXELS_PER_SECOND

                item = TimelineClipItem(
                    entry_id=entry.id,
                    media_id=entry.media_id,
                    track_type=entry.track,
                    title=title,
                    x=x, y=y,
                    width=width, height=TRACK_HEIGHT,
                    on_moved=self._on_clip_moved,
                    has_waveform=has_waveform,
                )
                self._scene.addItem(item)
                self.clip_items.append(item)

        self._update_scene_rect()

    def _load_waveform_for_track(self, session, track, entry, dur, y):
        """Lädt Rekordbox-Wellenform aus DB und fügt sie zur Scene hinzu."""
        if track is None or track.waveform_data is None:
            return

        wd = track.waveform_data
        beat_json = "[]"
        if track.beatgrid and track.beatgrid.beat_positions:
            beat_json = track.beatgrid.beat_positions

        wf_item = WaveformGraphicsItem.from_db_data(
            waveform_data=wd,
            beat_positions_json=beat_json,
            pixels_per_second=PIXELS_PER_SECOND,
            height=TRACK_HEIGHT,
        )
        x = entry.start_time * PIXELS_PER_SECOND
        wf_item.setPos(x, y)
        wf_item.setZValue(1)  # Über dem Track-Background, unter dem Clip-Label
        self._scene.addItem(wf_item)
        self.waveform_items.append(wf_item)

    def add_clip(self, entry_id: int, media_id: int, track_type: str,
                 title: str, start_time: float, duration: float):
        y = AUDIO_TRACK_Y if track_type == "audio" else VIDEO_TRACK_Y
        width = duration * PIXELS_PER_SECOND
        x = start_time * PIXELS_PER_SECOND

        # Rekordbox Waveform für Audio-Clips laden
        has_waveform = False
        if track_type == "audio":
            with DBSession(engine) as session:
                track = session.get(AudioTrack, media_id)
                if track and track.waveform_data:
                    has_waveform = True
                    entry_stub = type("E", (), {"start_time": start_time})()
                    self._load_waveform_for_track(session, track, entry_stub, duration, y)

        item = TimelineClipItem(
            entry_id=entry_id, media_id=media_id, track_type=track_type,
            title=title, x=x, y=y, width=width, height=TRACK_HEIGHT,
            on_moved=self._on_clip_moved, has_waveform=has_waveform,
        )
        self._scene.addItem(item)
        self.clip_items.append(item)
        self._update_scene_rect()

    def set_cut_points(self, cuts: list[CutPoint], total_duration: float):
        for line in self.cut_lines:
            self._scene.removeItem(line)
        self.cut_lines.clear()

        color_map = {
            "beat": QColor(100, 200, 100, 180),
            "scene": QColor(255, 200, 60, 180),
            "energy": QColor(200, 100, 200, 180),
            "drum": QColor(255, 80, 80, 220),
            "anchor": QColor(255, 0, 255, 220),
        }
        for cp in cuts:
            x = cp.time * PIXELS_PER_SECOND
            color = color_map.get(cp.source, QColor(180, 180, 180))
            pen = QPen(color, 1)
            line_h = int(20 * cp.strength)
            line = self._scene.addLine(x, CUT_MARKERS_Y, x, CUT_MARKERS_Y + line_h, pen)
            line.setZValue(5)
            self.cut_lines.append(line)

        self._draw_ruler(total_duration)
        self._update_scene_rect()

    def _draw_ruler(self, total_duration: float):
        pen = QPen(QColor(80, 80, 80), 1)
        total_px = total_duration * PIXELS_PER_SECOND
        self._scene.addLine(0, RULER_Y, total_px, RULER_Y, pen)

        step = max(1.0, total_duration / 20)
        t = 0.0
        while t <= total_duration:
            x = t * PIXELS_PER_SECOND
            self._scene.addLine(x, RULER_Y - 3, x, RULER_Y + 3, pen)
            txt = self._scene.addText(f"{t:.0f}s", QFont("Segoe UI", 7))
            txt.setDefaultTextColor(QColor(80, 80, 80))
            txt.setPos(x - 10, RULER_Y + 5)
            t += step

    def _on_clip_moved(self, entry_id: int, new_x: float):
        new_start = max(0, new_x / PIXELS_PER_SECOND)
        with DBSession(engine) as session:
            entry = session.get(TimelineEntry, entry_id)
            if entry:
                old_start = entry.start_time
                entry.start_time = round(new_start, 3)
                if entry.end_time is not None:
                    delta = new_start - old_start
                    entry.end_time = round(entry.end_time + delta, 3)
                session.commit()
        self.clip_moved.emit(entry_id, new_start)

    def _update_scene_rect(self):
        r = self._scene.itemsBoundingRect()
        r.adjust(-60, -10, 200, 40)
        self._scene.setSceneRect(r)

    def wheelEvent(self, event):
        """Zoom mit Mausrad — sanfter Faktor, nur horizontal, zur Mausposition."""
        delta = event.angleDelta().y()
        if delta == 0:
            return
        # Sanfterer Zoom-Faktor (1.08 statt 1.15) für flüssigeres Gefühl
        factor = 1.08 if delta > 0 else 1.0 / 1.08
        # Begrenze Zoom-Bereich
        current_scale = self.transform().m11()
        new_scale = current_scale * factor
        if new_scale < 0.01 or new_scale > 200.0:
            return
        self.scale(factor, 1.0)

    def mousePressEvent(self, event):
        """Mittlere Maustaste oder Space+Links → Panning starten."""
        if (event.button() == Qt.MouseButton.MiddleButton or
                (self._space_held and event.button() == Qt.MouseButton.LeftButton)):
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Panning: Timeline verschieben."""
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            hs = self.horizontalScrollBar()
            vs = self.verticalScrollBar()
            hs.setValue(int(hs.value() - delta.x()))
            vs.setValue(int(vs.value() - delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Panning beenden."""
        if self._panning and (event.button() == Qt.MouseButton.MiddleButton or
                              event.button() == Qt.MouseButton.LeftButton):
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        """Space gedrückt → Panning-Modus. M → Anker setzen auf selektiertem Clip."""
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif event.key() == Qt.Key.Key_M and not event.isAutoRepeat():
            self._set_anchor_on_selected()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """Space losgelassen → Panning-Modus deaktivieren."""
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            if not self._panning:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        super().keyReleaseEvent(event)

    def _set_anchor_on_selected(self):
        """Setzt einen Anker in der Mitte des aktuell selektierten Clips (Taste M)."""
        selected = [item for item in self._scene.selectedItems()
                    if isinstance(item, TimelineClipItem)]
        if not selected:
            if self.console_log:
                self.console_log("[Anchor] Kein Clip ausgewaehlt — waehle zuerst einen Clip.")
            return
        for clip_item in selected:
            # Anker in der Clip-Mitte setzen
            mid_x = clip_item._clip_width / 2.0
            anchor_id = clip_item.add_anchor_at(mid_x)
            if self.console_log and anchor_id:
                time_offset = mid_x / PIXELS_PER_SECOND
                self.console_log(
                    f"[Anchor] Anker #{anchor_id} gesetzt auf {clip_item.track_type}-Clip "
                    f"bei {time_offset:.2f}s (Taste M)"
                )

    def sync_anchors(self) -> bool:
        """Anker synchronisieren: Verschiebt Video-Clips so, dass ihr Anker
        exakt über dem Audio-Anker liegt.

        Returns True wenn mindestens ein Sync durchgefuehrt wurde.
        """
        audio_clips = [c for c in self.clip_items if c.track_type == "audio"]
        video_clips = [c for c in self.clip_items if c.track_type == "video"]

        if not audio_clips or not video_clips:
            return False

        synced = False
        for audio_clip in audio_clips:
            audio_anchor_offset = audio_clip.get_first_anchor_time()
            if audio_anchor_offset is None:
                continue

            # Absoluter Zeitpunkt des Audio-Ankers auf der Timeline
            audio_clip_start = audio_clip.pos().x() / PIXELS_PER_SECOND
            audio_anchor_abs = audio_clip_start + audio_anchor_offset

            for video_clip in video_clips:
                video_anchor_offset = video_clip.get_first_anchor_time()
                if video_anchor_offset is None:
                    continue

                # Video-Clip verschieben: Anker soll auf audio_anchor_abs landen
                new_video_start = audio_anchor_abs - video_anchor_offset
                new_x = max(0, new_video_start * PIXELS_PER_SECOND)

                video_clip.setPos(new_x, video_clip._track_y)

                # DB aktualisieren
                with DBSession(engine) as session:
                    entry = session.get(TimelineEntry, video_clip.entry_id)
                    if entry:
                        if entry.end_time is not None:
                            duration = entry.end_time - entry.start_time
                        entry.start_time = round(new_video_start, 4)
                        if entry.end_time is not None:
                            entry.end_time = round(new_video_start + duration, 4)
                        session.commit()

                synced = True

        return synced


# ======================================================================
# Manual Pacing Curve Widget (drawable density over time)
# ======================================================================

class PacingCurveWidget(QWidget):
    """Drawable pacing density curve for manual cut-density override."""
    curve_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)
        self.setMaximumHeight(16777215)  # no max — resizable via QSplitter
        self.setToolTip(
            "Pacing-Kurve: Klicke und ziehe um die Schnitt-Dichte ueber die Zeit "
            "zu zeichnen. Oben = viele Schnitte, Unten = wenige"
        )
        self._num_samples = 200
        self._density = [0.5] * self._num_samples
        self._drawing = False
        self._total_duration = 60.0
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

    def set_duration(self, duration: float):
        self._total_duration = max(1.0, duration)
        self.update()

    def reset_curve(self):
        self._density = [0.5] * self._num_samples
        self.curve_changed.emit()
        self.update()

    def get_density_at(self, time_sec: float) -> float:
        if self._total_duration <= 0:
            return 0.5
        idx = int((time_sec / self._total_duration) * (self._num_samples - 1))
        idx = max(0, min(idx, self._num_samples - 1))
        return self._density[idx]

    def get_all_densities(self) -> list[float]:
        return list(self._density)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, QColor(10, 10, 10))

        # Subtle grid
        p.setPen(QPen(QColor(25, 25, 25), 1))
        for i in range(1, 4):
            y = int(h * i / 4)
            p.drawLine(0, y, w, y)

        # Time markers
        p.setPen(QPen(QColor(50, 50, 50), 1))
        p.setFont(QFont("Segoe UI", 7))
        if self._total_duration > 0:
            step = max(5.0, self._total_duration / 10)
            t = 0.0
            while t <= self._total_duration:
                x = int((t / self._total_duration) * w)
                p.drawLine(x, h - 8, x, h)
                p.drawText(x + 2, h - 1, f"{t:.0f}s")
                t += step

        # Build smooth point list
        points = []
        for i, d in enumerate(self._density):
            x = (i / (self._num_samples - 1)) * w
            y = h - (d * (h - 10))
            points.append((x, y))

        # Filled area under curve (smooth cubic spline)
        path = QPainterPath()
        path.moveTo(0, h)
        if points:
            path.lineTo(points[0][0], points[0][1])
            for i in range(1, len(points)):
                x0, y0 = points[i - 1]
                x1, y1 = points[i]
                cx = (x0 + x1) / 2.0
                path.cubicTo(cx, y0, cx, y1, x1, y1)
            path.lineTo(w, h)
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 180, 212, 35))
        p.drawPath(path)

        # Curve line (smooth cubic spline)
        line_path = QPainterPath()
        if points:
            line_path.moveTo(points[0][0], points[0][1])
            for i in range(1, len(points)):
                x0, y0 = points[i - 1]
                x1, y1 = points[i]
                cx = (x0 + x1) / 2.0
                line_path.cubicTo(cx, y0, cx, y1, x1, y1)
        p.setPen(QPen(QColor(0, 212, 230, 160), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(line_path)

        # Label
        p.setPen(QColor(60, 60, 60))
        p.setFont(QFont("Segoe UI", 8))
        p.drawText(4, 11, "PACING DENSITY")
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drawing = True
            self._paint_at(event.position())

    def mouseMoveEvent(self, event):
        if self._drawing:
            self._paint_at(event.position())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drawing = False
            self.curve_changed.emit()

    def _paint_at(self, pos):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return
        x_ratio = max(0.0, min(1.0, pos.x() / w))
        y_ratio = max(0.0, min(1.0, 1.0 - (pos.y() / h)))
        idx = int(x_ratio * (self._num_samples - 1))
        idx = max(0, min(idx, self._num_samples - 1))
        # Wider brush radius for organic, smooth drawing
        radius = 6
        for offset in range(-radius, radius + 1):
            j = idx + offset
            if 0 <= j < self._num_samples:
                weight = 1.0 - abs(offset) / (radius + 1.0)
                weight = weight * weight  # quadratic falloff for smoother feel
                self._density[j] = self._density[j] * (1 - weight) + y_ratio * weight
        self.update()


# ======================================================================
# Video Preview Widget
# ======================================================================

class VideoPreviewWidget(QLabel):
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
        self._extract_and_show_frame(0.0)

    def play_from(self, time_sec: float):
        if not self._current_path:
            return
        self._current_time = time_sec
        self._is_playing = True
        self._play_timer.start()

    def stop(self):
        self._play_timer.stop()
        self._is_playing = False

    def toggle_play(self):
        if self._is_playing:
            self.stop()
        else:
            self.play_from(self._current_time)

    def _advance_frame(self):
        self._current_time += 0.5
        if self._duration > 0 and self._current_time >= self._duration:
            self._current_time = 0.0
            self.stop()
            return
        self._extract_and_show_frame(self._current_time)

    def _extract_and_show_frame(self, time_sec: float, vf_extra: str = ""):
        if not self._current_path or not Path(self._current_path).exists():
            self.setText("Datei nicht gefunden")
            return
        if self._frame_thread is not None and self._frame_thread.isRunning():
            self._frame_thread.quit()
            self._frame_thread.wait(1000)

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
        _GLOBAL_ACTIVE_THREADS.append((thread, worker))
        thread.start()

    def _on_frame_thread_finished(self):
        """Cleanup nach Frame-Extraction — Referenzen freigeben."""
        # Globalen GC-Schutz aufheben
        if self._frame_thread is not None and self._frame_worker is not None:
            pair = (self._frame_thread, self._frame_worker)
            if pair in _GLOBAL_ACTIVE_THREADS:
                _GLOBAL_ACTIVE_THREADS.remove(pair)
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


# ======================================================================
# About Dialog
# ======================================================================

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About PB_studio")
        self.setFixedSize(400, 280)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel("PB_studio")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 28px; font-weight: 800; color: #00F0FF;")
        layout.addWidget(title)

        subtitle = QLabel("Director's Cockpit")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("font-size: 14px; color: #00B8D4; font-weight: 600;")
        layout.addWidget(subtitle)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background-color: #2A2A2A;")
        layout.addWidget(line)

        info = QLabel(
            f"Version {APP_VERSION}\n\n"
            "Beat-synchronisierte Video-Produktion\n"
            "mit KI-gestuetztem Pacing.\n\n"
            "Built with PySide6 + FFmpeg + Demucs + librosa"
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet("color: #707070; font-size: 12px; line-height: 1.5;")
        layout.addWidget(info)

        btn = QPushButton("Schliessen")
        btn.setObjectName("btn_accent")
        btn.setMaximumWidth(140)
        btn.setToolTip("Diesen Dialog schliessen und zur App zurueckkehren")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)


# ======================================================================
# Task Manager Widget
# ======================================================================

class TaskManagerDock(QDockWidget):
    """Verankerte Taskliste als QDockWidget am unteren Bildschirmrand.

    Zeigt alle laufenden Hintergrund-Prozesse mit echten QProgressBars an.
    Keine schwebenden Fenster — fest verankert.
    """
    cancel_requested = Signal(str)  # task_id

    def __init__(self, parent=None):
        super().__init__("TASKS", parent)
        self.setObjectName("task_manager_dock")
        self.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
        )  # Kein Schliessen, kein Schweben — fest verankert
        self.setMinimumHeight(150)
        self.setMinimumSize(400, 150)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        # Header mit Cancel-Button und Clear-Button
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_label = QLabel("HINTERGRUND-PROZESSE")
        header_label.setStyleSheet(
            "color: #00D4E6; font-size: 10px; font-weight: 700; letter-spacing: 1px;"
        )
        header_row.addWidget(header_label)
        header_row.addStretch()

        self.btn_clear = QPushButton("Fertige loeschen")
        self.btn_clear.setFixedHeight(20)
        self.btn_clear.setFixedWidth(110)
        self.btn_clear.setStyleSheet(
            "QPushButton { background: #1A1A2E; color: #707070; border: 1px solid #333; "
            "font-size: 9px; border-radius: 3px; padding: 0 6px; }"
            "QPushButton:hover { color: #FFFFFF; background: #2A2A3E; }"
        )
        self.btn_clear.setToolTip("Abgeschlossene Tasks aus der Liste entfernen")
        self.btn_clear.clicked.connect(self._clear_finished)
        header_row.addWidget(self.btn_clear)

        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_cancel.setFixedHeight(20)
        self.btn_cancel.setFixedWidth(90)
        self.btn_cancel.setStyleSheet(
            "QPushButton { background: #3A1010; color: #FF5050; border: 1px solid #FF3030; "
            "font-size: 10px; font-weight: bold; border-radius: 3px; padding: 0 6px; }"
            "QPushButton:hover { background: #FF3030; color: #FFFFFF; }"
        )
        self.btn_cancel.setToolTip("Laufenden Task abbrechen")
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        header_row.addWidget(self.btn_cancel)

        layout.addLayout(header_row)

        # Scrollbarer Bereich fuer Task-Rows mit echten QProgressBars
        self._task_container = QVBoxLayout()
        self._task_container.setSpacing(2)
        self._task_container.setContentsMargins(0, 0, 0, 0)

        task_scroll_widget = QWidget()
        task_scroll_widget.setLayout(self._task_container)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(task_scroll_widget)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(scroll, stretch=1)

        # Placeholder fuer leeren Zustand
        self._empty_label = QLabel("Keine laufenden Tasks")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            "color: #505050; font-size: 11px; font-style: italic; border: none; padding: 8px;"
        )
        self._task_container.addWidget(self._empty_label)

        self.setWidget(container)

        # Task-Tracking: task_id → (row_widget, progress_bar, status_label, name_label, time_label)
        self._task_rows: dict[str, dict] = {}

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_elapsed)
        self._timer.start()

        task_manager.task_added.connect(self._on_task_added)
        task_manager.task_updated.connect(self._on_task_updated)
        task_manager.task_finished.connect(self._on_task_finished)

    def _on_cancel_clicked(self):
        """Cancel the currently selected (or first running) task via TaskEngine."""
        for tid in self._task_rows:
            task = task_manager.get_task(tid)
            if task and task.status == "running":
                task_manager.cancel_task(tid)
                self.cancel_requested.emit(tid)
                break

    def _clear_finished(self):
        """Entfernt abgeschlossene Tasks aus der Anzeige."""
        to_remove = []
        for tid, row_data in self._task_rows.items():
            task = task_manager.get_task(tid)
            if task and task.status != "running":
                to_remove.append(tid)
        for tid in to_remove:
            row_data = self._task_rows.pop(tid)
            widget = row_data["widget"]
            self._task_container.removeWidget(widget)
            widget.deleteLater()
        task_manager.clear_finished()
        # Placeholder wieder einblenden wenn keine Tasks mehr da
        if not self._task_rows:
            self._empty_label.show()

    def _on_task_added(self, task_id: str):
        task = task_manager.get_task(task_id)
        if not task:
            return

        # Placeholder ausblenden sobald Tasks existieren
        self._empty_label.hide()

        # Neue Task-Row erstellen mit echtem QProgressBar
        row_widget = QWidget()
        row_widget.setStyleSheet(
            "QWidget { background: #0E0E14; border: 1px solid #1E1E2E; border-radius: 3px; }"
        )
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(6, 3, 6, 3)
        row_layout.setSpacing(8)

        # Task-Name
        name_label = QLabel(task.name)
        name_label.setFixedWidth(180)
        name_label.setStyleSheet("color: #C0C0C0; font-size: 10px; font-weight: 600; border: none;")
        row_layout.addWidget(name_label)

        # Status-Label
        status_label = QLabel("Running")
        status_label.setFixedWidth(70)
        status_label.setStyleSheet("color: #00E676; font-size: 10px; font-weight: bold; border: none;")
        row_layout.addWidget(status_label)

        # Echter QProgressBar
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setTextVisible(True)
        progress_bar.setFormat("%p%")
        progress_bar.setFixedHeight(16)
        progress_bar.setStyleSheet(
            "QProgressBar { background: #1A1A2E; border: 1px solid #2A2A3E; border-radius: 3px; "
            "text-align: center; color: #C0C0C0; font-size: 9px; }"
            "QProgressBar::chunk { background: qlineargradient("
            "x1:0, y1:0, x2:1, y2:0, stop:0 #00607A, stop:1 #00B4D8); border-radius: 2px; }"
        )
        row_layout.addWidget(progress_bar, stretch=1)

        # Nachricht
        msg_label = QLabel("")
        msg_label.setFixedWidth(200)
        msg_label.setStyleSheet("color: #707070; font-size: 9px; border: none;")
        row_layout.addWidget(msg_label)

        # Zeit
        time_label = QLabel("0s")
        time_label.setFixedWidth(50)
        time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        time_label.setStyleSheet("color: #505050; font-size: 9px; border: none;")
        row_layout.addWidget(time_label)

        self._task_container.addWidget(row_widget)

        self._task_rows[task_id] = {
            "widget": row_widget,
            "name_label": name_label,
            "status_label": status_label,
            "progress_bar": progress_bar,
            "msg_label": msg_label,
            "time_label": time_label,
        }

    def _on_task_updated(self, task_id: str):
        task = task_manager.get_task(task_id)
        row_data = self._task_rows.get(task_id)
        if not task or not row_data:
            return

        progress_bar = row_data["progress_bar"]
        msg_label = row_data["msg_label"]

        if task.total > 0:
            progress_bar.setRange(0, task.total)
            progress_bar.setValue(task.progress)
            progress_bar.setFormat(f"{task.progress}%")
        msg_label.setText(task.message[:40] if task.message else "")
        msg_label.setToolTip(task.message or "")

    def _on_task_finished(self, task_id: str):
        task = task_manager.get_task(task_id)
        row_data = self._task_rows.get(task_id)
        if not task or not row_data:
            return

        status_label = row_data["status_label"]
        progress_bar = row_data["progress_bar"]
        msg_label = row_data["msg_label"]
        time_label = row_data["time_label"]

        if task.status == "finished":
            status_label.setText("Fertig")
            status_label.setStyleSheet("color: #00B4D8; font-size: 10px; font-weight: bold; border: none;")
            progress_bar.setValue(progress_bar.maximum())
            progress_bar.setFormat("100%")
            progress_bar.setStyleSheet(
                "QProgressBar { background: #1A1A2E; border: 1px solid #2A2A3E; border-radius: 3px; "
                "text-align: center; color: #C0C0C0; font-size: 9px; }"
                "QProgressBar::chunk { background: #00B4D8; border-radius: 2px; }"
            )
        elif task.status == "cancelled":
            status_label.setText("Abbruch")
            status_label.setStyleSheet("color: #FFB040; font-size: 10px; font-weight: bold; border: none;")
        else:
            status_label.setText("Fehler")
            status_label.setStyleSheet("color: #FF5050; font-size: 10px; font-weight: bold; border: none;")
            progress_bar.setStyleSheet(
                "QProgressBar { background: #1A1A2E; border: 1px solid #3A1010; border-radius: 3px; "
                "text-align: center; color: #FF5050; font-size: 9px; }"
                "QProgressBar::chunk { background: #FF3030; border-radius: 2px; }"
            )

        msg_label.setText(task.message[:40] if task.message else "")
        msg_label.setToolTip(task.message or "")
        time_label.setText(f"{task.elapsed}s")

    def _update_elapsed(self):
        for task_id, row_data in self._task_rows.items():
            task = task_manager.get_task(task_id)
            if task and task.status == "running":
                row_data["time_label"].setText(f"{task.elapsed}s")


# ======================================================================
# DaVinci-Style Workspace Navigation Bar
# ======================================================================

class WorkspaceNavBar(QWidget):
    """Bottom navigation bar — DaVinci Resolve Style."""
    workspace_changed = Signal(int)

    WORKSPACE_NAMES = ["MEDIA", "EDIT", "STEMS", "CONVERT", "DELIVER"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workspace_nav")
        self.setFixedHeight(42)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addStretch()

        self._buttons: list[QPushButton] = []
        self._current_index = 0

        tooltips = [
            "MEDIA: Dateien importieren, verwalten und analysieren",
            "EDIT: Timeline bearbeiten, Clips schneiden, KI-Pacing",
            "STEMS: DAW-Ansicht mit 4 Stem-Wellenformen (Vocals, Drums, Bass, Other)",
            "CONVERT: Videos standardisieren (Aufloesung, FPS, Format)",
            "DELIVER: Finales Video exportieren und rendern",
        ]

        for i, name in enumerate(self.WORKSPACE_NAMES):
            btn = QPushButton(name)
            btn.setObjectName("workspace_btn")
            btn.setCheckable(True)
            btn.setFixedHeight(36)
            btn.setMinimumWidth(120)
            btn.setToolTip(tooltips[i])
            btn.clicked.connect(lambda checked, idx=i: self._on_click(idx))
            layout.addWidget(btn)
            self._buttons.append(btn)

        layout.addStretch()

        self._buttons[0].setChecked(True)

    def _on_click(self, index: int):
        self._current_index = index
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)
        self.workspace_changed.emit(index)

    def set_workspace(self, index: int):
        if 0 <= index < len(self._buttons):
            self._on_click(index)


# ======================================================================
# Hauptfenster — DaVinci Resolve Style
# ======================================================================

class PBWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"PB_studio v{APP_VERSION} — Director's Cockpit")
        self.resize(1500, 900)
        self._active_threads: list[QThread] = []
        self._active_workers: list[QObject] = []
        self._otio_timeline_service: TimelineService | None = None

        # Zentrales Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Top Bar (minimal) ──
        top_bar = QWidget()
        top_bar.setObjectName("top_bar")
        top_bar.setFixedHeight(36)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 0, 12, 0)

        app_title = QLabel(f"PB_studio v{APP_VERSION}")
        app_title.setStyleSheet("color: #00F0FF; font-weight: 700; font-size: 13px; background: transparent;")
        top_layout.addWidget(app_title)

        top_layout.addStretch()

        btn_about = QPushButton("About")
        btn_about.setMaximumWidth(80)
        btn_about.setFixedHeight(28)
        btn_about.setToolTip("Informationen ueber PB_studio anzeigen (Version, Technologie, Credits)")
        btn_about.clicked.connect(self._show_about)
        top_layout.addWidget(btn_about)

        main_layout.addWidget(top_bar)

        # ── Trennlinie ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #1E1E1E;")
        main_layout.addWidget(sep)

        # ── Workspace (volle Flaeche — TaskManager ist jetzt QDockWidget unten) ──
        self.workspace_stack = QStackedWidget()
        self.workspace_stack.addWidget(self._build_media_workspace())
        self.workspace_stack.addWidget(self._build_edit_workspace())
        self.workspace_stack.addWidget(self._build_stems_workspace())
        self.workspace_stack.addWidget(self._build_effects_workspace())
        self.workspace_stack.addWidget(self._build_deliver_workspace())

        main_layout.addWidget(self.workspace_stack, stretch=1)

        # ── Bottom Navigation Bar (DaVinci Style) ──
        self.nav_bar = WorkspaceNavBar()
        self.nav_bar.workspace_changed.connect(self.workspace_stack.setCurrentIndex)
        main_layout.addWidget(self.nav_bar)

        # ── Status Bar ──
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"PB_studio v{APP_VERSION} | System bereit")

        # ── Dock Widgets (fest verankert, keine schwebenden Fenster) ──
        self.setup_task_dock()
        self.setup_console()
        self.setup_chat_dock()

        self._refresh_media_table()

    def closeEvent(self, event):
        for thread in list(self._active_threads):
            thread.quit()
            if not thread.wait(3000):
                thread.terminate()
                thread.wait(1000)
        self._active_threads.clear()
        self._active_workers.clear()
        # Globale Liste beim Schließen ebenfalls leeren
        _GLOBAL_ACTIVE_THREADS.clear()
        # Stem Player aufräumen
        if hasattr(self, "stem_player"):
            self.stem_player.cleanup()
        # GPU-VRAM freigeben
        try:
            from services.model_manager import ModelManager
            ModelManager().unload()
        except Exception:
            pass
        super().closeEvent(event)

    def _show_about(self):
        dialog = AboutDialog(self)
        dialog.exec()

    # ==================================================================
    # Workspace 1: MEDIA
    # ==================================================================

    def _build_media_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(8, 8, 8, 4)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Linke Seite: Import-Aktionen ──
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(4, 4, 4, 4)

        import_group = QGroupBox("Import")
        import_layout = QVBoxLayout(import_group)

        btn_video = QPushButton("Video importieren")
        btn_video.setToolTip("Video-Dateien (MP4, MOV, AVI, MKV) importieren")
        btn_video.clicked.connect(self._import_video)
        import_layout.addWidget(btn_video)

        btn_audio = QPushButton("Audio importieren")
        btn_audio.setToolTip("Audio-Dateien (WAV, MP3, FLAC, OGG) importieren")
        btn_audio.clicked.connect(self._import_audio)
        import_layout.addWidget(btn_audio)

        btn_folder = QPushButton("Ordner importieren")
        btn_folder.setToolTip("Alle Audio- und Video-Dateien aus einem Ordner (inkl. Unterordner) importieren")
        btn_folder.clicked.connect(self._import_folder)
        import_layout.addWidget(btn_folder)

        left_layout.addWidget(import_group)

        # Verwaltung
        manage_group = QGroupBox("Verwaltung")
        manage_layout = QVBoxLayout(manage_group)

        btn_clear_all = QPushButton("Sammlung bereinigen")
        btn_clear_all.setToolTip("Alle Medien aus Datenbank und Ansicht entfernen")
        btn_clear_all.setStyleSheet("color: #FF6060; font-weight: bold;")
        btn_clear_all.clicked.connect(self._clear_all_media)
        manage_layout.addWidget(btn_clear_all)

        left_layout.addWidget(manage_group)

        # Analyse-Gruppe
        analyze_group = QGroupBox("Analyse")
        analyze_layout = QVBoxLayout(analyze_group)

        self.btn_analyze = QPushButton("Audio analysieren")
        self.btn_analyze.setToolTip("BPM, Beats und Energie-Verlauf erkennen")
        self.btn_analyze.clicked.connect(self._analyze_selected_audio)
        analyze_layout.addWidget(self.btn_analyze)

        self.btn_analyze_video = QPushButton("Video analysieren")
        self.btn_analyze_video.setToolTip("Aufloesung, FPS, Codec + Proxy erstellen")
        self.btn_analyze_video.clicked.connect(self._analyze_selected_video)
        analyze_layout.addWidget(self.btn_analyze_video)

        self.btn_video_pipeline = QPushButton("Video-Pipeline (Szenen + KI)")
        self.btn_video_pipeline.setToolTip(
            "Vollständige 3-Schritt Pipeline:\n"
            "1. Szenen-Erkennung + Motion-Analyse\n"
            "2. Keyframe-Extraktion\n"
            "3. SigLIP Embeddings → LanceDB\n\n"
            "Ermöglicht anschließend semantische Text-Suche."
        )
        self.btn_video_pipeline.setStyleSheet("font-weight: bold; color: #00D4E6;")
        self.btn_video_pipeline.clicked.connect(self._start_video_pipeline)
        analyze_layout.addWidget(self.btn_video_pipeline)

        self.btn_waveform = QPushButton("Rekordbox Wellenform")
        self.btn_waveform.setToolTip("Frequenz-Wellenform (Low/Mid/High) + Beatgrid berechnen")
        self.btn_waveform.setStyleSheet("font-weight: bold; color: #3C8CFF;")
        self.btn_waveform.clicked.connect(self._analyze_waveform)
        analyze_layout.addWidget(self.btn_waveform)

        left_layout.addWidget(analyze_group)

        # KI-Werkzeuge
        ki_group = QGroupBox("KI-Werkzeuge")
        ki_layout = QVBoxLayout(ki_group)

        self.btn_stem_separate = QPushButton("KI Stem Separation")
        self.btn_stem_separate.setToolTip("Demucs: Vocals, Drums, Bass, Other trennen")
        self.btn_stem_separate.clicked.connect(self._start_stem_separation)
        ki_layout.addWidget(self.btn_stem_separate)

        self.btn_auto_duck = QPushButton("Auto-Ducking")
        self.btn_auto_duck.setToolTip("Musik bei Sprache automatisch absenken")
        self.btn_auto_duck.clicked.connect(self._start_auto_ducking)
        ki_layout.addWidget(self.btn_auto_duck)

        left_layout.addWidget(ki_group)

        # Timeline-Aktion
        self.btn_add_to_timeline = QPushButton("Zur Timeline hinzufuegen")
        self.btn_add_to_timeline.setObjectName("btn_accent")
        self.btn_add_to_timeline.setToolTip("Markierte Datei auf Timeline legen")
        self.btn_add_to_timeline.clicked.connect(self._add_selected_to_timeline)
        left_layout.addWidget(self.btn_add_to_timeline)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Analyse laeuft...")
        self.progress_bar.setToolTip("Zeigt den Fortschritt der aktuellen Hintergrund-Analyse an")
        left_layout.addWidget(self.progress_bar)

        left_layout.addStretch()
        splitter.addWidget(left_panel)

        # ── Rechte Seite: Video Pool + Audio Pool (vertikal getrennt) ──
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        # --- Semantic Search Bar (Phase 2, SEKTOR 3) ---
        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(4)

        search_icon = QLabel("SigLIP")
        search_icon.setStyleSheet(
            "color: #00D4E6; font-weight: 700; font-size: 9px; padding: 2px 6px; "
            "background: #0A1520; border: 1px solid #00607A; border-radius: 3px;"
        )
        search_icon.setFixedWidth(46)
        search_row.addWidget(search_icon)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Semantische Suche: z.B. 'person dancing on stage'...")
        self.search_input.setToolTip(
            "SigLIP Text-zu-Video Suche: Beschreibe was du suchst, "
            "und die relevantesten Szenen werden angezeigt"
        )
        self.search_input.returnPressed.connect(self._run_semantic_search)
        search_row.addWidget(self.search_input, stretch=1)

        self.btn_search = QPushButton("Suchen")
        self.btn_search.setFixedHeight(26)
        self.btn_search.setFixedWidth(70)
        self.btn_search.setToolTip("Semantische Suche starten (SigLIP + LanceDB)")
        self.btn_search.clicked.connect(self._run_semantic_search)
        search_row.addWidget(self.btn_search)

        self.btn_search_clear = QPushButton("X")
        self.btn_search_clear.setFixedSize(26, 26)
        self.btn_search_clear.setToolTip("Suche zurücksetzen — alle Videos anzeigen")
        self.btn_search_clear.setStyleSheet(
            "QPushButton { color: #FF6060; font-weight: bold; border: 1px solid #333; border-radius: 3px; }"
            "QPushButton:hover { background: #3A1010; }"
        )
        self.btn_search_clear.clicked.connect(self._clear_search)
        search_row.addWidget(self.btn_search_clear)

        right_layout.addLayout(search_row)

        pool_splitter = QSplitter(Qt.Orientation.Vertical)

        # --- Video Pool ---
        video_pool_widget = QWidget()
        video_pool_layout = QVBoxLayout(video_pool_widget)
        video_pool_layout.setContentsMargins(0, 0, 0, 0)
        video_pool_layout.setSpacing(2)

        video_pool_header = QLabel("VIDEO POOL")
        video_pool_header.setStyleSheet("color: #00F0FF; font-weight: 700; font-size: 11px; padding: 2px 4px; background: #0A0A0A;")
        video_pool_layout.addWidget(video_pool_header)

        self.video_pool_table = QTableWidget()
        self.video_pool_table.setColumnCount(6)
        self.video_pool_table.setHorizontalHeaderLabels(["ID", "Titel", "Aufloesung", "FPS", "Codec", "Dateipfad"])
        self.video_pool_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.video_pool_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.video_pool_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.video_pool_table.setAlternatingRowColors(True)
        self.video_pool_table.setToolTip("Video Pool: Alle importierten Video-Dateien")
        vh = self.video_pool_table.horizontalHeader()
        vh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        vh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        vh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        vh.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        vh.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        vh.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        video_pool_layout.addWidget(self.video_pool_table)

        pool_splitter.addWidget(video_pool_widget)

        # --- Audio Pool ---
        audio_pool_widget = QWidget()
        audio_pool_layout = QVBoxLayout(audio_pool_widget)
        audio_pool_layout.setContentsMargins(0, 0, 0, 0)
        audio_pool_layout.setSpacing(2)

        audio_pool_header = QLabel("AUDIO POOL")
        audio_pool_header.setStyleSheet("color: #FF6AC1; font-weight: 700; font-size: 11px; padding: 2px 4px; background: #0A0A0A;")
        audio_pool_layout.addWidget(audio_pool_header)

        self.audio_pool_table = QTableWidget()
        self.audio_pool_table.setColumnCount(6)
        self.audio_pool_table.setHorizontalHeaderLabels(["ID", "Titel", "BPM", "Key", "Stems", "Dateipfad"])
        self.audio_pool_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.audio_pool_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.audio_pool_table.setAlternatingRowColors(True)
        self.audio_pool_table.setToolTip("Audio Pool: Alle importierten Audio-Dateien")
        ah = self.audio_pool_table.horizontalHeader()
        ah.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        ah.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        ah.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        ah.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        ah.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        ah.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        audio_pool_layout.addWidget(self.audio_pool_table)

        # --- Stem Player (synchroner Multi-Track Audio-Mixer) ---
        # StemPlayer wird hier erzeugt, damit er vor _build_stems_workspace existiert.
        # Der alte StemWidget wurde entfernt — alle Stem-Kontrolle läuft über den
        # STEMS-Haupt-Reiter (StemWorkspace).
        self.stem_player = StemPlayer(self)
        self.stem_player.playback_finished.connect(self._on_stem_playback_finished)

        pool_splitter.addWidget(audio_pool_widget)

        pool_splitter.setStretchFactor(0, 1)
        pool_splitter.setStretchFactor(1, 1)

        right_layout.addWidget(pool_splitter)

        # Legacy media_table kept as hidden proxy for selection-based functions
        self.media_table = QTableWidget()
        self.media_table.setColumnCount(8)
        self.media_table.setHorizontalHeaderLabels(
            ["ID", "Typ", "Titel", "BPM", "Aufloesung", "FPS", "Stems", "Dateipfad"]
        )
        self.media_table.setVisible(False)

        # Sync pool table selections to hidden media_table
        self.video_pool_table.currentCellChanged.connect(self._on_video_pool_selected)
        self.audio_pool_table.currentCellChanged.connect(self._on_audio_pool_selected)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)

        layout.addWidget(splitter)
        return workspace

    # ==================================================================
    # Workspace 2: EDIT
    # ==================================================================

    def _build_edit_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main vertical splitter: top (preview+inspector) / bottom (curve+timeline)
        main_splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Top: Video Preview + Inspector Panel ──
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Large Video Preview (no GroupBox — clean)
        preview_container = QWidget()
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(4, 4, 4, 2)
        preview_layout.setSpacing(2)

        self.video_preview = VideoPreviewWidget()
        self.video_preview.setMinimumSize(100, 100)
        self.video_preview.setMaximumHeight(400)
        preview_layout.addWidget(self.video_preview, stretch=1)

        # Compact transport bar
        transport_row = QHBoxLayout()
        transport_row.setSpacing(4)
        self.btn_preview_play = QPushButton("\u25B6")
        self.btn_preview_play.setFixedSize(28, 24)
        self.btn_preview_play.setToolTip("Play / Pause")
        self.btn_preview_play.clicked.connect(self._toggle_preview_play)
        transport_row.addWidget(self.btn_preview_play)

        self.btn_preview_stop = QPushButton("\u25A0")
        self.btn_preview_stop.setFixedSize(28, 24)
        self.btn_preview_stop.setToolTip("Stop")
        self.btn_preview_stop.clicked.connect(self.video_preview.stop)
        transport_row.addWidget(self.btn_preview_stop)

        self.preview_time_label = QLabel("00:00 / 00:00")
        self.preview_time_label.setStyleSheet("color: #505050; font-size: 10px;")
        transport_row.addWidget(self.preview_time_label)
        transport_row.addStretch()

        # Inspector toggle button (always visible)
        self.btn_toggle_inspector = QPushButton("\u25B6")
        self.btn_toggle_inspector.setFixedSize(22, 22)
        self.btn_toggle_inspector.setToolTip("Inspector Panel ein-/ausklappen")
        self.btn_toggle_inspector.setStyleSheet("font-size: 9px; padding: 0;")
        self.btn_toggle_inspector.clicked.connect(self._toggle_inspector)
        transport_row.addWidget(self.btn_toggle_inspector)

        preview_layout.addLayout(transport_row)
        top_splitter.addWidget(preview_container)

        # ── Inspector Panel (collapsible, narrow right side) ──
        # Outer container that goes into the splitter
        self.inspector_panel = QWidget()
        self.inspector_panel.setObjectName("inspector_panel")
        self.inspector_panel.setMinimumWidth(350)
        insp_outer = QVBoxLayout(self.inspector_panel)
        insp_outer.setContentsMargins(0, 0, 0, 0)

        # ScrollArea wraps the actual inspector content
        insp_scroll = QScrollArea()
        insp_scroll.setWidgetResizable(True)
        insp_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        insp_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        insp_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        insp_outer.addWidget(insp_scroll)

        insp_content = QWidget()
        insp = QVBoxLayout(insp_content)
        insp.setContentsMargins(6, 6, 6, 6)
        insp.setSpacing(5)

        # Header
        hdr = QLabel("INSPECTOR")
        hdr.setStyleSheet(
            "color: #00D4E6; font-weight: 700; font-size: 10px; letter-spacing: 2px;"
        )
        insp.addWidget(hdr)
        self._add_separator(insp)

        # Source selectors
        src_lbl = QLabel("QUELLEN")
        src_lbl.setStyleSheet("color: #505050; font-size: 9px; font-weight: 600; letter-spacing: 1px;")
        insp.addWidget(src_lbl)

        self.audio_combo = QComboBox()
        self.audio_combo.setToolTip("Audio-Track fuer BPM-Pacing")
        insp.addWidget(self.audio_combo)

        self.video_combo = QComboBox()
        self.video_combo.setToolTip("Video-Clip fuer Vorschau")
        self.video_combo.currentIndexChanged.connect(self._on_video_combo_changed)
        insp.addWidget(self.video_combo)

        self.vibe_input = QLineEdit()
        self.vibe_input.setPlaceholderText("Stimmung / Vibe...")
        self.vibe_input.setToolTip("Freitext: energetisch, melancholisch, aggressiv...")
        insp.addWidget(self.vibe_input)

        self._add_separator(insp)

        # ── Phase 3: Advanced Pacing (DJ-Regler) ──
        pacing_lbl = QLabel("DJ PACING")
        pacing_lbl.setStyleSheet("color: #505050; font-size: 9px; font-weight: 600; letter-spacing: 1px;")
        insp.addWidget(pacing_lbl)

        # 1. Base Cut Rate (Beats per cut)
        cut_rate_row = QHBoxLayout()
        cut_rate_row.setSpacing(4)
        cr_lbl = QLabel("Cut Rate")
        cr_lbl.setFixedWidth(52)
        cr_lbl.setStyleSheet("color: #707070; font-size: 10px;")
        cr_lbl.setToolTip("Basis-Schnittrate: Alle N Beats wird geschnitten")
        cut_rate_row.addWidget(cr_lbl)
        self.cut_rate_combo = QComboBox()
        self.cut_rate_combo.addItems(["1 Beat", "2 Beats", "4 Beats", "8 Beats", "16 Beats"])
        self.cut_rate_combo.setCurrentIndex(2)  # Default: 4 Beats (Downbeat)
        self.cut_rate_combo.setToolTip("Basis-Schnittrate: 1=jeden Beat, 4=Downbeat, 16=sehr langsam")
        self.cut_rate_combo.setFixedHeight(22)
        cut_rate_row.addWidget(self.cut_rate_combo, stretch=1)
        insp.addLayout(cut_rate_row)

        # 2. Energy Reactivity (0-100%)
        energy_row = QHBoxLayout()
        energy_row.setSpacing(4)
        er_lbl = QLabel("Reaktivitaet")
        er_lbl.setFixedWidth(52)
        er_lbl.setStyleSheet("color: #707070; font-size: 10px;")
        er_lbl.setToolTip("Energy Reactivity: Erhoehe Cut-Rate bei hohem RMS/Spektral-Level")
        energy_row.addWidget(er_lbl)
        self.energy_reactivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.energy_reactivity_slider.setRange(0, 100)
        self.energy_reactivity_slider.setValue(50)
        self.energy_reactivity_slider.setFixedHeight(16)
        energy_row.addWidget(self.energy_reactivity_slider, stretch=1)
        self.energy_reactivity_spin = QSpinBox()
        self.energy_reactivity_spin.setRange(0, 100)
        self.energy_reactivity_spin.setValue(50)
        self.energy_reactivity_spin.setSuffix("%")
        self.energy_reactivity_spin.setFixedWidth(52)
        self.energy_reactivity_spin.setFixedHeight(20)
        self.energy_reactivity_spin.setStyleSheet("font-size: 10px;")
        # Sync slider <-> spinbox
        self.energy_reactivity_slider.valueChanged.connect(self.energy_reactivity_spin.setValue)
        self.energy_reactivity_spin.valueChanged.connect(self.energy_reactivity_slider.setValue)
        energy_row.addWidget(self.energy_reactivity_spin)
        insp.addLayout(energy_row)

        # 3. Breakdown Behavior
        bd_row = QHBoxLayout()
        bd_row.setSpacing(4)
        bd_lbl = QLabel("Breakdown")
        bd_lbl.setFixedWidth(52)
        bd_lbl.setStyleSheet("color: #707070; font-size: 10px;")
        bd_lbl.setToolTip("Verhalten bei niedrigem RMS (Breakdowns/Intros)")
        bd_row.addWidget(bd_lbl)
        self.breakdown_combo = QComboBox()
        self.breakdown_combo.addItems([
            "Cuts halbieren",
            "16-Beat erzwingen",
            "Keine Cuts",
        ])
        self.breakdown_combo.setCurrentIndex(0)
        self.breakdown_combo.setToolTip(
            "Halbieren: Cut-Rate verdoppelt sich (z.B. 4→8 Beats)\n"
            "16-Beat: Erzwingt 16-Beat Intervalle bei Breakdowns\n"
            "Keine Cuts: Keine Schnitte waehrend Breakdowns"
        )
        self.breakdown_combo.setFixedHeight(22)
        bd_row.addWidget(self.breakdown_combo, stretch=1)
        insp.addLayout(bd_row)

        # Legacy slider refs (for backward compat with _generate_timeline)
        self.tempo_slider = self.energy_reactivity_slider
        self.energy_slider = self.energy_reactivity_slider
        self.density_slider = self.energy_reactivity_slider

        self._add_separator(insp)

        # Action buttons
        self.btn_generate = QPushButton("Timeline generieren")
        self.btn_generate.setObjectName("btn_accent")
        self.btn_generate.setFixedHeight(30)
        self.btn_generate.setToolTip("Berechnet Schnittpunkte (BPM + Pacing-Kurve)")
        self.btn_generate.clicked.connect(self._generate_timeline)
        insp.addWidget(self.btn_generate)

        self.btn_auto_edit = QPushButton("Auto-Edit")
        self.btn_auto_edit.setObjectName("btn_accent")
        self.btn_auto_edit.setFixedHeight(30)
        self.btn_auto_edit.setToolTip(
            "Phase 3: DJ-Pacing + OTIO Timeline + Anker + LanceDB Matching"
        )
        self.btn_auto_edit.clicked.connect(self._auto_edit_to_beat)
        insp.addWidget(self.btn_auto_edit)

        self._add_separator(insp)

        # ── Phase 3: Anchor System ──
        anchor_lbl = QLabel("ANKER")
        anchor_lbl.setStyleSheet("color: #505050; font-size: 9px; font-weight: 600; letter-spacing: 1px;")
        insp.addWidget(anchor_lbl)

        # Anchor list widget
        self.anchor_list = QTreeWidget()
        self.anchor_list.setHeaderLabels(["Zeit", "Video/Szene"])
        self.anchor_list.setMaximumHeight(100)
        self.anchor_list.setStyleSheet(
            "QTreeWidget { background: #0A0A0A; border: 1px solid #1E1E1E; "
            "font-size: 10px; color: #C0C0C0; }"
            "QTreeWidget::item { padding: 1px; }"
        )
        self.anchor_list.setToolTip(
            "Audio-Anker: An diesen Zeitpunkten wird ein bestimmtes Video eingesetzt.\n"
            "Doppelklick zum Bearbeiten."
        )
        insp.addWidget(self.anchor_list)

        # Anchor add/remove buttons
        anchor_btn_row = QHBoxLayout()
        anchor_btn_row.setSpacing(4)
        self.btn_add_anchor = QPushButton("+ Anker")
        self.btn_add_anchor.setFixedHeight(22)
        self.btn_add_anchor.setStyleSheet("font-size: 9px;")
        self.btn_add_anchor.setToolTip("Neuen Anker an der aktuellen Position hinzufuegen")
        self.btn_add_anchor.clicked.connect(self._add_anchor_dialog)
        anchor_btn_row.addWidget(self.btn_add_anchor)

        self.btn_remove_anchor = QPushButton("- Anker")
        self.btn_remove_anchor.setFixedHeight(22)
        self.btn_remove_anchor.setStyleSheet("font-size: 9px;")
        self.btn_remove_anchor.setToolTip("Ausgewaehlten Anker entfernen")
        self.btn_remove_anchor.clicked.connect(self._remove_selected_anchor)
        anchor_btn_row.addWidget(self.btn_remove_anchor)

        self.btn_sync_anchors = QPushButton("Sync")
        self.btn_sync_anchors.setFixedHeight(22)
        self.btn_sync_anchors.setStyleSheet("font-size: 9px;")
        self.btn_sync_anchors.setToolTip("Anker synchronisieren")
        self.btn_sync_anchors.clicked.connect(self._sync_anchors)
        anchor_btn_row.addWidget(self.btn_sync_anchors)
        insp.addLayout(anchor_btn_row)

        self._add_separator(insp)

        # ── Phase 3: Keyframe-String Analyse ──
        kf_lbl = QLabel("SZENEN-ANALYSE")
        kf_lbl.setStyleSheet("color: #505050; font-size: 9px; font-weight: 600; letter-spacing: 1px;")
        insp.addWidget(kf_lbl)

        self.btn_keyframe_string = QPushButton("Keyframe-String generieren")
        self.btn_keyframe_string.setFixedHeight(24)
        self.btn_keyframe_string.setStyleSheet("font-size: 9px; color: #00D4E6; font-weight: bold;")
        self.btn_keyframe_string.setToolTip(
            "Generiert lesbaren Text-String aller erkannten Video-Szenen\n"
            "mit RAFT-Motion-Werten (Ruhig/Moderat/Action/Extrem)"
        )
        self.btn_keyframe_string.clicked.connect(self._show_keyframe_strings)
        insp.addWidget(self.btn_keyframe_string)

        self.keyframe_text = QTextEdit()
        self.keyframe_text.setReadOnly(True)
        self.keyframe_text.setMaximumHeight(120)
        self.keyframe_text.setStyleSheet(
            "QTextEdit { background: #0A0A0A; border: 1px solid #1E1E1E; "
            "font-family: 'Cascadia Code'; font-size: 9px; color: #A0A0A0; }"
        )
        self.keyframe_text.setToolTip("Szenen-Analyse: Zeigt alle erkannten Szenen mit Motion-Kategorien")
        self.keyframe_text.setPlaceholderText("Keyframe-Strings werden hier angezeigt...")
        insp.addWidget(self.keyframe_text)

        insp.addStretch()

        insp_scroll.setWidget(insp_content)

        top_splitter.addWidget(self.inspector_panel)
        top_splitter.setStretchFactor(0, 1)
        top_splitter.setStretchFactor(1, 1)
        top_splitter.setCollapsible(0, False)
        top_splitter.setCollapsible(1, False)

        main_splitter.addWidget(top_splitter)

        # ── Bottom: Manual Pacing Curve + Timeline ──
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(4, 2, 4, 2)
        bottom_layout.setSpacing(1)

        # Pacing curve header
        curve_hdr = QHBoxLayout()
        curve_hdr.setSpacing(4)
        curve_lbl = QLabel("MANUAL PACING")
        curve_lbl.setStyleSheet("color: #505050; font-size: 9px; font-weight: 600; letter-spacing: 1px;")
        curve_hdr.addWidget(curve_lbl)
        btn_reset = QPushButton("Reset")
        btn_reset.setFixedHeight(16)
        btn_reset.setFixedWidth(44)
        btn_reset.setStyleSheet("font-size: 8px; padding: 0 3px;")
        btn_reset.setToolTip("Pacing-Kurve zuruecksetzen auf 50%")
        btn_reset.clicked.connect(lambda: self.pacing_curve.reset_curve())
        curve_hdr.addWidget(btn_reset)
        curve_hdr.addStretch()
        bottom_layout.addLayout(curve_hdr)

        # Drawable pacing density curve
        self.pacing_curve = PacingCurveWidget()
        bottom_layout.addWidget(self.pacing_curve)

        # Timeline (full width, maximum space)
        self.timeline_view = InteractiveTimeline()
        self.timeline_view.setToolTip("Timeline: Drag & Drop, Mausrad zum Zoomen")
        self.timeline_view.clip_moved.connect(self._on_timeline_clip_moved)
        bottom_layout.addWidget(self.timeline_view, stretch=1)

        self.cut_info_label = QLabel("")
        self.cut_info_label.setStyleSheet("color: #404040; font-size: 10px; padding: 1px 4px;")
        bottom_layout.addWidget(self.cut_info_label)

        main_splitter.addWidget(bottom_widget)

        # Preview ~30%, Timeline area ~70% — timeline dominates
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 3)
        main_splitter.setSizes([200, 600])
        main_splitter.setCollapsible(0, False)
        main_splitter.setCollapsible(1, False)

        layout.addWidget(main_splitter)

        self._refresh_director_combos()
        return workspace

    # ==================================================================
    # Workspace 3: STEMS (DAW-Style Stem View)
    # ==================================================================

    def _build_stems_workspace(self) -> QWidget:
        """Baut den STEMS Workspace: 4 Track-Bänder mit Wellenformen + Transport."""
        self.stem_workspace = StemWorkspace()

        # Signale zum bestehenden StemPlayer verbinden
        self.stem_workspace.stem_volume_changed.connect(self.stem_player.set_volume)
        self.stem_workspace.stem_mute_toggled.connect(self.stem_player.set_mute)
        self.stem_workspace.play_requested.connect(self.stem_player.play)
        self.stem_workspace.pause_requested.connect(self.stem_player.pause)
        self.stem_workspace.stop_requested.connect(self.stem_player.stop)
        self.stem_workspace.seek_requested.connect(self.stem_player.seek)
        self.stem_player.position_changed.connect(self.stem_workspace.update_position)
        self.stem_player.state_changed.connect(self.stem_workspace.update_playback_state)
        # [I-10 FIX] playback_finished nutzt benannte Methode (oben definiert)

        return self.stem_workspace

    # ==================================================================
    # Workspace 4: CONVERT (Video-Standardisierung)
    # ==================================================================

    def _build_effects_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(8, 8, 8, 4)

        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Linke Seite: Konvertierungs-Einstellungen ──
        settings_panel = QWidget()
        settings_layout = QVBoxLayout(settings_panel)

        # Ziel-Format
        format_group = QGroupBox("Ziel-Format")
        format_layout = QVBoxLayout(format_group)

        res_row = QHBoxLayout()
        res_row.addWidget(QLabel("Aufloesung:"))
        self.convert_resolution = QComboBox()
        self.convert_resolution.addItems(["1920x1080 (1080p)", "2560x1440 (2K)", "3840x2160 (4K)", "1280x720 (720p)"])
        self.convert_resolution.setToolTip("Ziel-Aufloesung fuer alle Videos")
        res_row.addWidget(self.convert_resolution)
        format_layout.addLayout(res_row)

        fps_row = QHBoxLayout()
        fps_row.addWidget(QLabel("Framerate:"))
        self.convert_fps = QComboBox()
        self.convert_fps.addItems(["30 fps", "24 fps", "25 fps", "50 fps", "60 fps"])
        self.convert_fps.setToolTip("Ziel-Framerate fuer alle Videos")
        fps_row.addWidget(self.convert_fps)
        format_layout.addLayout(fps_row)

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Container:"))
        self.convert_format = QComboBox()
        self.convert_format.addItems(["mp4 (H.264)", "mp4 (H.265/HEVC)", "mov (ProRes)", "mkv (H.264)"])
        self.convert_format.setToolTip("Ziel-Containerformat")
        fmt_row.addWidget(self.convert_format)
        format_layout.addLayout(fmt_row)

        settings_layout.addWidget(format_group)

        # Konvertierungs-Aktionen
        action_group = QGroupBox("Aktionen")
        action_layout = QVBoxLayout(action_group)

        self.btn_standardize_all = QPushButton("Alle Videos standardisieren")
        self.btn_standardize_all.setObjectName("btn_accent")
        self.btn_standardize_all.setMinimumHeight(46)
        self.btn_standardize_all.setToolTip(
            "Konvertiert alle Videos im Video Pool in das gewaehlte Standardformat (per ffmpeg)"
        )
        self.btn_standardize_all.clicked.connect(self._standardize_all_videos)
        action_layout.addWidget(self.btn_standardize_all)

        self.convert_progress = QProgressBar()
        self.convert_progress.setVisible(False)
        self.convert_progress.setTextVisible(True)
        self.convert_progress.setFormat("Konvertierung...")
        action_layout.addWidget(self.convert_progress)

        settings_layout.addWidget(action_group)

        # Legacy effects controls (hidden but keep refs for existing code)
        self.effects_clip_combo = QComboBox()
        self.effects_clip_combo.setVisible(False)
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setVisible(False)
        self.brightness_label = QLabel()
        self.contrast_slider = QSlider(Qt.Orientation.Horizontal)
        self.contrast_slider.setVisible(False)
        self.contrast_label = QLabel()
        self.crossfade_slider = QSlider(Qt.Orientation.Horizontal)
        self.crossfade_slider.setVisible(False)
        self.crossfade_label = QLabel()

        settings_layout.addStretch()
        top_splitter.addWidget(settings_panel)

        # ── Rechte Seite: Konvertierungs-Log ──
        log_panel = QWidget()
        log_layout = QVBoxLayout(log_panel)

        log_title = QLabel("CONVERT LOG")
        log_title.setStyleSheet("color: #00F0FF; font-weight: 700; font-size: 11px; padding: 2px 4px;")
        log_layout.addWidget(log_title)

        self.convert_log = QTextEdit()
        self.convert_log.setReadOnly(True)
        self.convert_log.setStyleSheet("background-color: #0A0A0A; border: 1px solid #1E1E1E; color: #C0C0C0; font-family: 'Consolas';")
        self.convert_log.setToolTip("Protokoll der Video-Konvertierungen")
        self.convert_log.append("[Convert] Bereit. Waehle Ziel-Format und klicke 'Alle Videos standardisieren'.")
        log_layout.addWidget(self.convert_log)

        self.effects_preview = QLabel("")
        self.effects_preview.setVisible(False)

        top_splitter.addWidget(log_panel)
        top_splitter.setStretchFactor(0, 2)
        top_splitter.setStretchFactor(1, 3)

        layout.addWidget(top_splitter)
        return workspace

    # ==================================================================
    # Workspace 4: DELIVER
    # ==================================================================

    def _build_deliver_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(8, 8, 8, 4)

        # ── Timeline-Status ──
        info_group = QGroupBox("Timeline-Status")
        info_layout = QVBoxLayout(info_group)
        self.production_info = QLabel("Timeline laden...")
        self.production_info.setStyleSheet("color: #E0E0E0; font-size: 14px;")
        self.production_info.setToolTip("Zeigt eine Zusammenfassung der aktuellen Timeline: Anzahl der Clips, Spuren und geschaetzte Gesamtdauer")
        info_layout.addWidget(self.production_info)
        layout.addWidget(info_group)

        # ── Export-Einstellungen ──
        settings_group = QGroupBox("Export-Einstellungen")
        settings_layout = QHBoxLayout(settings_group)

        name_label = QLabel("Dateiname:")
        name_label.setToolTip("Name der finalen Video-Datei. Die Endung .mp4 wird automatisch angehaengt")
        settings_layout.addWidget(name_label)
        self.export_name_input = QLineEdit("output.mp4")
        self.export_name_input.setToolTip("Gib den gewuenschten Dateinamen fuer das exportierte Video ein (ohne Pfad)")
        settings_layout.addWidget(self.export_name_input)

        res_label = QLabel("Aufloesung:")
        res_label.setToolTip("Ziel-Aufloesung des exportierten Videos. Hoehere Aufloesung = groessere Datei, laengerer Export")
        settings_layout.addWidget(res_label)
        self.resolution_combo = QComboBox()
        self.resolution_combo.addItems(["1920x1080", "1280x720", "854x480", "3840x2160"])
        self.resolution_combo.setToolTip("Waehle die Video-Aufloesung: 1080p (Standard), 720p (schnell), 480p (Vorschau) oder 4K (beste Qualitaet)")
        settings_layout.addWidget(self.resolution_combo)

        fps_label = QLabel("FPS:")
        fps_label.setToolTip("Bildrate des exportierten Videos. 30 FPS ist Standard, 60 FPS fuer fluessigere Bewegungen")
        settings_layout.addWidget(fps_label)
        self.fps_combo = QComboBox()
        self.fps_combo.addItems(["30", "24", "25", "60"])
        self.fps_combo.setToolTip("Waehle die Bildrate: 30 (Standard), 24 (Film-Look), 25 (PAL), 60 (Sport/Gaming)")
        settings_layout.addWidget(self.fps_combo)

        layout.addWidget(settings_group)

        # ── Export-Buttons ──
        export_row = QHBoxLayout()

        self.btn_export = QPushButton("Video exportieren")
        self.btn_export.setObjectName("btn_accent")
        self.btn_export.setMinimumHeight(36)
        self.btn_export.setToolTip("Finales Video mit FFmpeg rendern")
        self.btn_export.clicked.connect(self._start_export)
        export_row.addWidget(self.btn_export)

        self.btn_refresh_production = QPushButton("Aktualisieren")
        self.btn_refresh_production.setMinimumHeight(36)
        self.btn_refresh_production.setToolTip("Timeline-Status aktualisieren")
        self.btn_refresh_production.clicked.connect(self._refresh_production_info)
        export_row.addWidget(self.btn_refresh_production)

        layout.addLayout(export_row)

        # ── Export-Fortschritt ──
        self.export_progress = QProgressBar()
        self.export_progress.setVisible(False)
        self.export_progress.setTextVisible(True)
        self.export_progress.setToolTip("Fortschritt des aktuellen Video-Exports in Prozent")
        layout.addWidget(self.export_progress)

        # ── Export-Log ──
        log_label = QLabel("Export-Protokoll:")
        log_label.setStyleSheet("color: #00F0FF; font-weight: 600; margin-top: 8px;")
        layout.addWidget(log_label)

        self.export_log = QTextEdit()
        self.export_log.setReadOnly(True)
        self.export_log.setToolTip("Protokoll des Export-Vorgangs: Zeigt jeden Schritt, Fehler und den finalen Ausgabepfad")
        layout.addWidget(self.export_log)

        return workspace

    # ==================================================================
    # Helper: Slider erstellen
    # ==================================================================

    def _create_compact_slider(self, label: str, min_val: int, max_val: int,
                               default: int):
        """Compact horizontal slider row: [Label] [=====o=====] [Value]"""
        row = QHBoxLayout()
        row.setSpacing(4)
        lbl = QLabel(label)
        lbl.setFixedWidth(46)
        lbl.setStyleSheet("color: #707070; font-size: 10px;")
        row.addWidget(lbl)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default)
        slider.setFixedHeight(16)
        row.addWidget(slider, stretch=1)
        val_lbl = QLabel(str(default))
        val_lbl.setFixedWidth(26)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        val_lbl.setStyleSheet("color: #00D4E6; font-size: 10px;")
        slider.valueChanged.connect(lambda v: val_lbl.setText(str(v)))
        row.addWidget(val_lbl)
        return slider, row

    def _toggle_inspector(self):
        """Toggle inspector panel visibility."""
        if self.inspector_panel.isVisible():
            self.inspector_panel.hide()
            self.btn_toggle_inspector.setText("\u25C0")
        else:
            self.inspector_panel.show()
            self.btn_toggle_inspector.setText("\u25B6")

    @staticmethod
    def _add_separator(layout):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #1E1E1E;")
        layout.addWidget(sep)

    # ==================================================================
    # Helper: Thread starten
    # ==================================================================

    def _start_worker_thread(self, worker: QObject, on_finish=None, on_error=None):
        """Legacy-Bridge: Leitet an GlobalTaskManager.start_task() weiter.

        Alle Threads werden jetzt vom TaskManager gehalten (GC-Schutz).
        Existierende Aufrufe bleiben kompatibel.
        """
        # Worker-Name fuer Task-Anzeige aus Klasse ableiten
        worker_name = type(worker).__name__.replace("Worker", "")

        # Falls der Worker schon eine task_id hat (von manueller create_task()),
        # registrieren wir Thread+Worker im bestehenden Task.
        existing_task_id = getattr(worker, 'task_id', None)

        if existing_task_id and existing_task_id in task_manager._tasks:
            # Thread im bestehenden Task registrieren
            task = task_manager._tasks[existing_task_id]
            thread = QThread()
            worker.moveToThread(thread)
            thread.started.connect(worker.run)

            if on_finish:
                def _guarded_finish(*args, _w=worker, _cb=on_finish):
                    if not getattr(_w, '_errored', False):
                        _cb(*args)
                worker.finished.connect(_guarded_finish)
            # Error-Signal: Fallback-Logger immer verbinden (stille Fehler verhindern)
            def _default_error_handler(*args, _tid=existing_task_id, _name=worker_name, _tm=task_manager):
                err_msg = str(args[-1]) if args else "Unbekannter Fehler"
                logging.error(
                    "[TaskEngine] Worker-Fehler '%s' (task_id=%s): %s",
                    _name, _tid, err_msg,
                )
                _tm.finish_task(_tid, status="error", message=err_msg)
            worker.error.connect(_default_error_handler)
            if on_error:
                worker.error.connect(on_error)

            # Progress-Signal auto-verbinden wenn vorhanden
            if hasattr(worker, "progress"):
                worker.progress.connect(
                    lambda pct, msg, _tid=existing_task_id: task_manager.update_task(
                        _tid, pct, message=msg
                    )
                )

            worker.finished.connect(thread.quit)
            thread.finished.connect(
                lambda _tid=existing_task_id: task_manager._on_thread_done(_tid)
            )

            task.thread = thread
            task.worker = worker
            self._active_threads.append(thread)
            self._active_workers.append(worker)
            thread.finished.connect(
                lambda _t=thread, _w=worker: self._cleanup_worker(_t, _w)
            )
            thread.start()
            return thread
        else:
            # Neuer Task ueber die Engine
            task = task_manager.start_task(
                name=worker_name,
                worker=worker,
                on_finish=on_finish,
                on_error=on_error,
            )
            if task.thread:
                self._active_threads.append(task.thread)
                task.thread.finished.connect(
                    lambda _t=task.thread, _w=worker: self._cleanup_worker(_t, _w)
                )
            self._active_workers.append(worker)
            return task.thread

    def _cancel_worker_for_task(self, task_id: str):
        """Cancel via TaskEngine."""
        task_manager.cancel_task(task_id)
        self.console_text.append(f"[System] Task abgebrochen: {task_id}")

    # ==================================================================
    # Combos aktualisieren
    # ==================================================================

    def _refresh_director_combos(self):
        media = get_all_media()
        self.audio_combo.clear()
        self.video_combo.clear()
        self.audio_combo.addItem("-- kein Audio --", None)
        self.video_combo.addItem("-- kein Video --", None)
        for item in media:
            label = f"[{item['id']}] {item['title']}"
            if item["type"] == "Audio":
                bpm = item.get("bpm")
                if bpm:
                    label += f" ({bpm} BPM)"
                self.audio_combo.addItem(label, item["id"])
            elif item["type"] == "Video":
                self.video_combo.addItem(label, item["id"])

    def _refresh_effects_combos(self):
        self.effects_clip_combo.clear()
        self.effects_clip_combo.addItem("-- Clip waehlen --", None)
        with DBSession(engine) as session:
            entries = (
                session.query(TimelineEntry)
                .filter_by(project_id=1, track="video")
                .order_by(TimelineEntry.start_time)
                .all()
            )
            for entry in entries:
                clip = session.get(VideoClip, entry.media_id)
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

        vf_extra = f"eq=brightness={brightness}:contrast={contrast}"
        worker = FrameExtractWorker(file_path, 1.0, 320, 180, vf_extra)
        worker.frame_ready.connect(self._on_effect_frame_ready)
        worker.error.connect(lambda msg: self.effects_preview.setText(msg))
        # Kurzlebiger Task (Frame-Extraktion) — ueber Task-Engine
        self._start_worker_thread(worker)

    def _on_effect_frame_ready(self, raw_data: bytes, width: int, height: int):
        img = QImage(raw_data, width, height, width * 3, QImage.Format.Format_RGB888)
        self.effects_preview.setPixmap(QPixmap.fromImage(img))

    # ==================================================================
    # CONVERT: Video-Standardisierung
    # ==================================================================

    def _standardize_all_videos(self):
        """Konvertiert alle Videos im Video Pool ins gewaehlte Format per ffmpeg (im Worker-Thread)."""
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
        worker.progress.connect(lambda pct, msg: (
            self.convert_log.append(msg),
            self.convert_progress.setValue(pct),
        ))
        worker.finished.connect(lambda converted, total: self._on_batch_convert_finished(
            converted, total, task.task_id
        ))
        worker.error.connect(lambda err: self._on_batch_convert_error(err, task.task_id))

        self._start_worker_thread(worker)

    def _on_batch_convert_finished(self, converted: int, total: int, task_id: str):
        if converted == 0 and total == 0:
            return  # Error-path fallback
        self.convert_progress.setVisible(False)
        task_manager.finish_task(task_id, message=f"{converted}/{total} konvertiert")
        self.convert_log.append(f"[Convert] Fertig: {converted}/{total} Videos konvertiert.")

    def _on_batch_convert_error(self, error_msg: str, task_id: str):
        self.convert_progress.setVisible(False)
        self.convert_log.append(f"[Convert-Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Video Combo Changed
    # ==================================================================

    def _on_video_combo_changed(self, index: int):
        video_id = self.video_combo.currentData()
        if video_id is None:
            self.video_preview.setText("Keine Vorschau")
            return
        with DBSession(engine) as session:
            clip = session.get(VideoClip, video_id)
            if clip and clip.file_path:
                dur = clip.duration if clip.duration else 0.0
                self.video_preview.load_video(clip.file_path, dur)

    def _toggle_preview_play(self):
        self.video_preview.toggle_play()

    # ==================================================================
    # Timeline generieren
    # ==================================================================

    def _generate_timeline(self):
        audio_id = self.audio_combo.currentData()
        video_id = self.video_combo.currentData()

        # Collect manual density curve from pacing widget
        densities = self.pacing_curve.get_all_densities()

        # Map cut_rate_combo to tempo for legacy PacingSettings
        cut_rate_map = {0: 90, 1: 70, 2: 50, 3: 30, 4: 10}
        tempo_val = cut_rate_map.get(self.cut_rate_combo.currentIndex(), 50)
        reactivity = self.energy_reactivity_spin.value()

        settings = PacingSettings(
            tempo=tempo_val,
            energy=reactivity,
            cut_density=reactivity,
            vibe=self.vibe_input.text(),
            manual_density_curve=densities,
        )

        audio_dur = 0.0
        video_dur = 0.0
        if audio_id is not None:
            with DBSession(engine) as s:
                track = s.get(AudioTrack, audio_id)
                if track and track.duration:
                    audio_dur = track.duration
        if video_id is not None:
            with DBSession(engine) as s:
                clip = s.get(VideoClip, video_id)
                if clip and clip.duration:
                    video_dur = clip.duration

        total_dur = max(audio_dur, video_dur, 30.0)

        # Update pacing curve duration
        self.pacing_curve.set_duration(total_dur)

        cuts = calculate_cut_points(audio_id, video_id, settings, total_dur)

        self.timeline_view.load_from_db()
        self.timeline_view.set_cut_points(cuts, total_dur)

        beat_cuts = sum(1 for c in cuts if c.source == "beat")
        scene_cuts = sum(1 for c in cuts if c.source == "scene")
        energy_cuts = sum(1 for c in cuts if c.source == "energy")
        drum_cuts = sum(1 for c in cuts if c.source == "drum")
        self.cut_info_label.setText(
            f"{len(cuts)} Cuts | Beat:{beat_cuts} Szene:{scene_cuts} "
            f"Energie:{energy_cuts} Drum:{drum_cuts} | {total_dur:.0f}s"
        )
        self.console_text.append(
            f"[Pacing] {len(cuts)} Cuts generiert (Manual Curve aktiv)"
        )

    # ==================================================================
    # Auto-Edit to Beat
    # ==================================================================

    def _auto_edit_to_beat(self):
        """Phase 3: DJ-Pacing Auto-Edit mit OTIO Timeline."""
        audio_id = self.audio_combo.currentData()
        if audio_id is None:
            self.console_text.append("[Auto-Edit] Kein Audio-Track ausgewaehlt.")
            return

        with DBSession(engine) as session:
            clips = session.query(VideoClip).filter_by(project_id=1).all()
            video_ids = [c.id for c in clips]

        if not video_ids:
            self.console_text.append("[Auto-Edit] Keine Video-Clips vorhanden.")
            return

        # Phase 3: DJ-Regler auslesen
        cut_rate_map = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16}
        base_cut_rate = cut_rate_map.get(self.cut_rate_combo.currentIndex(), 4)

        breakdown_map = {0: "halve", 1: "force16", 2: "none"}
        breakdown = breakdown_map.get(self.breakdown_combo.currentIndex(), "halve")

        # Anker aus UI sammeln
        anchors = self._collect_anchors_from_ui()

        settings = AdvancedPacingSettings(
            base_cut_rate=base_cut_rate,
            energy_reactivity=self.energy_reactivity_spin.value(),
            breakdown_behavior=breakdown,
            vibe=self.vibe_input.text(),
            manual_density_curve=self.pacing_curve.get_all_densities(),
            anchors=anchors,
        )

        task = task_manager.create_task(
            "Auto-Edit (Phase 3)",
            f"DJ-Pacing: {base_cut_rate}-Beat, Reaktivitaet={settings.energy_reactivity}%, "
            f"Breakdown={breakdown}"
        )
        self.console_text.append(
            f"[Auto-Edit] Phase 3 DJ-Pacing starte "
            f"(Rate={base_cut_rate} Beats, Reaktivitaet={settings.energy_reactivity}%, "
            f"Breakdown={breakdown}, {len(video_ids)} Clips, "
            f"{len(anchors)} Anker)..."
        )
        self.btn_auto_edit.setEnabled(False)
        self.btn_auto_edit.setText("laeuft...")

        worker = AutoEditWorker(audio_id, video_ids, settings)
        worker.task_id = task.task_id
        worker.finished.connect(
            lambda segs, cps: self._on_auto_edit_finished(segs, cps, task.task_id)
        )
        worker.error.connect(lambda err: self._on_auto_edit_error(err, task.task_id))

        self._start_worker_thread(worker)

    def _on_auto_edit_finished(self, segments: list, cut_points: list, task_id: str):
        self.btn_auto_edit.setEnabled(True)
        self.btn_auto_edit.setText("Auto-Edit")

        if not segments:
            # Could be error-path fallback OR legitimate empty result (no beats)
            if not cut_points:
                return  # Error-path: _on_auto_edit_error already handled
            self.console_text.append("[Auto-Edit] Keine Segmente erzeugt (kein Audio/Beats?).")
            task_manager.finish_task(task_id, "error", "Keine Segmente")
            return

        # 1. SQLite TimelineEntries aktualisieren (fuer UI-Anzeige)
        # Bug-21 Fix: DELETE und alle INSERTs in EINER Transaktion (kein Split-Commit).
        # Vorher: erster commit() nach DELETE persistierte sofort; wenn der zweite
        # Block (Insert-Loop) fehlschlug, war die Timeline leer ohne Ersatz-Einträge.
        with DBSession(engine) as session:
            session.query(TimelineEntry).filter_by(
                project_id=1, track="video"
            ).delete()

            for seg in segments:
                entry = TimelineEntry(
                    project_id=1,
                    track="video",
                    media_id=seg["video_id"],
                    start_time=seg["start"],
                    end_time=seg["end"],
                    source_start=seg.get("source_start", 0.0),
                    source_end=seg.get("source_end"),
                    lane=0,
                )
                session.add(entry)
            session.commit()  # Einziger Commit — atomar

        # 2. OTIO Timeline generieren
        self._build_otio_timeline(segments)

        # 3. UI aktualisieren
        self.timeline_view.load_from_db()

        # 4. CutPoints visualisieren
        if cut_points:
            total_dur = segments[-1]["end"] if segments else 60.0
            cps = [CutPoint(
                time=cp["time"], source=cp["source"], strength=cp["strength"]
            ) for cp in cut_points]
            self.timeline_view.set_cut_points(cps, total_dur)

            anchor_cuts = sum(1 for cp in cut_points if cp["source"] == "anchor")
            beat_cuts = sum(1 for cp in cut_points if cp["source"] == "beat")
            self.cut_info_label.setText(
                f"{len(cut_points)} Cuts | Beat:{beat_cuts} Anker:{anchor_cuts} | "
                f"{total_dur:.0f}s | {len(segments)} Segmente"
            )

        self.console_text.append(
            f"[Auto-Edit] Phase 3 fertig: {len(segments)} Segmente, "
            f"OTIO Timeline generiert."
        )
        task_manager.finish_task(task_id, "finished", f"{len(segments)} Segmente")

    def _build_otio_timeline(self, segments: list):
        """Baut eine OTIO-Timeline aus den Auto-Edit Segmenten."""
        audio_id = self.audio_combo.currentData()
        tls = TimelineService(fps=30.0)
        tls.create_timeline("PB Studio Auto-Edit")

        # Audio-Track hinzufuegen
        if audio_id is not None:
            with DBSession(engine) as session:
                track = session.get(AudioTrack, audio_id)
                if track:
                    audio_track = tls.get_audio_track()
                    tls.add_clip(
                        track=audio_track,
                        name=track.title or Path(track.file_path).stem,
                        media_path=track.file_path,
                        source_start=0.0,
                        source_duration=track.duration or 60.0,
                        available_duration=track.duration,
                    )

        # Video-Clips hinzufuegen
        video_track = tls.get_video_track()
        for seg in segments:
            source_duration = seg.get("source_end", seg["end"]) - seg.get("source_start", seg["start"])
            metadata = {}
            if seg.get("is_anchor"):
                metadata = {"scene_id": seg.get("scene_id", ""), "type": "anchor"}

            tls.add_clip(
                track=video_track,
                name=Path(seg["video_path"]).stem if seg.get("video_path") else f"clip_{seg['video_id']}",
                media_path=seg.get("video_path", ""),
                source_start=seg.get("source_start", 0.0),
                source_duration=source_duration,
                metadata=metadata if metadata else None,
            )

        # Anker als OTIO Marker speichern
        anchors = self._collect_anchors_from_ui()
        for anchor in anchors:
            tls.add_marker(
                name=f"Anchor_{anchor['scene_id']}",
                time=anchor["time"],
                color="MAGENTA",
                metadata={
                    "scene_id": anchor["scene_id"],
                    "type": "anchor",
                },
            )

        # Speichern
        self._otio_timeline_service = tls
        otio_path = tls.save_otio("exports/auto_edit_phase3.otio")
        self.console_text.append(f"[OTIO] Timeline gespeichert: {otio_path}")

    def _on_auto_edit_error(self, error_msg: str, task_id: str):
        self.btn_auto_edit.setEnabled(True)
        self.btn_auto_edit.setText("Auto-Edit")
        self.console_text.append(f"[Auto-Edit Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Phase 3: Anchor System
    # ==================================================================

    def _collect_anchors_from_ui(self) -> list[dict]:
        """Sammelt alle Anker aus der Anchor-Liste im Inspector."""
        anchors = []
        for i in range(self.anchor_list.topLevelItemCount()):
            item = self.anchor_list.topLevelItem(i)
            time_text = item.text(0)
            scene_id = item.data(0, Qt.ItemDataRole.UserRole) or ""
            try:
                # Parse "MM:SS.ss" or plain seconds
                if ":" in time_text:
                    parts = time_text.replace("s", "").split(":")
                    time_sec = float(parts[0]) * 60 + float(parts[1])
                else:
                    time_sec = float(time_text.replace("s", ""))
                anchors.append({"time": time_sec, "scene_id": str(scene_id)})
            except (ValueError, IndexError):
                continue
        return anchors

    def _add_anchor_dialog(self):
        """Oeffnet einen Dialog zum Hinzufuegen eines neuen Audio-Ankers."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Anker hinzufuegen")
        dialog.setFixedSize(320, 180)
        dialog.setStyleSheet("background-color: #1A1A1A; color: #E0E0E0;")
        layout = QVBoxLayout(dialog)

        # Zeitpunkt
        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Zeitpunkt (Sek):"))
        time_spin = QSpinBox()
        time_spin.setRange(0, 36000)
        time_spin.setValue(0)
        time_spin.setSuffix("s")
        time_row.addWidget(time_spin)
        layout.addLayout(time_row)

        # Video/Szene Auswahl
        scene_row = QHBoxLayout()
        scene_row.addWidget(QLabel("Video/Szene:"))
        scene_combo = QComboBox()
        scene_combo.addItem("-- Szene waehlen --", "")
        # Alle Szenen aus der DB laden
        with DBSession(engine) as session:
            clips = session.query(VideoClip).filter_by(project_id=1).all()
            for clip in clips:
                clip_name = Path(clip.file_path).stem[:20]
                for scene in clip.scenes:
                    label = (
                        f"{clip_name} | Szene {scene.id} "
                        f"({scene.start_time:.1f}-{scene.end_time:.1f}s)"
                    )
                    scene_combo.addItem(label, str(scene.id))
                # Falls keine Szenen: ganzen Clip anbieten
                if not clip.scenes:
                    scene_combo.addItem(f"{clip_name} (komplett)", f"clip_{clip.id}")
        scene_row.addWidget(scene_combo)
        layout.addLayout(scene_row)

        # OK/Cancel
        btn_row = QHBoxLayout()
        btn_ok = QPushButton("Hinzufuegen")
        btn_ok.setObjectName("btn_accent")
        btn_ok.clicked.connect(dialog.accept)
        btn_row.addWidget(btn_ok)
        btn_cancel = QPushButton("Abbrechen")
        btn_cancel.clicked.connect(dialog.reject)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            time_sec = time_spin.value()
            scene_id = scene_combo.currentData() or ""
            scene_label = scene_combo.currentText()

            # Zur Anchor-Liste hinzufuegen
            minutes = int(time_sec // 60)
            secs = time_sec % 60
            time_str = f"{minutes}:{secs:05.2f}"

            item = QTreeWidgetItem([time_str, scene_label[:30]])
            item.setData(0, Qt.ItemDataRole.UserRole, scene_id)
            self.anchor_list.addTopLevelItem(item)

            self.console_text.append(
                f"[Anchor] Anker bei {time_str} -> {scene_label}"
            )

    def _remove_selected_anchor(self):
        """Entfernt den ausgewaehlten Anker aus der Liste."""
        selected = self.anchor_list.currentItem()
        if selected:
            idx = self.anchor_list.indexOfTopLevelItem(selected)
            self.anchor_list.takeTopLevelItem(idx)
            self.console_text.append("[Anchor] Anker entfernt.")

    def _sync_anchors(self):
        """Anker synchronisieren — richtet Video-Clips an Audio-Ankern aus."""
        synced = self.timeline_view.sync_anchors()
        if synced:
            self.timeline_view.load_from_db()
            self.console_text.append(
                "[Anchor] Anker synchronisiert — Video-Clips an Audio-Ankern ausgerichtet."
            )
        else:
            self.console_text.append(
                "[Anchor] Keine Anker gefunden. Setze Anker auf Audio- und Video-Clips "
                "(Rechtsklick oder Taste M), dann klicke erneut."
            )

    def _show_keyframe_strings(self):
        """Phase 3: Generiert und zeigt die Keyframe-Strings aller Video-Clips."""
        try:
            kf_string = generate_keyframe_strings_for_project(project_id=1)
            self.keyframe_text.setPlainText(kf_string)
            self.console_text.append("[Pacing] Keyframe-Strings generiert.")
        except Exception as e:
            self.keyframe_text.setPlainText(f"Fehler: {e}")
            self.console_text.append(f"[Pacing-Fehler] Keyframe-Strings: {e}")

    def _on_timeline_clip_moved(self, entry_id: int, new_start: float):
        self.console_text.append(
            f"[Timeline] Clip {entry_id} verschoben -> Start: {new_start:.2f}s"
        )

    # ==================================================================
    # Zur Timeline hinzufuegen
    # ==================================================================

    def _add_selected_to_timeline(self):
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return

        media_type = self.media_table.item(row, 1).text()
        media_id = int(self.media_table.item(row, 0).text())
        title = self.media_table.item(row, 2).text()

        track_type = "audio" if media_type == "Audio" else "video"

        with DBSession(engine) as session:
            existing = (
                session.query(TimelineEntry)
                .filter_by(project_id=1, track=track_type)
                .order_by(TimelineEntry.start_time.desc())
                .first()
            )
            start_time = 0.0
            if existing and existing.end_time:
                start_time = existing.end_time

            if track_type == "audio":
                obj = session.get(AudioTrack, media_id)
                duration = obj.duration if obj and obj.duration else 30.0
            else:
                obj = session.get(VideoClip, media_id)
                duration = obj.duration if obj and obj.duration else 10.0

            entry = TimelineEntry(
                project_id=1,
                track=track_type,
                media_id=media_id,
                start_time=round(start_time, 3),
                end_time=round(start_time + duration, 3),
                lane=0,
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            entry_id = entry.id

        self.timeline_view.add_clip(
            entry_id=entry_id,
            media_id=media_id,
            track_type=track_type,
            title=title,
            start_time=start_time,
            duration=duration,
        )

        self.console_text.append(
            f"[Timeline] {media_type} '{title}' hinzugefuegt bei {start_time:.1f}s "
            f"(Dauer: {duration:.1f}s)"
        )

        # Automatisch zum EDIT Workspace wechseln
        self.nav_bar.set_workspace(1)

    # ==================================================================
    # Pool-Selection → Hidden media_table Sync
    # ==================================================================

    def _on_video_pool_selected(self, row, col, prev_row, prev_col):
        """Sync video pool selection to hidden media_table."""
        if row < 0:
            return
        vid_id_item = self.video_pool_table.item(row, 0)
        if not vid_id_item:
            return
        vid_id = vid_id_item.text()
        for r in range(self.media_table.rowCount()):
            item = self.media_table.item(r, 0)
            type_item = self.media_table.item(r, 1)
            if item and type_item and item.text() == vid_id and type_item.text() == "Video":
                self.media_table.setCurrentCell(r, 0)
                break

    def _on_audio_pool_selected(self, row, col, prev_row, prev_col):
        """Sync audio pool selection to hidden media_table + StemWorkspace."""
        if row < 0:
            self.stem_player.stop()
            if hasattr(self, "stem_workspace"):
                self.stem_workspace.update_for_track(None, None)
            return
        aud_id_item = self.audio_pool_table.item(row, 0)
        if not aud_id_item:
            self.stem_player.stop()
            if hasattr(self, "stem_workspace"):
                self.stem_workspace.update_for_track(None, None)
            return
        aud_id = aud_id_item.text()
        for r in range(self.media_table.rowCount()):
            item = self.media_table.item(r, 0)
            type_item = self.media_table.item(r, 1)
            if item and type_item and item.text() == aud_id and type_item.text() == "Audio":
                self.media_table.setCurrentCell(r, 0)
                break

        # Stem Workspace aktualisieren
        self._update_stem_workspace(int(aud_id))

    def _on_stem_playback_finished(self):
        """[I-10 FIX] Benannte Methode für playback_finished — reset Position."""
        if hasattr(self, "stem_workspace"):
            self.stem_workspace.update_position(0.0)

    def _update_stem_workspace(self, track_id: int):
        """Lädt Stem-Pfade aus der DB, aktualisiert StemWorkspace und Player."""
        try:
            with DBSession(engine) as session:
                track = session.query(AudioTrack).filter_by(id=track_id).first()
                if not track:
                    if hasattr(self, "stem_workspace"):
                        self.stem_workspace.update_for_track(None, None)
                    self.stem_player.stop()
                    return
                stem_paths = {
                    "vocals": track.stem_vocals_path,
                    "drums": track.stem_drums_path,
                    "bass": track.stem_bass_path,
                    "other": track.stem_other_path,
                }

                if self.stem_player.load_stems(stem_paths):
                    if hasattr(self, "stem_workspace"):
                        self.stem_workspace.update_for_track(track_id, stem_paths)
                        self.stem_workspace.set_duration(self.stem_player.duration)
                    self.console_text.append(
                        f"[StemPlayer] Track #{track_id} geladen: "
                        f"{self.stem_player.duration:.1f}s"
                    )
                else:
                    if hasattr(self, "stem_workspace"):
                        self.stem_workspace.update_for_track(track_id, stem_paths)
        except Exception as e:
            self.console_text.append(f"[Stem-Widget] Fehler: {e}")
            if hasattr(self, "stem_workspace"):
                self.stem_workspace.update_for_track(None, None)

    # ==================================================================
    # Import-Logik
    # ==================================================================

    def _import_video(self):
        ext_filter = "Video-Dateien (" + " ".join(f"*{e}" for e in VIDEO_EXTENSIONS) + ")"
        paths, _ = QFileDialog.getOpenFileNames(self, "Videos importieren", "", ext_filter)
        self._process_imports(paths, "video")

    def _import_audio(self):
        ext_filter = "Audio-Dateien (" + " ".join(f"*{e}" for e in AUDIO_EXTENSIONS) + ")"
        paths, _ = QFileDialog.getOpenFileNames(self, "Audio importieren", "", ext_filter)
        self._process_imports(paths, "audio")

    def _process_imports(self, paths: list[str], media_type: str):
        if not paths:
            return
        added = 0
        new_video_clips = []  # (clip_id, file_path, title) for proxy creation
        for p in paths:
            if media_type == "audio":
                result = ingest_audio(p)
            else:
                result = ingest_video(p)
            name = Path(p).name
            if result is None:
                self.console_text.append(f"[Warnung] Datei bereits importiert: {name}")
            else:
                self.console_text.append(f"[Ingest] {media_type.capitalize()} importiert: {name}")
                added += 1
                # Phase 2: Proxy-Erstellung für neue Videos triggern
                if media_type == "video" and hasattr(result, 'id'):
                    new_video_clips.append((result.id, str(Path(p).resolve()), name))
        if added:
            self._refresh_media_table()
            self._refresh_director_combos()
            self.status_bar.showMessage(f"{added} Datei(en) importiert | System bereit")

            # Phase 2 (SEKTOR 2): Auto-Proxy für jedes neue Video
            for clip_id, video_path, title in new_video_clips:
                self._start_proxy_creation(clip_id, video_path, title)

    def _import_folder(self):
        """Importiert alle unterstuetzten Medien aus einem Ordner (rekursiv)."""
        folder = QFileDialog.getExistingDirectory(self, "Ordner importieren")
        if not folder:
            return
        all_exts = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
        paths_audio: list[str] = []
        paths_video: list[str] = []
        for root, _dirs, files in os.walk(folder):
            for f in files:
                ext = Path(f).suffix.lower()
                full = os.path.join(root, f)
                if ext in AUDIO_EXTENSIONS:
                    paths_audio.append(full)
                elif ext in VIDEO_EXTENSIONS:
                    paths_video.append(full)
        total = len(paths_audio) + len(paths_video)
        if total == 0:
            self.console_text.append(f"[Warnung] Keine unterstuetzten Medien in: {folder}")
            return
        self.console_text.append(f"[Ordner] {total} Dateien gefunden in: {folder}")
        self._process_imports(paths_audio, "audio")
        self._process_imports(paths_video, "video")

    def _clear_all_media(self):
        """Loescht alle Medien aus Datenbank und UI."""
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Sammlung bereinigen",
            "Alle Medien aus der Datenbank entfernen?\nDie Original-Dateien bleiben erhalten.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            count = delete_all_media()
            self._refresh_media_table()
            self._refresh_director_combos()
            self.console_text.append(f"[System] {count} Medien-Eintraege geloescht.")
            self.status_bar.showMessage(f"Sammlung bereinigt ({count} Eintraege) | System bereit")

    # ==================================================================
    # Audio-Analyse
    # ==================================================================

    def _analyze_selected_audio(self):
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return
        media_type = self.media_table.item(row, 1).text()
        if media_type != "Audio":
            self.console_text.append("[Warnung] Nur Audio-Dateien koennen analysiert werden.")
            return
        track_id = int(self.media_table.item(row, 0).text())
        title = self.media_table.item(row, 2).text()

        task = task_manager.create_task(f"Audio: {title}", "BPM + Beat-Analyse")

        worker = AnalysisWorker(track_id, title)
        worker.task_id = task.task_id
        worker.started.connect(self._on_analysis_started)
        worker.finished.connect(lambda tid, r: self._on_analysis_finished(tid, r, task.task_id))
        worker.error.connect(lambda tid, err: self._on_analysis_error(tid, err, task.task_id))
        worker.progress.connect(lambda pct, msg: self.console_text.append(f"[Audio] {msg}"))

        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setText("Analyse laeuft...")
        self.progress_bar.setVisible(True)

        self._start_worker_thread(worker)

    def _on_analysis_started(self, track_id: int, title: str):
        self.console_text.append(f"[Audio] Analysiere '{title}'...")
        self.status_bar.showMessage(f"Audio-Analyse: {title}")

    def _on_analysis_finished(self, track_id: int, result: dict, task_id: str = ""):
        if not result:
            return  # Error-path fallback — _on_analysis_error already handled this
        bpm = result["bpm"]
        duration = result["duration"]
        beats = len(result.get("beat_positions", []))
        self.console_text.append(
            f"[Audio] Analyse fertig: {bpm} BPM | Dauer: {duration}s | "
            f"Beats: {beats} | Energie-Punkte: {len(result['energy_curve'])}"
        )
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("Audio analysieren")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Analyse abgeschlossen | System bereit")
        self._refresh_media_table()
        self._refresh_director_combos()
        if task_id:
            task_manager.finish_task(task_id, "finished", f"{bpm} BPM, {beats} Beats")

    def _on_analysis_error(self, track_id: int, error_msg: str, task_id: str = ""):
        self.console_text.append(f"[Fehler] Audio-Analyse fehlgeschlagen (ID {track_id}): {error_msg}")
        self.btn_analyze.setEnabled(True)
        self.btn_analyze.setText("Audio analysieren")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Analyse-Fehler | System bereit")
        if task_id:
            task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Rekordbox Waveform-Analyse
    # ==================================================================

    def _analyze_waveform(self):
        """Startet Rekordbox-Style Frequenzanalyse für den ausgewählten Audio-Track."""
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return
        media_type = self.media_table.item(row, 1).text()
        if media_type != "Audio":
            self.console_text.append("[Warnung] Wellenform-Analyse nur fuer Audio-Dateien.")
            return
        track_id = int(self.media_table.item(row, 0).text())
        title = self.media_table.item(row, 2).text()

        task = task_manager.create_task(
            f"Waveform: {title}", "Rekordbox Frequenz-Wellenform + Beatgrid"
        )

        worker = WaveformAnalysisWorker(track_id)
        worker.task_id = task.task_id
        worker.progress.connect(
            lambda pct, msg: self._on_waveform_progress(pct, msg, task.task_id)
        )
        worker.finished.connect(
            lambda tid, r: self._on_waveform_finished(tid, r, title, task.task_id)
        )
        worker.error.connect(
            lambda tid, err: self._on_waveform_error(tid, err, task.task_id)
        )

        self.btn_waveform.setEnabled(False)
        self.btn_waveform.setText("Analyse laeuft...")
        self.progress_bar.setVisible(True)
        self.console_text.append(f"[Waveform] Starte Rekordbox-Analyse fuer '{title}'...")

        self._start_worker_thread(worker)

    def _on_waveform_progress(self, pct: int, msg: str, task_id: str):
        # update_task wird automatisch durch die Task-Engine gemacht
        self.console_text.append(f"[Waveform] {msg} ({pct}%)")

    def _on_waveform_finished(self, track_id: int, result: dict, title: str, task_id: str):
        if not result:
            return  # Error-path fallback — _on_waveform_error already handled this
        bpm = result["bpm"]
        beats = len(result.get("beat_positions", []))
        samples = result["num_samples"]
        self.console_text.append(
            f"[Waveform] Rekordbox-Analyse fertig: '{title}' | {bpm} BPM | "
            f"{beats} Beats | {samples} Wellenform-Samples (Low/Mid/High)"
        )
        self.btn_waveform.setEnabled(True)
        self.btn_waveform.setText("Rekordbox Wellenform")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(f"Wellenform fertig: {title} | {bpm} BPM")
        self._refresh_media_table()

        # Timeline neu laden, damit die Wellenform sichtbar wird
        self.timeline_view.load_from_db()

        if task_id:
            task_manager.finish_task(
                task_id, "finished",
                f"{bpm} BPM, {beats} Beats, {samples} Samples"
            )

    def _on_waveform_error(self, track_id: int, error_msg: str, task_id: str):
        self.console_text.append(
            f"[Fehler] Wellenform-Analyse fehlgeschlagen (ID {track_id}): {error_msg}"
        )
        self.btn_waveform.setEnabled(True)
        self.btn_waveform.setText("Rekordbox Wellenform")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Wellenform-Fehler | System bereit")
        if task_id:
            task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Video-Analyse
    # ==================================================================

    def _analyze_selected_video(self):
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return
        media_type = self.media_table.item(row, 1).text()
        if media_type != "Video":
            self.console_text.append("[Warnung] Nur Video-Dateien koennen hier analysiert werden.")
            return
        clip_id = int(self.media_table.item(row, 0).text())
        title = self.media_table.item(row, 2).text()

        task = task_manager.create_task(f"Video: {title}", "Metadaten + Proxy")

        worker = VideoAnalysisWorker(clip_id, title)
        worker.task_id = task.task_id
        worker.started.connect(self._on_video_analysis_started)
        worker.finished.connect(lambda cid, r: self._on_video_analysis_finished(cid, r, task.task_id))
        worker.error.connect(lambda cid, err: self._on_video_analysis_error(cid, err, task.task_id))

        self.btn_analyze_video.setEnabled(False)
        self.btn_analyze_video.setText("Analyse laeuft...")
        self.progress_bar.setVisible(True)

        self._start_worker_thread(worker)

    def _on_video_analysis_started(self, clip_id: int, title: str):
        self.console_text.append(f"[Video] Analysiere '{title}'...")
        self.status_bar.showMessage(f"Video-Analyse: {title}")

    def _on_video_analysis_finished(self, clip_id: int, result: dict, task_id: str = ""):
        if not result:
            return  # Error-path fallback — _on_video_analysis_error already handled this
        self.console_text.append(
            f"[Video] Analyse fertig: {result['width']}x{result['height']} | "
            f"{result['fps']} FPS | Dauer: {result.get('duration', '?')}s | Codec: {result['codec']}"
        )
        if "proxy_path" in result:
            self.console_text.append(f"[Video] Proxy erstellt: {result['proxy_path']}")
        self.btn_analyze_video.setEnabled(True)
        self.btn_analyze_video.setText("Video analysieren")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Video-Analyse abgeschlossen | System bereit")
        self._refresh_media_table()
        self._refresh_director_combos()
        if task_id:
            task_manager.finish_task(task_id, "finished",
                                     f"{result['width']}x{result['height']} {result['fps']}fps")

    def _on_video_analysis_error(self, clip_id: int, error_msg: str, task_id: str = ""):
        self.console_text.append(f"[Fehler] Video-Analyse fehlgeschlagen (ID {clip_id}): {error_msg}")
        self.btn_analyze_video.setEnabled(True)
        self.btn_analyze_video.setText("Video analysieren")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Video-Analyse-Fehler | System bereit")
        if task_id:
            task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Phase 2: Video Analysis Pipeline (SEKTOR 1)
    # ==================================================================

    def _start_video_pipeline(self):
        """Startet die 3-Schritt Video-Analyse-Pipeline für ALLE ausgewählten Videos.

        Liest alle markierten Zeilen im Video Pool aus und übergibt sie
        als Batch an den Worker. Sequenzielle Abarbeitung (6GB VRAM).
        """
        # SEKTOR 1: Alle selektierten Zeilen im Video Pool auslesen
        selected_rows = set()
        for index in self.video_pool_table.selectionModel().selectedRows():
            selected_rows.add(index.row())
        if not selected_rows:
            # Fallback: aktuelle Zeile
            row = self.video_pool_table.currentRow()
            if row >= 0:
                selected_rows.add(row)
        if not selected_rows:
            self.console_text.append("[Warnung] Keine Zeile im Video Pool ausgewaehlt.")
            return

        # Clip-IDs und Pfade aus der Video Pool Tabelle sammeln
        batch = []
        with DBSession(engine) as session:
            for row in sorted(selected_rows):
                id_item = self.video_pool_table.item(row, 0)
                title_item = self.video_pool_table.item(row, 1)
                if not id_item:
                    continue
                clip_id = int(id_item.text())
                title = title_item.text() if title_item else f"Clip {clip_id}"

                clip = session.get(VideoClip, clip_id)
                if not clip:
                    self.console_text.append(f"[Fehler] VideoClip {clip_id} nicht gefunden.")
                    continue
                batch.append((clip_id, clip.file_path, title))

        if not batch:
            self.console_text.append("[Warnung] Keine gültigen Videos in der Auswahl.")
            return

        # SEKTOR 2: Batch-Task erstellen
        count = len(batch)
        label = batch[0][2] if count == 1 else f"{count} Videos"
        task = task_manager.create_task(
            f"Pipeline: {label}",
            f"Batch-Analyse: {count} Video(s) — Szenen + Motion + SigLIP"
        )

        self.btn_video_pipeline.setEnabled(False)
        self.btn_video_pipeline.setText(f"Pipeline laeuft ({count})...")
        self.progress_bar.setVisible(True)

        titles_str = ", ".join(t for _, _, t in batch[:3])
        if count > 3:
            titles_str += f" (+{count - 3} weitere)"
        self.console_text.append(
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

        self._start_worker_thread(worker)

    def _on_pipeline_progress(self, pct: int, msg: str, task_id: str):
        # update_task wird automatisch durch die Task-Engine gemacht
        self.console_text.append(f"[Pipeline] {msg} ({pct}%)")

    def _on_pipeline_finished(self, clip_id: int, result: dict, title: str, task_id: str):
        if not result:
            return  # Error-path fallback — _on_pipeline_error already handled this
        scenes = result.get("scenes", 0)
        embeddings = result.get("embeddings", 0)
        videos_done = result.get("videos_processed", 1)
        self.console_text.append(
            f"[Pipeline] Fertig: {title} — {videos_done} Video(s), "
            f"{scenes} Szenen, {embeddings} Embeddings in LanceDB"
        )
        self.btn_video_pipeline.setEnabled(True)
        self.btn_video_pipeline.setText("Video-Pipeline (Szenen + KI)")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage(
            f"Pipeline fertig: {title} | {videos_done} Video(s), "
            f"{scenes} Szenen, {embeddings} Embeddings"
        )
        self._refresh_media_table()
        if task_id:
            task_manager.finish_task(
                task_id, "finished",
                f"{videos_done} Video(s), {scenes} Szenen, {embeddings} Embeddings"
            )

    def _on_pipeline_error(self, clip_id: int, error_msg: str, task_id: str):
        self.console_text.append(f"[Pipeline-Fehler] VideoClip {clip_id}: {error_msg}")
        self.btn_video_pipeline.setEnabled(True)
        self.btn_video_pipeline.setText("Video-Pipeline (Szenen + KI)")
        self.progress_bar.setVisible(False)
        self.status_bar.showMessage("Pipeline-Fehler | System bereit")
        if task_id:
            task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Phase 2: Proxy Creation (SEKTOR 2)
    # ==================================================================

    def _start_proxy_creation(self, clip_id: int, video_path: str, title: str):
        """Startet NVENC Proxy-Erstellung im Hintergrund."""
        task = task_manager.create_task(
            f"Proxy: {title}", "NVENC 540p Edit-Proxy"
        )
        self.console_text.append(f"[Proxy] Erstelle Edit-Proxy fuer '{title}'...")

        worker = ProxyCreationWorker(clip_id, video_path)
        worker.task_id = task.task_id
        worker.finished.connect(
            lambda cid, path: self._on_proxy_finished(cid, path, title, task.task_id)
        )
        worker.error.connect(
            lambda cid, err: self._on_proxy_error(cid, err, title, task.task_id)
        )

        self._start_worker_thread(worker)

    def _on_proxy_finished(self, clip_id: int, proxy_path: str, title: str, task_id: str):
        if not proxy_path:
            return  # Error-path fallback — _on_proxy_error already handled this
        self.console_text.append(f"[Proxy] Fertig: '{title}' → {proxy_path}")
        self._refresh_media_table()
        task_manager.finish_task(task_id, "finished", proxy_path)

    def _on_proxy_error(self, clip_id: int, error_msg: str, title: str, task_id: str):
        self.console_text.append(f"[Proxy-Fehler] '{title}': {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Phase 2: Semantic Search (SEKTOR 3)
    # ==================================================================

    def _run_semantic_search(self):
        """Startet SigLIP Text-zu-Video Suche."""
        query = self.search_input.text().strip()
        if not query:
            self.console_text.append("[Suche] Bitte Suchbegriff eingeben.")
            return

        self.btn_search.setEnabled(False)
        self.btn_search.setText("...")
        self.console_text.append(f"[Suche] SigLIP-Suche: '{query}'...")

        worker = SemanticSearchWorker(query, top_k=20)
        worker.finished.connect(self._on_search_finished)
        worker.error.connect(self._on_search_error)

        self._start_worker_thread(worker)

    def _on_search_finished(self, results: list):
        self.btn_search.setEnabled(True)
        self.btn_search.setText("Suchen")

        if not results:
            self.console_text.append("[Suche] Keine Ergebnisse gefunden.")
            return

        self.console_text.append(f"[Suche] {len(results)} Ergebnisse gefunden.")

        # Video Pool mit Suchergebnissen aktualisieren
        self.video_pool_table.setRowCount(len(results))
        for row, r in enumerate(results):
            video_name = Path(r["video_path"]).stem
            scene_info = f"Sz{r['scene_index']} ({r['scene_start']:.1f}-{r['scene_end']:.1f}s)"
            distance = f"{r['_distance']:.3f}"
            motion = f"{r['motion_score']:.2f}"

            self.video_pool_table.setItem(row, 0, QTableWidgetItem(str(r.get("id", ""))))
            self.video_pool_table.setItem(row, 1, QTableWidgetItem(video_name))
            self.video_pool_table.setItem(row, 2, QTableWidgetItem(scene_info))
            self.video_pool_table.setItem(row, 3, QTableWidgetItem(motion))
            self.video_pool_table.setItem(row, 4, QTableWidgetItem(distance))
            self.video_pool_table.setItem(row, 5, QTableWidgetItem(r["video_path"]))

    def _on_search_error(self, error_msg: str):
        self.btn_search.setEnabled(True)
        self.btn_search.setText("Suchen")
        self.console_text.append(f"[Suche-Fehler] {error_msg}")

    def _clear_search(self):
        """Suche zurücksetzen — normale Video-Pool Anzeige."""
        self.search_input.clear()
        self._refresh_media_table()
        self.console_text.append("[Suche] Zurückgesetzt — alle Videos angezeigt.")

    # ==================================================================
    # Stem Separation
    # ==================================================================

    def _start_stem_separation(self):
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return
        media_type = self.media_table.item(row, 1).text()
        if media_type != "Audio":
            self.console_text.append("[Warnung] Nur Audio-Dateien koennen separiert werden.")
            return
        track_id = int(self.media_table.item(row, 0).text())
        title = self.media_table.item(row, 2).text()

        task = task_manager.create_task(f"Stems: {title}", "KI Stem Separation (Demucs)")

        self.btn_stem_separate.setEnabled(False)
        self.btn_stem_separate.setText("Separation laeuft...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setFormat("KI-Separation laeuft... (kann mehrere Minuten dauern)")

        self.console_text.append(f"[Stems] Starte KI-Stem-Separation fuer '{title}'...")

        worker = StemSeparationWorker(track_id)
        worker.task_id = task.task_id  # Verknuepfung mit bestehendem Task
        worker.progress.connect(
            lambda pct, msg: self.console_text.append(f"[Stems] {msg} ({pct}%)")
        )
        worker.finished.connect(lambda tid, r: self._on_stem_finished(tid, r, task.task_id))
        worker.error.connect(lambda tid, err: self._on_stem_error(tid, err, task.task_id))

        self._start_worker_thread(worker)

    def _on_stem_finished(self, track_id: int, stems: dict, task_id: str):
        if not stems:
            return  # Error-path fallback — _on_stem_error already handled this
        self.btn_stem_separate.setEnabled(True)
        self.btn_stem_separate.setText("KI Stem Separation")
        self.progress_bar.setVisible(False)

        stem_list = [f"{k}: {('OK' if v else 'fehlt')}" for k, v in stems.items()]
        self.console_text.append(f"[Stems] Separation fertig: {', '.join(stem_list)}")
        self._refresh_media_table()
        self._update_stem_workspace(track_id)
        task_manager.finish_task(task_id, "finished", "Stems OK")

    def _on_stem_error(self, track_id: int, error_msg: str, task_id: str):
        self.btn_stem_separate.setEnabled(True)
        self.btn_stem_separate.setText("KI Stem Separation")
        self.progress_bar.setVisible(False)
        self.console_text.append(f"[Stem-Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Auto-Ducking
    # ==================================================================

    def _start_auto_ducking(self):
        row = self.media_table.currentRow()
        if row < 0:
            self.console_text.append("[Warnung] Keine Zeile ausgewaehlt.")
            return
        media_type = self.media_table.item(row, 1).text()
        if media_type != "Audio":
            self.console_text.append("[Warnung] Waehle einen Audio-Track mit Stems.")
            return
        track_id = int(self.media_table.item(row, 0).text())

        with DBSession(engine) as session:
            track = session.get(AudioTrack, track_id)
            if not track:
                return
            if not track.stem_vocals_path or not track.stem_other_path:
                self.console_text.append(
                    "[Ducking] Zuerst Stems separieren! (Vocals + Other benoetigt)"
                )
                return
            vocals_path = track.stem_vocals_path
            other_path = track.stem_other_path
            title = track.title

        output_path = str(Path("storage/ducked") / f"{title}_ducked.wav")
        task = task_manager.create_task(f"Ducking: {title}", "Auto-Ducking")

        self.btn_auto_duck.setEnabled(False)
        self.btn_auto_duck.setText("Ducking laeuft...")

        self.console_text.append(f"[Ducking] Starte Auto-Ducking fuer '{title}'...")

        worker = AutoDuckingWorker(other_path, vocals_path, output_path)
        worker.task_id = task.task_id
        worker.finished.connect(lambda p: self._on_ducking_finished(p, task.task_id))
        worker.error.connect(lambda err: self._on_ducking_error(err, task.task_id))

        self._start_worker_thread(worker)

    def _on_ducking_finished(self, output_path: str, task_id: str):
        if not output_path:
            return  # Error-path fallback — _on_ducking_error already handled this
        self.btn_auto_duck.setEnabled(True)
        self.btn_auto_duck.setText("Auto-Ducking")
        self.console_text.append(f"[Ducking] Fertig: {output_path}")
        task_manager.finish_task(task_id, "finished", f"Gespeichert: {output_path}")

    def _on_ducking_error(self, error_msg: str, task_id: str):
        self.btn_auto_duck.setEnabled(True)
        self.btn_auto_duck.setText("Auto-Ducking")
        self.console_text.append(f"[Ducking-Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)

    # ==================================================================
    # Production / Export
    # ==================================================================

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
            return  # Error-path fallback — _on_export_error already handled this
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

    def _cleanup_worker(self, thread: QThread, worker: QObject):
        """Entfernt Worker/Thread aus lokalen Listen.
        GC-Schutz liegt jetzt beim GlobalTaskManager (TaskInfo haelt Referenzen).
        """
        if worker in self._active_workers:
            self._active_workers.remove(worker)
        if thread in self._active_threads:
            self._active_threads.remove(thread)
        # Legacy-Liste auch aufräumen (falls noch Eintraege)
        pair = (thread, worker)
        if pair in _GLOBAL_ACTIVE_THREADS:
            _GLOBAL_ACTIVE_THREADS.remove(pair)

    # ==================================================================
    # Media-Tabelle
    # ==================================================================

    def _refresh_media_table(self):
        # Video Pool
        videos = get_all_video()
        self.video_pool_table.setRowCount(len(videos))
        for row, item in enumerate(videos):
            self.video_pool_table.setItem(row, 0, QTableWidgetItem(str(item["id"])))
            self.video_pool_table.setItem(row, 1, QTableWidgetItem(item["title"]))
            self.video_pool_table.setItem(row, 2, QTableWidgetItem(item.get("resolution") or "-"))
            fps_str = str(item.get("fps", "")) if item.get("fps") else "-"
            self.video_pool_table.setItem(row, 3, QTableWidgetItem(fps_str))
            self.video_pool_table.setItem(row, 4, QTableWidgetItem("-"))
            self.video_pool_table.setItem(row, 5, QTableWidgetItem(item["file_path"]))

        # Audio Pool
        audios = get_all_audio()
        self.audio_pool_table.setRowCount(len(audios))
        for row, item in enumerate(audios):
            self.audio_pool_table.setItem(row, 0, QTableWidgetItem(str(item["id"])))
            self.audio_pool_table.setItem(row, 1, QTableWidgetItem(item["title"]))
            bpm_str = str(item["bpm"]) if item.get("bpm") else "-"
            self.audio_pool_table.setItem(row, 2, QTableWidgetItem(bpm_str))
            self.audio_pool_table.setItem(row, 3, QTableWidgetItem("-"))
            self.audio_pool_table.setItem(row, 4, QTableWidgetItem(item.get("stems", "-")))
            self.audio_pool_table.setItem(row, 5, QTableWidgetItem(item["file_path"]))

        # Hidden proxy table (for legacy selection-based functions)
        media = get_all_media()
        self.media_table.setRowCount(len(media))
        for row, item in enumerate(media):
            self.media_table.setItem(row, 0, QTableWidgetItem(str(item["id"])))
            self.media_table.setItem(row, 1, QTableWidgetItem(item["type"]))
            self.media_table.setItem(row, 2, QTableWidgetItem(item["title"]))
            bpm_str = str(item["bpm"]) if item.get("bpm") else "-"
            self.media_table.setItem(row, 3, QTableWidgetItem(bpm_str))
            res = item.get("resolution", "-")
            self.media_table.setItem(row, 4, QTableWidgetItem(res or "-"))
            fps_str = str(item.get("fps", "")) if item.get("fps") else "-"
            self.media_table.setItem(row, 5, QTableWidgetItem(fps_str))
            stems = item.get("stems", "-")
            self.media_table.setItem(row, 6, QTableWidgetItem(stems))
            self.media_table.setItem(row, 7, QTableWidgetItem(item["file_path"]))

    # ==================================================================
    # System-Konsole & Chat Dock
    # ==================================================================

    def setup_task_dock(self):
        """TaskManager als fest verankertes QDockWidget am unteren Rand."""
        self.task_dock = TaskManagerDock(self)
        self.task_dock.cancel_requested.connect(self._cancel_worker_for_task)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.task_dock)
        self.task_dock.setVisible(True)
        self.task_dock.setFixedHeight(160)
        self.task_dock.show()

    def setup_console(self):
        dock = QDockWidget("System-Konsole", self)
        dock.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea)

        self.console_text = QTextEdit()
        self.console_text.setReadOnly(True)
        self.console_text.setMaximumHeight(160)
        self.console_text.setToolTip("System-Konsole: Zeigt alle Aktionen, Warnungen und Fehler der Anwendung in Echtzeit an")
        self.console_text.append("[System] PB_studio Core Engine erfolgreich gestartet.")

        dock.setWidget(self.console_text)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)

    def setup_chat_dock(self):
        self.chat_dock = ChatDock(self)
        self.chat_dock.setMinimumWidth(220)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.chat_dock)

        # MainWindow-Referenz für direkte Kommandos (analysiere, schneide, etc.)
        self.chat_dock.set_main_window(self)

        try:
            import services.register_actions  # noqa: F401
            from services.local_agent_service import LocalAgentService
            self._ai_agent = LocalAgentService()
            self.chat_dock.set_agent(self._ai_agent)

            # GPU-Status in Konsole und Chat anzeigen
            gpu_info = self._ai_agent.model_manager.gpu_info
            gpu_name = gpu_info.get("name", "unbekannt")
            vram = gpu_info.get("vram_total_mb", 0)

            if gpu_name != "CPU" and vram > 0:
                hw_msg = f"HARDWARE AKTIV: {gpu_name} ({vram:.0f} MB VRAM)"
                self.console_text.append(f"[GPU] {hw_msg}")
                self.chat_dock.append_system(
                    f"Agent bereit. {hw_msg}\n"
                    "Befehle: 'analysiere', 'schneide', 'gpu status'"
                )
            else:
                self.console_text.append("[GPU] Keine CUDA-GPU — CPU-Modus")
                self.chat_dock.append_system(
                    "Agent bereit (CPU-Modus).\n"
                    "Befehle: 'analysiere', 'schneide', 'gpu status'"
                )

            self.console_text.append("[KI] Chat-Assistent initialisiert (Modell wird bei erster Anfrage geladen).")
        except Exception as e:
            self.chat_dock.append_error(f"Agent konnte nicht initialisiert werden: {e}")
            self.console_text.append(f"[KI-Fehler] {e}")


def main():
    try:
        init_db()
    except Exception as exc:
        logging.basicConfig(level=logging.ERROR)
        logging.critical("Datenbank-Initialisierung fehlgeschlagen: %s", exc, exc_info=True)
        print(f"[FATAL] DB-Init fehlgeschlagen: {exc}")
        sys.exit(1)

    app = QApplication(sys.argv)

    # TaskManager als erstes erstellen und an QApplication verankern
    global task_manager
    task_manager = GlobalTaskManager.instance()
    app.task_manager = task_manager

    # Theme laden
    qss_path = RESOURCE_DIR / "styles.qss"
    if not qss_path.exists():
        qss_path = STYLE_DIR / "dark_steel.qss"
    if qss_path.exists():
        try:
            app.setStyleSheet(qss_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logging.warning("Theme konnte nicht geladen werden: %s", exc)

    try:
        window = PBWindow()
    except Exception as exc:
        logging.critical("Fenster-Initialisierung fehlgeschlagen: %s", exc, exc_info=True)
        print(f"[FATAL] Fenster konnte nicht erstellt werden: {exc}")
        traceback.print_exc()
        sys.exit(1)

    window.console_text.append("[System] SQLite Datenbank (pb_studio.db) erfolgreich initialisiert.")
    window.console_text.append("[System] DaVinci-Style UI geladen.")
    window.console_text.append(f"[System] Version {APP_VERSION} — Workspace UI + KI-Pacing.")
    window.showMaximized()
    # Timeline-Daten NACH dem Fenster laden (non-blocking Startup)
    QTimer.singleShot(0, window.timeline_view.load_from_db)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
