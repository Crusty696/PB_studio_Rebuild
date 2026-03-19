"""
PB_studio v0.4.0 — DaVinci Resolve Style UI Rebuild
=====================================================
4 Arbeitsbereiche: MEDIA | EDIT | EFFECTS | DELIVER
Bottom-Navigationsleiste wie DaVinci Resolve.
Optimierte Timeline mit Caching.
"""

import sys
import subprocess
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QStatusBar, QDockWidget, QTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QSplitter, QFileDialog, QHeaderView,
    QProgressBar, QLabel, QLineEdit, QSlider, QGroupBox,
    QComboBox, QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsTextItem, QGraphicsLineItem, QDialog, QFrame,
    QTreeWidget, QTreeWidgetItem, QCheckBox, QStackedWidget,
    QSizePolicy, QSpacerItem,
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QRectF, QPointF, QTimer
from PySide6.QtGui import QPainter, QPainterPath, QColor, QFont, QBrush, QPen, QPixmap, QImage

APP_VERSION = "0.4.0"
STYLE_DIR = Path(__file__).parent / "styles"
RESOURCE_DIR = Path(__file__).parent / "resources"

from database import init_db, engine, AudioTrack, VideoClip, TimelineEntry, Beatgrid, WaveformData
from sqlalchemy.orm import Session as DBSession
import json as _json
from services.ingest_service import (
    ingest_audio, ingest_video, get_all_media,
    AUDIO_EXTENSIONS, VIDEO_EXTENSIONS,
)
from services.audio_service import AudioAnalyzer
from services.video_service import VideoAnalyzer
from services.pacing_service import PacingSettings, calculate_cut_points, CutPoint, auto_edit_to_beats
from services.export_service import export_timeline, get_timeline_summary
from ui.chat_dock import ChatDock
from ui.waveform_item import WaveformGraphicsItem


# ======================================================================
# Phase 4: Globaler Task-Manager
# ======================================================================

class TaskInfo:
    """Beschreibt einen laufenden Hintergrund-Task."""
    def __init__(self, task_id: str, name: str, description: str = ""):
        self.task_id = task_id
        self.name = name
        self.description = description
        self.status = "running"
        self.progress = 0
        self.total = 0
        self.message = ""
        self.start_time = time.time()

    @property
    def elapsed(self) -> float:
        return round(time.time() - self.start_time, 1)


class GlobalTaskManager(QObject):
    """Verwaltet alle laufenden Hintergrund-Prozesse."""
    task_added = Signal(str)
    task_updated = Signal(str)
    task_finished = Signal(str)

    def __init__(self):
        super().__init__()
        self._tasks: dict[str, TaskInfo] = {}
        self._counter = 0

    def create_task(self, name: str, description: str = "") -> TaskInfo:
        self._counter += 1
        task_id = f"task_{self._counter}"
        task = TaskInfo(task_id, name, description)
        self._tasks[task_id] = task
        self.task_added.emit(task_id)
        return task

    def update_task(self, task_id: str, progress: int = 0, total: int = 0,
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

    def get_task(self, task_id: str) -> TaskInfo | None:
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[TaskInfo]:
        return list(self._tasks.values())

    def clear_finished(self):
        self._tasks = {k: v for k, v in self._tasks.items() if v.status == "running"}


task_manager = GlobalTaskManager()


# ======================================================================
# Background Workers
# ======================================================================

class AnalysisWorker(QObject):
    finished = Signal(int, dict)
    error = Signal(int, str)
    started = Signal(int, str)

    def __init__(self, track_id: int, title: str):
        super().__init__()
        self.track_id = track_id
        self.title = title
        self.analyzer = AudioAnalyzer()

    def run(self):
        self.started.emit(self.track_id, self.title)
        try:
            result = self.analyzer.analyze_and_store(self.track_id)
            self.finished.emit(self.track_id, result)
        except Exception as e:
            self.error.emit(self.track_id, str(e))


class VideoAnalysisWorker(QObject):
    finished = Signal(int, dict)
    error = Signal(int, str)
    started = Signal(int, str)

    def __init__(self, clip_id: int, title: str):
        super().__init__()
        self.clip_id = clip_id
        self.title = title
        self.analyzer = VideoAnalyzer()

    def run(self):
        self.started.emit(self.clip_id, self.title)
        try:
            result = self.analyzer.analyze_and_store(self.clip_id)
            self.finished.emit(self.clip_id, result)
        except Exception as e:
            self.error.emit(self.clip_id, str(e))


class StemSeparationWorker(QObject):
    finished = Signal(int, dict)
    error = Signal(int, str)
    progress = Signal(int, int, str)

    def __init__(self, track_id: int):
        super().__init__()
        self.track_id = track_id

    def run(self):
        try:
            from services.ai_audio_service import StemSeparator
            separator = StemSeparator()
            result = separator.separate_and_store(
                self.track_id,
                progress_cb=lambda s, t, m: self.progress.emit(s, t, m),
            )
            self.finished.emit(self.track_id, result)
        except Exception as e:
            self.error.emit(self.track_id, str(e))


class AutoDuckingWorker(QObject):
    finished = Signal(str)
    error = Signal(str)
    progress = Signal(int, int, str)

    def __init__(self, music_path: str, voice_path: str, output_path: str):
        super().__init__()
        self.music_path = music_path
        self.voice_path = voice_path
        self.output_path = output_path

    def run(self):
        try:
            from services.ai_audio_service import AutoDucker
            ducker = AutoDucker()
            result = ducker.create_ducked_audio(
                self.music_path, self.voice_path, self.output_path,
                progress_cb=lambda s, t, m: self.progress.emit(s, t, m),
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ExportWorker(QObject):
    finished = Signal(str)
    error = Signal(str)
    progress = Signal(int, int, str)

    def __init__(self, project_id: int, output_name: str,
                 resolution: str = "1920x1080", fps: float = 30.0):
        super().__init__()
        self.project_id = project_id
        self.output_name = output_name
        self.resolution = resolution
        self.fps = fps

    def run(self):
        try:
            path = export_timeline(
                project_id=self.project_id,
                output_name=self.output_name,
                resolution=self.resolution,
                fps=self.fps,
                progress_cb=lambda s, t, m: self.progress.emit(s, t, m),
            )
            self.finished.emit(path)
        except Exception as e:
            self.error.emit(str(e))


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
                self.error.emit(f"Frame @ {self.time_sec:.1f}s nicht verfuegbar")
        except Exception as e:
            self.error.emit(str(e))


class AutoEditWorker(QObject):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, audio_id: int, video_ids: list[int], total_duration: float):
        super().__init__()
        self.audio_id = audio_id
        self.video_ids = video_ids
        self.total_duration = total_duration

    def run(self):
        try:
            segments = auto_edit_to_beats(
                self.audio_id, self.video_ids, self.total_duration
            )
            self.finished.emit(segments)
        except Exception as e:
            self.error.emit(str(e))


class WaveformAnalysisWorker(QObject):
    """Background Worker: Rekordbox-Style Frequenzanalyse + Beatgrid."""
    finished = Signal(int, dict)   # track_id, result
    error = Signal(int, str)       # track_id, error_msg
    progress = Signal(int, int, str)

    def __init__(self, track_id: int):
        super().__init__()
        self.track_id = track_id

    def run(self):
        try:
            from services.ai_audio_service import FrequencyAnalyzer
            analyzer = FrequencyAnalyzer()
            result = analyzer.analyze_and_store(
                self.track_id,
                progress_cb=lambda s, t, m: self.progress.emit(s, t, m),
            )
            self.finished.emit(self.track_id, result)
        except Exception as e:
            self.error.emit(self.track_id, str(e))


# ======================================================================
# Draggable Timeline Clip (QGraphicsRectItem)
# ======================================================================

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

        # Performance: Caching und Optimierung (Sektor 3)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self.setOptimizationFlags(
            QGraphicsView.OptimizationFlag.DontSavePainterState
        )
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.SmartViewportUpdate
        )

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
            for entry in entries:
                has_waveform = False
                if entry.track == "audio":
                    track = session.get(AudioTrack, entry.media_id)
                    title = track.title if track else "?"
                    dur = track.duration if track and track.duration else 30.0
                    y = AUDIO_TRACK_Y

                    # Rekordbox Waveform laden (falls vorhanden)
                    if track and track.waveform_data:
                        has_waveform = True
                        self._load_waveform_for_track(session, track, entry, dur, y)

                elif entry.track == "video":
                    clip = session.get(VideoClip, entry.media_id)
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
        """Zoom mit Mausrad fuer smoothes Zoomen."""
        factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
        self.scale(factor, 1.0)


# ======================================================================
# Manual Pacing Curve Widget (drawable density over time)
# ======================================================================

class PacingCurveWidget(QWidget):
    """Drawable pacing density curve for manual cut-density override."""
    curve_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(55)
        self.setMaximumHeight(75)
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

        # Filled area under curve
        path = QPainterPath()
        path.moveTo(0, h)
        for i, d in enumerate(self._density):
            x = (i / (self._num_samples - 1)) * w
            y = h - (d * (h - 10))
            path.lineTo(x, y)
        path.lineTo(w, h)
        path.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 180, 212, 35))
        p.drawPath(path)

        # Curve line
        line_path = QPainterPath()
        for i, d in enumerate(self._density):
            x = (i / (self._num_samples - 1)) * w
            y = h - (d * (h - 10))
            if i == 0:
                line_path.moveTo(x, y)
            else:
                line_path.lineTo(x, y)
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
        # Brush radius for smooth drawing
        for offset in range(-3, 4):
            j = idx + offset
            if 0 <= j < self._num_samples:
                weight = 1.0 - abs(offset) / 4.0
                self._density[j] = self._density[j] * (1 - weight) + y_ratio * weight
        self.update()


# ======================================================================
# Video Preview Widget
# ======================================================================

class VideoPreviewWidget(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("video_preview")
        self.setMinimumSize(320, 180)
        self.setMaximumHeight(220)
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
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._frame_thread = thread
        self._frame_worker = worker
        thread.start()

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

class TaskManagerWidget(QTreeWidget):
    """Zeigt alle laufenden Hintergrund-Prozesse an."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderLabels(["Task", "Status", "Fortschritt", "Zeit"])
        self.setColumnCount(4)
        self.setAlternatingRowColors(True)
        self.setMaximumHeight(120)
        self.setToolTip("Hintergrund-Prozesse: Zeigt den Status aller laufenden Aufgaben wie Analyse, Export und KI-Verarbeitung")

        header = self.header()
        header.setStretchLastSection(True)
        header.resizeSection(0, 200)
        header.resizeSection(1, 80)
        header.resizeSection(2, 120)

        self._items: dict[str, QTreeWidgetItem] = {}

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._update_elapsed)
        self._timer.start()

        task_manager.task_added.connect(self._on_task_added)
        task_manager.task_updated.connect(self._on_task_updated)
        task_manager.task_finished.connect(self._on_task_finished)

    def _on_task_added(self, task_id: str):
        task = task_manager.get_task(task_id)
        if not task:
            return
        item = QTreeWidgetItem([task.name, "Running", "", "0s"])
        item.setForeground(1, QBrush(QColor(100, 200, 100)))
        self.addTopLevelItem(item)
        self._items[task_id] = item

    def _on_task_updated(self, task_id: str):
        task = task_manager.get_task(task_id)
        item = self._items.get(task_id)
        if not task or not item:
            return
        if task.total > 0:
            item.setText(2, f"{task.progress}/{task.total}: {task.message}")
        else:
            item.setText(2, task.message)

    def _on_task_finished(self, task_id: str):
        task = task_manager.get_task(task_id)
        item = self._items.get(task_id)
        if not task or not item:
            return
        if task.status == "finished":
            item.setText(1, "Done")
            item.setForeground(1, QBrush(QColor(100, 200, 255)))
        else:
            item.setText(1, "Error")
            item.setForeground(1, QBrush(QColor(255, 100, 100)))
        item.setText(2, task.message)
        item.setText(3, f"{task.elapsed}s")

    def _update_elapsed(self):
        for task_id, item in self._items.items():
            task = task_manager.get_task(task_id)
            if task and task.status == "running":
                item.setText(3, f"{task.elapsed}s")


# ======================================================================
# DaVinci-Style Workspace Navigation Bar
# ======================================================================

class WorkspaceNavBar(QWidget):
    """Bottom navigation bar — DaVinci Resolve Style."""
    workspace_changed = Signal(int)

    WORKSPACE_NAMES = ["MEDIA", "EDIT", "EFFECTS", "DELIVER"]

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
            "EFFECTS: Farbkorrektur, Video-Filter und Ueberblendungen",
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

        # ── Workspace Content (QStackedWidget) ──
        self.workspace_stack = QStackedWidget()
        main_layout.addWidget(self.workspace_stack, stretch=1)

        # Workspaces erstellen
        self.workspace_stack.addWidget(self._build_media_workspace())
        self.workspace_stack.addWidget(self._build_edit_workspace())
        self.workspace_stack.addWidget(self._build_effects_workspace())
        self.workspace_stack.addWidget(self._build_deliver_workspace())

        # ── Task Manager (kompakt, immer sichtbar) ──
        self.task_manager_widget = TaskManagerWidget()
        main_layout.addWidget(self.task_manager_widget)

        # ── Bottom Navigation Bar (DaVinci Style) ──
        self.nav_bar = WorkspaceNavBar()
        self.nav_bar.workspace_changed.connect(self.workspace_stack.setCurrentIndex)
        main_layout.addWidget(self.nav_bar)

        # ── Status Bar ──
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(f"PB_studio v{APP_VERSION} | System bereit")

        # ── Dock Widgets ──
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

        left_layout.addWidget(import_group)

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

        # ── Rechte Seite: Media-Tabelle ──
        self.media_table = QTableWidget()
        self.media_table.setColumnCount(8)
        self.media_table.setHorizontalHeaderLabels(
            ["ID", "Typ", "Titel", "BPM", "Aufloesung", "FPS", "Stems", "Dateipfad"]
        )
        self.media_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.media_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.media_table.setAlternatingRowColors(True)
        self.media_table.setToolTip("Mediathek: Alle importierten Dateien. Klicke eine Zeile an, um sie fuer Analyse oder Timeline auszuwaehlen")

        header = self.media_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)

        splitter.addWidget(self.media_table)
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
        self.video_preview.setMinimumSize(480, 270)
        self.video_preview.setMaximumHeight(16777215)
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
        self.inspector_panel = QWidget()
        self.inspector_panel.setObjectName("inspector_panel")
        self.inspector_panel.setMaximumWidth(260)
        self.inspector_panel.setMinimumWidth(200)
        insp = QVBoxLayout(self.inspector_panel)
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

        # Pacing sliders (horizontal, compact)
        pacing_lbl = QLabel("PACING")
        pacing_lbl.setStyleSheet("color: #505050; font-size: 9px; font-weight: 600; letter-spacing: 1px;")
        insp.addWidget(pacing_lbl)

        self.tempo_slider, tempo_row = self._create_compact_slider("Tempo", 0, 100, 50)
        insp.addLayout(tempo_row)

        self.energy_slider, energy_row = self._create_compact_slider("Energie", 0, 100, 50)
        insp.addLayout(energy_row)

        self.density_slider, density_row = self._create_compact_slider("Dichte", 0, 100, 50)
        insp.addLayout(density_row)

        self._add_separator(insp)

        # Action buttons
        self.btn_generate = QPushButton("Timeline generieren")
        self.btn_generate.setObjectName("btn_accent")
        self.btn_generate.setFixedHeight(30)
        self.btn_generate.setToolTip("Berechnet Schnittpunkte (BPM + Pacing-Kurve)")
        self.btn_generate.clicked.connect(self._generate_timeline)
        insp.addWidget(self.btn_generate)

        self.btn_auto_edit = QPushButton("Auto-Edit to Beat")
        self.btn_auto_edit.setObjectName("btn_accent")
        self.btn_auto_edit.setFixedHeight(30)
        self.btn_auto_edit.setToolTip("Schneidet Videos automatisch auf Drum-Beats")
        self.btn_auto_edit.clicked.connect(self._auto_edit_to_beat)
        insp.addWidget(self.btn_auto_edit)

        insp.addStretch()

        top_splitter.addWidget(self.inspector_panel)
        top_splitter.setStretchFactor(0, 5)
        top_splitter.setStretchFactor(1, 0)

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

        # Preview ~35%, Timeline area ~65% — timeline dominates
        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 3)

        layout.addWidget(main_splitter)

        self._refresh_director_combos()
        return workspace

    # ==================================================================
    # Workspace 3: EFFECTS
    # ==================================================================

    def _build_effects_workspace(self) -> QWidget:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(8, 8, 8, 4)

        # ── Oberer Bereich: Einstellungen + Vorschau ──
        top_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Linke Seite: Effekt-Einstellungen
        settings_panel = QWidget()
        settings_layout = QVBoxLayout(settings_panel)

        # Clip-Auswahl
        select_group = QGroupBox("Clip auswaehlen")
        select_layout = QHBoxLayout(select_group)
        clip_label = QLabel("Timeline-Clip:")
        clip_label.setToolTip("Waehle den Video-Clip aus der Timeline, auf den die Effekte angewendet werden sollen")
        select_layout.addWidget(clip_label)
        self.effects_clip_combo = QComboBox()
        self.effects_clip_combo.setToolTip("Liste aller Video-Clips auf der Timeline. Waehle einen Clip, um seine Effekt-Einstellungen zu laden und zu bearbeiten")
        self.effects_clip_combo.currentIndexChanged.connect(self._on_effects_clip_changed)
        select_layout.addWidget(self.effects_clip_combo)
        btn_refresh_effects = QPushButton("Aktualisieren")
        btn_refresh_effects.setToolTip("Laedt die Clip-Liste neu, z.B. nach dem Hinzufuegen neuer Clips zur Timeline")
        btn_refresh_effects.clicked.connect(self._refresh_effects_combos)
        select_layout.addWidget(btn_refresh_effects)
        settings_layout.addWidget(select_group)

        # Farbkorrektur
        color_group = QGroupBox("Farbkorrektur")
        color_layout = QVBoxLayout(color_group)

        bright_row = QHBoxLayout()
        bright_label = QLabel("Helligkeit:")
        bright_label.setToolTip("Regelt die Gesamthelligkeit des Clips. Negativ = dunkler, Positiv = heller")
        bright_row.addWidget(bright_label)
        self.brightness_slider = QSlider(Qt.Orientation.Horizontal)
        self.brightness_slider.setRange(-100, 100)
        self.brightness_slider.setValue(0)
        self.brightness_slider.setToolTip("Helligkeit anpassen: -1.00 (schwarz) bis +1.00 (weiss). Standard ist 0.00 (keine Aenderung)")
        self.brightness_label = QLabel("0.00")
        self.brightness_slider.valueChanged.connect(
            lambda v: self.brightness_label.setText(f"{v / 100:.2f}")
        )
        bright_row.addWidget(self.brightness_slider)
        bright_row.addWidget(self.brightness_label)
        color_layout.addLayout(bright_row)

        contrast_row = QHBoxLayout()
        contrast_label = QLabel("Kontrast:")
        contrast_label.setToolTip("Regelt den Kontrast des Clips. Unter 1.0 = flacher, Ueber 1.0 = knackiger")
        contrast_row.addWidget(contrast_label)
        self.contrast_slider = QSlider(Qt.Orientation.Horizontal)
        self.contrast_slider.setRange(0, 300)
        self.contrast_slider.setValue(100)
        self.contrast_slider.setToolTip("Kontrast anpassen: 0.00 (grau) bis 3.00 (extrem). Standard ist 1.00 (keine Aenderung)")
        self.contrast_label = QLabel("1.00")
        self.contrast_slider.valueChanged.connect(
            lambda v: self.contrast_label.setText(f"{v / 100:.2f}")
        )
        contrast_row.addWidget(self.contrast_slider)
        contrast_row.addWidget(self.contrast_label)
        color_layout.addLayout(contrast_row)

        settings_layout.addWidget(color_group)

        # Crossfade
        crossfade_group = QGroupBox("Ueberblendung (Crossfade)")
        crossfade_layout = QHBoxLayout(crossfade_group)
        cf_label = QLabel("Dauer:")
        cf_label.setToolTip("Dauer der Ueberblendung zwischen zwei aufeinanderfolgenden Clips")
        crossfade_layout.addWidget(cf_label)
        self.crossfade_slider = QSlider(Qt.Orientation.Horizontal)
        self.crossfade_slider.setRange(0, 30)
        self.crossfade_slider.setValue(0)
        self.crossfade_slider.setToolTip("Crossfade-Dauer in Sekunden: 0.0s (harter Schnitt) bis 3.0s (langsame Ueberblendung)")
        self.crossfade_label = QLabel("0.0s")
        self.crossfade_slider.valueChanged.connect(
            lambda v: self.crossfade_label.setText(f"{v / 10:.1f}s")
        )
        crossfade_layout.addWidget(self.crossfade_slider)
        crossfade_layout.addWidget(self.crossfade_label)
        settings_layout.addWidget(crossfade_group)

        # Anwenden
        btn_apply = QPushButton("Effekte auf Clip anwenden")
        btn_apply.setObjectName("btn_accent")
        btn_apply.setMinimumHeight(46)
        btn_apply.setToolTip("Speichert die eingestellten Effekte (Helligkeit, Kontrast, Crossfade) fuer den ausgewaehlten Clip in der Datenbank und zeigt eine Vorschau")
        btn_apply.clicked.connect(self._apply_effects)
        settings_layout.addWidget(btn_apply)

        settings_layout.addStretch()
        top_splitter.addWidget(settings_panel)

        # Rechte Seite: Effekt-Vorschau
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)

        preview_title = QLabel("Effekt-Vorschau")
        preview_title.setStyleSheet("color: #00F0FF; font-weight: 600; font-size: 12px;")
        preview_layout.addWidget(preview_title)

        self.effects_preview = QLabel("Waehle einen Clip und passe die Effekte an")
        self.effects_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.effects_preview.setMinimumSize(400, 300)
        self.effects_preview.setStyleSheet("background-color: #0A0A0A; border: 1px solid #1E1E1E; color: #404040;")
        self.effects_preview.setToolTip("Zeigt eine Vorschau des aktuellen Clips mit den angewendeten Farbkorrekturen. Aktualisiert sich nach Klick auf 'Effekte anwenden'")
        preview_layout.addWidget(self.effects_preview)

        preview_layout.addStretch()
        top_splitter.addWidget(preview_panel)

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
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)

        if on_finish:
            worker.finished.connect(on_finish)
        if on_error:
            worker.error.connect(on_error)

        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(lambda: self._cleanup_worker(thread, worker))

        self._active_threads.append(thread)
        self._active_workers.append(worker)
        thread.start()
        return thread

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
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.frame_ready.connect(self._on_effect_frame_ready)
        worker.error.connect(lambda msg: self.effects_preview.setText(msg))
        worker.frame_ready.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._active_threads.append(thread)
        thread.finished.connect(lambda: (
            self._active_threads.remove(thread) if thread in self._active_threads else None
        ))
        thread.start()

    def _on_effect_frame_ready(self, raw_data: bytes, width: int, height: int):
        img = QImage(raw_data, width, height, width * 3, QImage.Format.Format_RGB888)
        self.effects_preview.setPixmap(QPixmap.fromImage(img))

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

        settings = PacingSettings(
            tempo=self.tempo_slider.value(),
            energy=self.energy_slider.value(),
            cut_density=self.density_slider.value(),
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
        audio_id = self.audio_combo.currentData()
        if audio_id is None:
            self.console_text.append("[Auto-Edit] Kein Audio-Track ausgewaehlt.")
            return

        with DBSession(engine) as session:
            clips = session.query(VideoClip).filter_by(project_id=1).all()
            video_ids = [c.id for c in clips]
            track = session.get(AudioTrack, audio_id)
            total_dur = track.duration if track and track.duration else 60.0

        if not video_ids:
            self.console_text.append("[Auto-Edit] Keine Video-Clips vorhanden.")
            return

        task = task_manager.create_task("Auto-Edit to Beat", "Drum-basierter Automatik-Schnitt")
        self.console_text.append("[Auto-Edit] Starte drum-basierten Automatik-Schnitt...")
        self.btn_auto_edit.setEnabled(False)
        self.btn_auto_edit.setText("Auto-Edit\nlaeuft...")

        worker = AutoEditWorker(audio_id, video_ids, total_dur)
        worker.finished.connect(lambda segs: self._on_auto_edit_finished(segs, task.task_id))
        worker.error.connect(lambda err: self._on_auto_edit_error(err, task.task_id))

        self._start_worker_thread(worker)

    def _on_auto_edit_finished(self, segments: list, task_id: str):
        self.btn_auto_edit.setEnabled(True)
        self.btn_auto_edit.setText("Auto-Edit\nto Beat")

        if not segments:
            self.console_text.append("[Auto-Edit] Keine Segmente generiert.")
            task_manager.finish_task(task_id, "error", "Keine Segmente")
            return

        with DBSession(engine) as session:
            session.query(TimelineEntry).filter_by(
                project_id=1, track="video"
            ).delete()
            session.commit()

            for seg in segments:
                entry = TimelineEntry(
                    project_id=1,
                    track="video",
                    media_id=seg["video_id"],
                    start_time=seg["start"],
                    end_time=seg["end"],
                    lane=0,
                )
                session.add(entry)
            session.commit()

        self.timeline_view.load_from_db()
        self.console_text.append(
            f"[Auto-Edit] {len(segments)} Segmente auf Drum-Beats verteilt."
        )
        task_manager.finish_task(task_id, "finished", f"{len(segments)} Segmente")

    def _on_auto_edit_error(self, error_msg: str, task_id: str):
        self.btn_auto_edit.setEnabled(True)
        self.btn_auto_edit.setText("Auto-Edit\nto Beat")
        self.console_text.append(f"[Auto-Edit Fehler] {error_msg}")
        task_manager.finish_task(task_id, "error", error_msg)

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
        if added:
            self._refresh_media_table()
            self._refresh_director_combos()
            self.status_bar.showMessage(f"{added} Datei(en) importiert | System bereit")

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
        worker.started.connect(self._on_analysis_started)
        worker.finished.connect(lambda tid, r: self._on_analysis_finished(tid, r, task.task_id))
        worker.error.connect(lambda tid, err: self._on_analysis_error(tid, err, task.task_id))

        self.btn_analyze.setEnabled(False)
        self.btn_analyze.setText("Analyse laeuft...")
        self.progress_bar.setVisible(True)

        self._start_worker_thread(worker)

    def _on_analysis_started(self, track_id: int, title: str):
        self.console_text.append(f"[Audio] Analysiere '{title}'...")
        self.status_bar.showMessage(f"Audio-Analyse: {title}")

    def _on_analysis_finished(self, track_id: int, result: dict, task_id: str = ""):
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
        worker.progress.connect(
            lambda s, t, m: self._on_waveform_progress(s, t, m, task.task_id)
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

    def _on_waveform_progress(self, step: int, total: int, msg: str, task_id: str):
        task_manager.update_task(task_id, step, total, msg)
        self.console_text.append(f"[Waveform] {msg} ({step}/{total})")

    def _on_waveform_finished(self, track_id: int, result: dict, title: str, task_id: str):
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
        worker.progress.connect(
            lambda s, t, m: task_manager.update_task(task.task_id, s, t, m)
        )
        worker.finished.connect(lambda tid, r: self._on_stem_finished(tid, r, task.task_id))
        worker.error.connect(lambda tid, err: self._on_stem_error(tid, err, task.task_id))

        self._start_worker_thread(worker)

    def _on_stem_finished(self, track_id: int, stems: dict, task_id: str):
        self.btn_stem_separate.setEnabled(True)
        self.btn_stem_separate.setText("KI Stem Separation")
        self.progress_bar.setVisible(False)

        stem_list = [f"{k}: {('OK' if v else 'fehlt')}" for k, v in stems.items()]
        self.console_text.append(f"[Stems] Separation fertig: {', '.join(stem_list)}")
        self._refresh_media_table()
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
        worker.progress.connect(
            lambda s, t, m: task_manager.update_task(task.task_id, s, t, m)
        )
        worker.finished.connect(lambda p: self._on_ducking_finished(p, task.task_id))
        worker.error.connect(lambda err: self._on_ducking_error(err, task.task_id))

        self._start_worker_thread(worker)

    def _on_ducking_finished(self, output_path: str, task_id: str):
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
        worker.progress.connect(self._on_export_progress)
        worker.progress.connect(
            lambda s, t, m: task_manager.update_task(task.task_id, s, t, m)
        )
        worker.finished.connect(lambda p: self._on_export_finished(p, task.task_id))
        worker.error.connect(lambda err: self._on_export_error(err, task.task_id))

        self._start_worker_thread(worker)

    def _on_export_progress(self, step: int, total: int, message: str):
        self.export_progress.setRange(0, total)
        self.export_progress.setValue(step)
        self.export_log.append(f"[Export] {message} ({step}/{total})")

    def _on_export_finished(self, output_path: str, task_id: str = ""):
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
        if worker in self._active_workers:
            self._active_workers.remove(worker)
        if thread in self._active_threads:
            self._active_threads.remove(thread)
        worker.deleteLater()
        thread.deleteLater()

    # ==================================================================
    # Media-Tabelle
    # ==================================================================

    def _refresh_media_table(self):
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

        try:
            import services.register_actions  # noqa: F401
            from services.local_agent_service import LocalAgentService
            self._ai_agent = LocalAgentService()
            self.chat_dock.set_agent(self._ai_agent)
            self.chat_dock.append_system(
                "Lokaler Agent bereit. Was kann ich tun?"
            )
            self.console_text.append("[KI] Chat-Assistent initialisiert (Modell wird bei erster Anfrage geladen).")
        except Exception as e:
            self.chat_dock.append_error(f"Agent konnte nicht initialisiert werden: {e}")
            self.console_text.append(f"[KI-Fehler] {e}")


def main():
    init_db()
    app = QApplication(sys.argv)

    # Theme laden
    qss_path = RESOURCE_DIR / "styles.qss"
    if not qss_path.exists():
        qss_path = STYLE_DIR / "dark_steel.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))

    window = PBWindow()
    window.console_text.append("[System] SQLite Datenbank (pb_studio.db) erfolgreich initialisiert.")
    window.console_text.append("[System] DaVinci-Style UI geladen.")
    window.console_text.append(f"[System] Version {APP_VERSION} — Workspace UI + KI-Pacing.")
    window.timeline_view.load_from_db()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
