"""Interactive Timeline with draggable clips, anchors, beat markers and zoom."""

import bisect
import json
import logging
from collections import namedtuple
from pathlib import Path

from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsTextItem, QGraphicsLineItem, QGraphicsPolygonItem, QMenu,
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QBrush, QPen, QPolygonF, QUndoStack

from sqlalchemy.orm import Session as DBSession

from database import engine, AudioTrack, VideoClip, TimelineEntry, Beatgrid, ClipAnchor, StructureSegment, nullpool_session

logger = logging.getLogger(__name__)
from services.pacing_service import CutPoint
from ui.shortcut_manager import get_shortcut_manager
from ui.waveform_item import WaveformGraphicsItem

# MIME type for internal clip drag & drop (must match media_workspace.py)
CLIP_MIME_TYPE = "application/x-pb-studio-clip"

_EntryStub = namedtuple("_EntryStub", ["start_time"])

# ======================================================================
# Constants
# ======================================================================

PIXELS_PER_SECOND = 20
TRACK_HEIGHT = 50
AUDIO_TRACK_Y = 10
VIDEO_TRACK_Y = AUDIO_TRACK_Y + TRACK_HEIGHT + 10
CUT_MARKERS_Y = VIDEO_TRACK_Y + TRACK_HEIGHT + 10
RULER_Y = CUT_MARKERS_Y + 30


# ======================================================================
# Anchor Marker
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


# ======================================================================
# Draggable Timeline Clip
# ======================================================================

class TimelineClipItem(QGraphicsRectItem):
    # Audio-Clips: refined slate blue
    AUDIO_COLOR = QColor(45, 85, 150, 80)
    AUDIO_COLOR_NO_WAVEFORM = QColor(60, 100, 180, 210)
    # Video-Clips: Premium Gold / Amber
    VIDEO_COLOR = QColor(212, 164, 74, 210)

    TRIM_ZONE = 6  # px from edge to activate trim handle

    def __init__(self, entry_id: int, media_id: int, track_type: str,
                 title: str, x: float, y: float, width: float, height: float,
                 on_moved=None, on_trimmed=None, has_waveform: bool = False,
                 anchors: list | None = None):
        super().__init__(QRectF(0, 0, width, height))
        self.entry_id = entry_id
        self.media_id = media_id
        self.track_type = track_type
        self.title = title  # stored for copy/paste (AUD-71)
        self.on_moved = on_moved
        self.on_trimmed = on_trimmed
        self._clip_width = width
        self._clip_height = height

        # State initialization (MUST happen before setFlag/setPos)
        self._trim_mode: str | None = None  # "left", "right", or None
        self._trim_start_mouse_x: float = 0.0
        self._trim_start_width: float = 0.0
        self._trim_start_pos_x: float = 0.0
        self._drag_start_x: float | None = None
        self._drag_duration: float | None = None  # H-34 fix: cache duration for non-blocking flush

        self.setPos(x, y)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)

        if track_type == "audio":
            color = self.AUDIO_COLOR if has_waveform else self.AUDIO_COLOR_NO_WAVEFORM
        else:
            color = self.VIDEO_COLOR
        self._base_color = color
        self.setBrush(QBrush(color))
        self.setPen(QPen(color.darker(120), 1))
        self.setZValue(2)  # Über der Wellenform

        label = QGraphicsTextItem(title[:30], self)
        label.setDefaultTextColor(QColor(255, 255, 255))
        label.setFont(QFont("Segoe UI Variable Text", 8, QFont.Weight.Bold))
        label.setPos(4, 2)

        # Trim handle visuals (thin colored bars at edges)
        trim_color = QColor(255, 255, 255, 100)
        self._left_handle = QGraphicsRectItem(QRectF(0, 0, 3, height), self)
        self._left_handle.setBrush(QBrush(trim_color))
        self._left_handle.setPen(QPen(Qt.PenStyle.NoPen))
        self._left_handle.setZValue(11)
        self._left_handle.setVisible(False)
        self._right_handle = QGraphicsRectItem(QRectF(width - 3, 0, 3, height), self)
        self._right_handle.setBrush(QBrush(trim_color))
        self._right_handle.setPen(QPen(Qt.PenStyle.NoPen))
        self._right_handle.setZValue(11)
        self._right_handle.setVisible(False)

        self._track_y = y
        self._anchor_markers: list[AnchorMarkerItem] = []
        if anchors is not None:
            self._apply_anchors(anchors)
        else:
            self._load_anchors()

    def _apply_anchors(self, anchors):
        """Zeichnet vorab geladene Anker (vermeidet N+1 DB-Queries)."""
        for anchor in anchors:
            x_px = anchor.time_offset * PIXELS_PER_SECOND
            if 0 <= x_px <= self._clip_width:
                marker = AnchorMarkerItem(x_px, self._clip_height, anchor.id, parent=self)
                self._anchor_markers.append(marker)

    def _load_anchors(self):
        """Laedt bestehende Anker aus der DB und zeichnet sie."""
        with nullpool_session() as session:
            anchors = session.query(ClipAnchor).filter_by(
                timeline_entry_id=self.entry_id
            ).all()
            self._apply_anchors(anchors)

    def add_anchor_at(self, local_x: float) -> int | None:
        """Setzt einen neuen Anker an der lokalen X-Position (in Pixeln).
        Gibt die Anchor-ID zurueck oder None bei Fehler.
        """
        time_offset = local_x / PIXELS_PER_SECOND
        if time_offset < 0:
            time_offset = 0.0

        from database import nullpool_session
        with nullpool_session() as session:
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
        from database import nullpool_session
        with nullpool_session() as session:
            session.query(ClipAnchor).filter_by(
                timeline_entry_id=self.entry_id
            ).delete()
            session.commit()
        for m in self._anchor_markers:
            m.remove_from_scene()
        self._anchor_markers.clear()

    def get_first_anchor_time(self) -> float | None:
        """Gibt den Zeitstempel des ersten Ankers zurueck (relativ zum Clip-Start)."""
        with nullpool_session() as session:
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
            "QMenu::item:selected { background: rgba(212,175,55,0.15); color: #E8CC6A; }"
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

    def _detect_trim_edge(self, local_x: float) -> str | None:
        """Erkennt ob die Maus ueber einem Trim-Handle ist."""
        if local_x <= self.TRIM_ZONE:
            return "left"
        if local_x >= self._clip_width - self.TRIM_ZONE:
            return "right"
        return None

    def hoverMoveEvent(self, event):
        """Cursor aendern wenn ueber Trim-Handle."""
        edge = self._detect_trim_edge(event.pos().x())
        if edge:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            self._left_handle.setVisible(edge == "left")
            self._right_handle.setVisible(edge == "right")
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._left_handle.setVisible(False)
            self._right_handle.setVisible(False)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        """Cursor zuruecksetzen."""
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._left_handle.setVisible(False)
        self._right_handle.setVisible(False)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        """Trim-Modus starten wenn auf Handle geklickt."""
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._detect_trim_edge(event.pos().x())
            if edge:
                self._trim_mode = edge
                self._trim_start_mouse_x = event.scenePos().x()
                self._trim_start_width = self._clip_width
                self._trim_start_pos_x = self.pos().x()
                self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, False)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Trim-Handle ziehen: Clip-Groesse aendern."""
        if self._trim_mode:
            delta_x = event.scenePos().x() - self._trim_start_mouse_x
            min_width = 10  # minimal 10px

            if self._trim_mode == "right":
                new_width = max(min_width, self._trim_start_width + delta_x)
                self.setRect(QRectF(0, 0, new_width, self._clip_height))
                self._clip_width = new_width
                self._right_handle.setRect(QRectF(new_width - 3, 0, 3, self._clip_height))
            elif self._trim_mode == "left":
                max_delta = self._trim_start_width - min_width
                clamped = max(-self._trim_start_pos_x, min(delta_x, max_delta))
                new_width = self._trim_start_width - clamped
                new_x = self._trim_start_pos_x + clamped
                self.setRect(QRectF(0, 0, new_width, self._clip_height))
                self._clip_width = new_width
                self.setPos(new_x, self._track_y)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def itemChange(self, change, value):
        if self._trim_mode:
            return super().itemChange(change, value)
        if change == QGraphicsRectItem.GraphicsItemChange.ItemPositionChange:
            # Drag-Start merken (erste Bewegung) + H-34 fix: cache duration
            if self._drag_start_x is None:
                self._drag_start_x = self.pos().x()
                # Cache duration from DB to avoid blocking read during flush
                from database import nullpool_session, TimelineEntry
                with nullpool_session() as session:
                    entry = session.get(TimelineEntry, self.entry_id)
                    if entry and entry.end_time is not None:
                        self._drag_duration = entry.end_time - entry.start_time
            new_pos = QPointF(max(0, value.x()), self._track_y)
            return new_pos
        if change == QGraphicsRectItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.on_moved:
                self.on_moved(self.entry_id, value.x())
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        """Drag-Start oder Trim beenden."""
        if self._trim_mode:
            self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)
            if self.on_trimmed:
                self.on_trimmed(
                    self.entry_id,
                    self._trim_mode,
                    self._trim_start_pos_x,
                    self._trim_start_width,
                    self.pos().x(),
                    self._clip_width,
                )
            self._trim_mode = None
            self._left_handle.setVisible(False)
            self._right_handle.setVisible(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)
        self._drag_start_x = None
        self._drag_duration = None  # H-34 fix: clear cached duration


# ======================================================================
# Interactive Timeline (QGraphicsView) — Performance Optimized
# ======================================================================

class InteractiveTimeline(QGraphicsView):
    clip_moved = Signal(int, float)
    selection_changed = Signal(list)  # emits list of dicts with clip data

    # AUD-71: Keyboard shortcut signals (wired to video preview / transport in PBWindow)
    play_pause_toggled = Signal()         # Space
    stop_requested = Signal()             # Escape
    seek_forward = Signal(float)          # L / Right arrow (seconds delta)
    seek_backward = Signal(float)         # J / Left arrow (seconds delta)
    jump_to_start = Signal()              # Home
    jump_to_end = Signal()                # End
    zoom_in_requested = Signal()          # + / =
    zoom_out_requested = Signal()         # -
    set_in_point = Signal(float)          # I (current playhead time)
    set_out_point = Signal(float)         # O (current playhead time)

    _RULER_FONT = QFont("Segoe UI Variable Small", 7)  # refined font

    def __init__(self, console_log=None):
        super().__init__()
        self.undo_stack = QUndoStack(self)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumHeight(120)
        # Match BG0 and BG2 from Premium theme
        self.setStyleSheet("background-color: #0a0d12; border: 1px solid #161c26; border-radius: 8px;")
        # Rubber-band selection on empty space, clip drag takes precedence on items
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setAcceptDrops(True)
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

        # Sektor 3: Software-Rendering (OpenGL entfernt wegen Thread-Crash
        # "Cannot make QOpenGLContext current in a different thread")
        # Tile-Cache + CacheBackground reicht fuer 2D-Timeline.

        # Panning-State
        self._panning = False
        self._pan_start = QPointF()
        self._space_held = False

        self.console_log = console_log
        self.clip_items: list[TimelineClipItem] = []
        self.cut_lines: list[QGraphicsLineItem] = []
        self.waveform_items: list[WaveformGraphicsItem] = []
        self._beat_markers: list[QGraphicsLineItem] = []
        self._beat_times: list[float] = []
        self._snap_to_beat = True
        self._ruler_items: list = []
        self._pending_moves: dict[int, float] = {}  # entry_id -> new_start
        self._move_timer = QTimer(self)
        self._move_timer.setSingleShot(True)
        self._move_timer.setInterval(200)
        self._move_timer.timeout.connect(self._flush_pending_moves)

        self._total_duration: float = 0.0
        self._anchor_map: dict[int, list] = {}  # entry_id -> list[ClipAnchor]
        self._track_bg_items: list[QGraphicsRectItem] = []

        # Beat Grid Overlay + Section Colors (AUD-70)
        self._section_items: list = []        # Section color backgrounds
        self._beat_grid_items: list = []      # Adaptive beat grid lines
        self._drop_markers: list = []         # Drop event markers
        self._current_zoom: float = 1.0       # Current horizontal zoom factor

        # Drop indicator (visual feedback during drag-over)
        self._drop_indicator: QGraphicsLineItem | None = None
        self._drop_ghost: QGraphicsRectItem | None = None

        # AUD-71: Playhead, shuttle state and internal clipboard
        self._playhead_time: float = 0.0   # Current playhead position in seconds
        self._shuttle_speed: int = 0        # JKL shuttle: -2,-1,0,1,2
        self._clipboard: list[dict] = []    # Ctrl+C/V internal clip clipboard

        # Selection changed → inspector
        self._scene.selectionChanged.connect(self._on_selection_changed)

        self._draw_track_backgrounds()
        self._draw_labels()

    @property
    def _scene_width(self) -> float:
        """Dynamic scene width based on total timeline duration."""
        return max(2000, self._total_duration * PIXELS_PER_SECOND + 200)

    def _draw_track_backgrounds(self):
        # Remove old background items before redrawing
        for bg in self._track_bg_items:
            self._scene.removeItem(bg)
        self._track_bg_items.clear()

        w = self._scene_width
        audio_bg = self._scene.addRect(
            QRectF(0, AUDIO_TRACK_Y, w, TRACK_HEIGHT),
            QPen(Qt.PenStyle.NoPen), QBrush(QColor(22, 22, 26))
        )
        audio_bg.setZValue(-10)
        self._track_bg_items.append(audio_bg)
        video_bg = self._scene.addRect(
            QRectF(0, VIDEO_TRACK_Y, w, TRACK_HEIGHT),
            QPen(Qt.PenStyle.NoPen), QBrush(QColor(26, 22, 22))
        )
        video_bg.setZValue(-10)
        self._track_bg_items.append(video_bg)

    def _draw_labels(self):
        for label_text, y in [("A1", AUDIO_TRACK_Y), ("V1", VIDEO_TRACK_Y)]:
            txt = self._scene.addText(label_text, QFont("Segoe UI", 9, QFont.Weight.Bold))
            txt.setDefaultTextColor(QColor(90, 90, 90))
            txt.setPos(-35, y + 15)
            txt.setZValue(10)

    def _cancel_pending_db_load(self):
        """M3-FIX: Laufenden DB-Worker canceln/disconnecten bevor ein neuer gestartet wird."""
        if hasattr(self, '_db_worker') and self._db_worker is not None:
            try:
                self._db_worker.finished.disconnect(self._on_db_load_finished)
            except (TypeError, RuntimeError):
                pass  # Bereits disconnected
        if hasattr(self, '_db_thread') and self._db_thread is not None:
            try:
                if self._db_thread.isRunning():
                    self._db_thread.quit()
                    self._db_thread.wait(2000)
            except RuntimeError:
                pass  # Underlying C++ QThread already deleted (auto-deleted after finished)
            self._db_worker = None
            self._db_thread = None

    def load_from_db(self, project_id: int | None = None):
        """Asynchrones Laden der Timeline-Daten (Fix für Main-Thread Blocking)."""
        # M3-FIX: Alten Worker canceln bevor ein neuer gestartet wird
        self._cancel_pending_db_load()

        if project_id is None:
            from database import get_active_project_id
            project_id = get_active_project_id()

        # UI sofort bereinigen
        for item in self.clip_items:
            self._scene.removeItem(item)
        self.clip_items.clear()
        for wf in self.waveform_items:
            self._scene.removeItem(wf)
        self.waveform_items.clear()
        # Clear old cut lines
        for line in self.cut_lines:
            self._scene.removeItem(line)
        self.cut_lines.clear()
        # Clear old beat markers
        for marker in self._beat_markers:
            self._scene.removeItem(marker)
        self._beat_markers.clear()
        # Clear sections + beat grid + drop markers (AUD-70)
        self._clear_sections()
        self._clear_beat_grid()

        # Hintergrund-Worker für die Datenbankabfrage
        from PySide6.QtCore import QObject, Signal, QThread
        
        class TimelineDBWorker(QObject):
            finished = Signal(list, dict, dict, dict)  # entries, audio_map, video_map, anchor_map
            
            def __init__(self, pid):
                super().__init__(None) # Parent explizit None für moveToThread
                self.pid = pid
                
            def run(self):
                try:
                    with nullpool_session() as session:
                        entries = session.query(TimelineEntry).filter_by(project_id=self.pid).all()
                        
                        _audio_ids = [e.media_id for e in entries if e.track == "audio"]
                        _video_ids = [e.media_id for e in entries if e.track == "video"]
                        
                        _audio_map = (
                            {t.id: t for t in session.query(AudioTrack).filter(
                                AudioTrack.id.in_(_audio_ids), AudioTrack.deleted_at.is_(None)).all()}
                            if _audio_ids else {}
                        )
                        _video_map = (
                            {c.id: c for c in session.query(VideoClip).filter(
                                VideoClip.id.in_(_video_ids), VideoClip.deleted_at.is_(None)).all()}
                            if _video_ids else {}
                        )

                        _entry_ids = [e.id for e in entries]
                        _all_anchors = (
                            session.query(ClipAnchor).filter(
                                ClipAnchor.timeline_entry_id.in_(_entry_ids)
                            ).all() if _entry_ids else []
                        )
                        
                        _anchor_map = {}
                        for anc in _all_anchors:
                            _anchor_map.setdefault(anc.timeline_entry_id, []).append(anc)
                            
                        # Objekte vom Session-State lösen für sichere Übergabe an Main-Thread
                        session.expunge_all()
                        self.finished.emit(entries, _audio_map, _video_map, _anchor_map)
                except Exception as e:
                    logger.error("TimelineDBWorker Fehler: %s", e)
                    self.finished.emit([], {}, {}, {})

        self._db_worker = TimelineDBWorker(project_id)
        self._db_thread = QThread(self)
        self._db_worker.moveToThread(self._db_thread)
        
        self._db_worker.finished.connect(self._on_db_load_finished)
        self._db_worker.finished.connect(self._db_thread.quit)
        self._db_thread.finished.connect(self._db_thread.deleteLater)
        self._db_thread.started.connect(self._db_worker.run)
        
        self._db_thread.start()

    def _on_db_load_finished(self, entries, audio_map, video_map, anchor_map):
        """Wird aufgerufen, sobald die Daten vom Hintergrund-Thread geladen wurden."""
        self._anchor_map = anchor_map
        
        for entry in entries:
            has_waveform = False
            if entry.track == "audio":
                track = audio_map.get(entry.media_id)
                title = track.title if track else "?"
                dur = track.duration if track and track.duration else 30.0
                y = AUDIO_TRACK_Y

                # Rekordbox Waveform laden (falls vorhanden)
                if track and track.waveform_data:
                    has_waveform = True
                    # Wir öffnen eine kurze Read-Only Session für den Waveform-Fetch
                    with DBSession(engine) as session:
                        fresh_track = session.merge(track)
                        self._load_waveform_for_track(session, fresh_track, entry, dur, y)

            elif entry.track == "video":
                clip = video_map.get(entry.media_id)
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
                on_trimmed=self._on_clip_trimmed,
                has_waveform=has_waveform,
                anchors=anchor_map.get(entry.id, []),
            )
            self._scene.addItem(item)
            self.clip_items.append(item)

        # Compute total duration from loaded clips for dynamic background width
        max_end = 0.0
        for ci in self.clip_items:
            clip_end = ci.pos().x() / PIXELS_PER_SECOND + ci._clip_width / PIXELS_PER_SECOND
            if clip_end > max_end:
                max_end = clip_end
        self._total_duration = max_end
        self._draw_track_backgrounds()
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
                track = session.query(AudioTrack).filter(
                    AudioTrack.id == media_id, AudioTrack.deleted_at.is_(None)
                ).first()
                if track and track.waveform_data:
                    has_waveform = True
                    entry_stub = _EntryStub(start_time=start_time)
                    self._load_waveform_for_track(session, track, entry_stub, duration, y)

        item = TimelineClipItem(
            entry_id=entry_id, media_id=media_id, track_type=track_type,
            title=title, x=x, y=y, width=width, height=TRACK_HEIGHT,
            on_moved=self._on_clip_moved, on_trimmed=self._on_clip_trimmed,
            has_waveform=has_waveform,
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
            "transition": QColor(0, 200, 255, 220),   # Cyan fuer DJ-Uebergaenge
            "drop": QColor(255, 40, 40, 255),          # Rot fuer Drops
        }
        for cp in cuts:
            x = cp.time * PIXELS_PER_SECOND
            color = color_map.get(cp.source, QColor(180, 180, 180))
            pen = QPen(color, 1)
            line_h = int(20 * cp.strength)
            line = self._scene.addLine(x, CUT_MARKERS_Y, x, CUT_MARKERS_Y + line_h, pen)
            line.setZValue(5)
            self.cut_lines.append(line)

        # Update total duration and redraw backgrounds if needed
        if total_duration > self._total_duration:
            self._total_duration = total_duration
            self._draw_track_backgrounds()

        self._draw_ruler(total_duration)
        self._update_scene_rect()

    def set_beat_markers(self, beat_times: list[float]) -> None:
        """Zeichnet goldene Beat-Marker auf der Timeline (AI-Funktion)."""
        for line in self._beat_markers:
            self._scene.removeItem(line)
        self._beat_markers.clear()
        self._beat_times = sorted(beat_times)

        gold_pen = QPen(QColor(212, 175, 55, 160), 1)
        downbeat_pen = QPen(QColor(212, 175, 55, 220), 1)
        marker_height = AUDIO_TRACK_Y + TRACK_HEIGHT * 2 + 20

        for i, t in enumerate(self._beat_times):
            x = t * PIXELS_PER_SECOND
            pen = downbeat_pen if (i % 4 == 0) else gold_pen
            line = self._scene.addLine(x, AUDIO_TRACK_Y, x, marker_height, pen)
            line.setZValue(3)
            self._beat_markers.append(line)

    # ── AUD-70: Beat Grid Overlay + Section Colors ───────────────

    # Section color mapping: label -> (background_color, border_color)
    SECTION_COLORS = {
        "DROP":      (QColor(180, 40, 40, 35),   QColor(255, 60, 60, 100)),
        "BUILDUP":   (QColor(200, 170, 30, 30),  QColor(255, 210, 40, 90)),
        "BREAKDOWN": (QColor(40, 90, 180, 30),   QColor(60, 130, 255, 90)),
        "INTRO":     (QColor(100, 100, 100, 20), QColor(140, 140, 140, 60)),
        "OUTRO":     (QColor(100, 100, 100, 20), QColor(140, 140, 140, 60)),
    }

    def load_sections(self, audio_track_id: int) -> None:
        """Laedt StructureSegments aus der DB und zeichnet farbige Sektions-Hintergruende."""
        self._clear_sections()
        with DBSession(engine) as session:
            segments = (
                session.query(StructureSegment)
                .filter_by(audio_track_id=audio_track_id)
                .order_by(StructureSegment.start_time)
                .all()
            )
            if not segments:
                return
            for seg in segments:
                self._draw_section(seg.label, seg.start_time, seg.end_time, seg.energy)

    def set_sections(self, sections: list[dict]) -> None:
        """Zeichnet Sektionen aus einer Liste von Dicts.

        Args:
            sections: [{"label": "DROP", "start": 30.0, "end": 45.0, "energy": 0.9}, ...]
        """
        self._clear_sections()
        for sec in sections:
            self._draw_section(
                sec.get("label", ""),
                sec.get("start", 0.0),
                sec.get("end", 0.0),
                sec.get("energy", 0.5),
            )

    def _clear_sections(self):
        for item in self._section_items:
            self._scene.removeItem(item)
        self._section_items.clear()

    def _draw_section(self, label: str, start: float, end: float, energy: float = 0.5):
        """Zeichnet eine einzelne Sektion als farbigen Hintergrund ueber beide Tracks."""
        colors = self.SECTION_COLORS.get(label.upper(), self.SECTION_COLORS.get("INTRO"))
        if not colors:
            return
        bg_color, border_color = colors

        x = start * PIXELS_PER_SECOND
        w = (end - start) * PIXELS_PER_SECOND
        if w < 1:
            return

        # Sektions-Hintergrund ueber Audio + Video Tracks
        total_h = (VIDEO_TRACK_Y + TRACK_HEIGHT) - AUDIO_TRACK_Y
        rect = self._scene.addRect(
            QRectF(x, AUDIO_TRACK_Y, w, total_h),
            QPen(border_color, 1),
            QBrush(bg_color),
        )
        rect.setZValue(-5)  # Hinter Clips, ueber Track-BG
        self._section_items.append(rect)

        # Section-Label oben links
        label_text = self._scene.addText(
            label.upper(), QFont("Segoe UI Variable Small", 7, QFont.Weight.Bold)
        )
        label_text.setDefaultTextColor(border_color.lighter(130))
        label_text.setPos(x + 3, AUDIO_TRACK_Y - 1)
        label_text.setZValue(-4)
        self._section_items.append(label_text)

        # Drop-Marker: Blitz-Icon bei DROP-Sektionen
        if label.upper() == "DROP":
            self._draw_drop_marker(x, energy)

    def _draw_drop_marker(self, x: float, energy: float = 0.8):
        """Zeichnet ein Blitz-Symbol als Drop-Event-Marker."""
        # Blitz-Polygon (Lightning Bolt)
        bolt = QPolygonF([
            QPointF(x + 4, AUDIO_TRACK_Y - 12),
            QPointF(x + 8, AUDIO_TRACK_Y - 4),
            QPointF(x + 6, AUDIO_TRACK_Y - 4),
            QPointF(x + 9, AUDIO_TRACK_Y + 4),
            QPointF(x + 3, AUDIO_TRACK_Y - 2),
            QPointF(x + 5, AUDIO_TRACK_Y - 2),
        ])
        marker = self._scene.addPolygon(
            bolt,
            QPen(QColor(255, 200, 40, 230), 1),
            QBrush(QColor(255, 60, 60, int(200 * energy))),
        )
        marker.setZValue(8)
        self._drop_markers.append(marker)
        self._section_items.append(marker)

    def set_beat_grid(self, beat_times: list[float],
                      downbeat_times: list[float] | None = None,
                      energy_per_beat: list[float] | None = None) -> None:
        """Zeichnet ein adaptives Beat-Grid auf die Timeline.

        Das Grid passt die Dichte automatisch an den Zoom-Level an:
        - Zoom < 0.5: Nur Downbeats (jeder 4.)
        - Zoom 0.5-1.5: Halbe Beats (jeder 2.)
        - Zoom > 1.5: Alle Beats

        Args:
            beat_times: Alle Beat-Positionen in Sekunden
            downbeat_times: Optional: Downbeat-Positionen (jeder 1.)
            energy_per_beat: Optional: Energie pro Beat [0.0-1.0] fuer Farb-Intensitaet
        """
        self._clear_beat_grid()
        if not beat_times:
            return

        sorted_beats = sorted(beat_times)
        downbeats = set(downbeat_times) if downbeat_times else set()
        zoom = self._current_zoom

        # Adaptive LOD: Beat-Dichte je nach Zoom
        if zoom < 0.5:
            step = 4  # Nur Downbeats
        elif zoom < 1.5:
            step = 2  # Halbe Beats
        else:
            step = 1  # Alle Beats

        grid_top = AUDIO_TRACK_Y
        grid_bottom = VIDEO_TRACK_Y + TRACK_HEIGHT

        # Pens fuer verschiedene Beat-Typen
        downbeat_pen = QPen(QColor(212, 175, 55, 140), 1, Qt.PenStyle.SolidLine)
        beat_pen = QPen(QColor(90, 90, 100, 60), 1, Qt.PenStyle.DotLine)
        half_beat_pen = QPen(QColor(60, 60, 70, 40), 1, Qt.PenStyle.DotLine)

        for i, t in enumerate(sorted_beats):
            if i % step != 0:
                continue

            x = t * PIXELS_PER_SECOND
            is_downbeat = t in downbeats or (not downbeats and i % 4 == 0)

            if is_downbeat:
                pen = downbeat_pen
            elif i % 2 == 0:
                pen = beat_pen
            else:
                pen = half_beat_pen

            # Energy-basierte Opacity (wenn verfuegbar)
            if energy_per_beat and i < len(energy_per_beat):
                e = max(0.2, min(1.0, energy_per_beat[i]))
                pen_color = pen.color()
                pen_color.setAlphaF(pen_color.alphaF() * e)
                pen = QPen(pen_color, pen.widthF(), pen.style())

            line = self._scene.addLine(x, grid_top, x, grid_bottom, pen)
            line.setZValue(-3)  # Hinter Clips, ueber Sections
            self._beat_grid_items.append(line)

    def _clear_beat_grid(self):
        for item in self._beat_grid_items:
            self._scene.removeItem(item)
        self._beat_grid_items.clear()
        for marker in self._drop_markers:
            if marker not in self._section_items:
                self._scene.removeItem(marker)
        self._drop_markers.clear()

    def load_beat_grid_from_db(self, audio_track_id: int) -> None:
        """Laedt Beatgrid + Sections aus der DB und zeichnet alles."""
        with DBSession(engine) as session:
            beatgrid = session.query(Beatgrid).filter_by(
                audio_track_id=audio_track_id
            ).first()
            if not beatgrid:
                return

            beat_times = []
            downbeat_times = []
            energy_per_beat = []

            # H7-FIX: Column(JSON) deserialisiert automatisch.
            # isinstance-Check fuer Backward-compat mit alten doppelt-serialisierten Daten.
            if beatgrid.beat_positions:
                try:
                    beat_times = (json.loads(beatgrid.beat_positions)
                                  if isinstance(beatgrid.beat_positions, str)
                                  else beatgrid.beat_positions)
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning("load_beat_grid: failed to parse beat_positions: %s", exc)

            if beatgrid.downbeat_positions:
                try:
                    downbeat_times = (json.loads(beatgrid.downbeat_positions)
                                      if isinstance(beatgrid.downbeat_positions, str)
                                      else beatgrid.downbeat_positions)
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning("load_beat_grid: failed to parse downbeat_positions: %s", exc)

            if beatgrid.energy_per_beat:
                try:
                    energy_per_beat = (json.loads(beatgrid.energy_per_beat)
                                       if isinstance(beatgrid.energy_per_beat, str)
                                       else beatgrid.energy_per_beat)
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning("load_beat_grid: failed to parse energy_per_beat: %s", exc)

            self.set_beat_grid(beat_times, downbeat_times or None,
                               energy_per_beat or None)

        # Sections laden
        self.load_sections(audio_track_id)

    def _update_beat_grid_lod(self):
        """Aktualisiert die Beat-Grid Dichte nach Zoom-Aenderung."""
        if self._beat_times:
            # Re-zeichne mit aktuellem Zoom-Level
            self.set_beat_grid(self._beat_times)

    def _snap_x_to_beat(self, x: float) -> float:
        """Rastet x (in Pixeln) an den naechsten Beat ein (Snap-Radius: 8px).
        Uses bisect for O(log N) lookup instead of O(N) min()."""
        if not self._snap_to_beat or not self._beat_times:
            return x
        t = x / PIXELS_PER_SECOND
        idx = bisect.bisect_left(self._beat_times, t)
        candidates = []
        if idx > 0:
            candidates.append(self._beat_times[idx - 1])
        if idx < len(self._beat_times):
            candidates.append(self._beat_times[idx])
        closest = min(candidates, key=lambda b: abs(b - t)) if candidates else t
        if abs(closest - t) * PIXELS_PER_SECOND <= 8.0:
            return closest * PIXELS_PER_SECOND
        return x

    def _draw_ruler(self, total_duration: float):
        # Entferne alte Ruler-Items bevor neue gezeichnet werden
        for item in self._ruler_items:
            self._scene.removeItem(item)
        self._ruler_items.clear()

        pen = QPen(QColor(60, 60, 60), 1)
        total_px = total_duration * PIXELS_PER_SECOND
        line = self._scene.addLine(0, RULER_Y, total_px, RULER_Y, pen)
        self._ruler_items.append(line)

        step = max(1.0, total_duration / 20)
        t = 0.0
        while t <= total_duration:
            x = t * PIXELS_PER_SECOND
            tick = self._scene.addLine(x, RULER_Y - 3, x, RULER_Y + 3, pen)
            self._ruler_items.append(tick)
            txt = self._scene.addText(f"{t:.0f}s", self._RULER_FONT)
            txt.setDefaultTextColor(QColor(70, 70, 70))
            txt.setPos(x - 10, RULER_Y + 5)
            self._ruler_items.append(txt)
            t += step

    def _on_clip_moved(self, entry_id: int, new_x: float):
        """Debounced: Sammelt Drag-Events und schreibt erst nach 200ms Ruhe in die DB."""
        snapped_x = self._snap_x_to_beat(max(0, new_x))
        new_start = max(0, snapped_x / PIXELS_PER_SECOND)
        self._pending_moves[entry_id] = new_start
        self._move_timer.start()

    def _flush_pending_moves(self):
        """Schreibt alle Drag-Zustaende in die DB (via UndoCommand, als Macro bei Multi-Select).
        H-34 fix: Uses cached duration to avoid blocking DB reads on GUI thread."""
        if not self._pending_moves:
            return
        moves = dict(self._pending_moves)
        self._pending_moves.clear()

        from ui.undo_commands import MoveClipCommand

        use_macro = len(moves) > 1
        if use_macro:
            self.undo_stack.beginMacro(f"{len(moves)} Clips verschieben")

        try:
            for entry_id, new_start in moves.items():
                clip_item = self._find_clip_item(entry_id)
                if not clip_item:
                    continue

                # Use cached values from drag start - no DB read needed
                drag_start_x = clip_item._drag_start_x
                duration = clip_item._drag_duration

                if drag_start_x is None or duration is None:
                    # Fallback: skip this clip if no cached data
                    logger.warning("Clip %d: No cached drag data, skipping flush", entry_id)
                    continue

                old_start = max(0, drag_start_x / PIXELS_PER_SECOND)
                old_end = round(old_start + duration, 3) if duration else None
                new_end = round(new_start + duration, 3) if duration else None

                cmd = MoveClipCommand(
                    timeline=self,
                    entry_id=entry_id,
                    old_start=old_start,
                    old_end=old_end,
                    new_start=new_start,
                    new_end=new_end,
                )
                self.undo_stack.push(cmd)
                self.clip_moved.emit(entry_id, new_start)
        finally:
            if use_macro:
                self.undo_stack.endMacro()

    def _find_clip_item(self, entry_id: int) -> TimelineClipItem | None:
        """Sucht ein TimelineClipItem anhand seiner entry_id."""
        for item in self.clip_items:
            if item.entry_id == entry_id:
                return item
        return None

    def _sync_clip_position(self, entry_id: int, start_time: float):
        """Aktualisiert die visuelle Position eines Clips (fuer Undo/Redo)."""
        item = self._find_clip_item(entry_id)
        if item:
            new_x = start_time * PIXELS_PER_SECOND
            item.setPos(new_x, item._track_y)

    def _remove_clip_item(self, entry_id: int):
        """Entfernt ein Clip-Item aus der Scene (fuer Undo/Redo)."""
        item = self._find_clip_item(entry_id)
        if item:
            self._scene.removeItem(item)
            self.clip_items.remove(item)

    def _on_clip_trimmed(self, entry_id: int, edge: str,
                         old_pos_x: float, old_width: float,
                         new_pos_x: float, new_width: float):
        """Callback nach Trim: DB-Update via UndoCommand."""
        from database import nullpool_session
        from ui.undo_commands import TrimClipCommand

        with nullpool_session() as session:
            entry = session.get(TimelineEntry, entry_id)
            if not entry:
                return
            old_start = entry.start_time
            old_end = entry.end_time
            old_source_start = entry.source_start
            old_source_end = entry.source_end

        new_duration = new_width / PIXELS_PER_SECOND

        if edge == "right":
            new_start = old_start
            new_end = round(old_start + new_duration, 3)
            new_source_start = old_source_start
            new_source_end = (round((old_source_start or 0.0) + new_duration, 3)
                              if old_source_end is not None else None)
        else:  # left
            delta = (new_pos_x - old_pos_x) / PIXELS_PER_SECOND
            new_start = round(old_start + delta, 3)
            new_end = old_end
            new_source_start = round((old_source_start or 0.0) + delta, 3)
            new_source_end = old_source_end

        cmd = TrimClipCommand(
            timeline=self,
            entry_id=entry_id,
            old_start=old_start,
            old_end=old_end,
            old_source_start=old_source_start,
            old_source_end=old_source_end,
            new_start=new_start,
            new_end=new_end,
            new_source_start=new_source_start,
            new_source_end=new_source_end,
        )
        self.undo_stack.push(cmd)

    def _sync_clip_after_trim(self, entry_id: int, start: float, end: float | None):
        """Aktualisiert Position und Breite eines Clips nach Trim (fuer Undo/Redo)."""
        item = self._find_clip_item(entry_id)
        if not item:
            return
        new_x = start * PIXELS_PER_SECOND
        duration = (end - start) if end is not None else item._clip_width / PIXELS_PER_SECOND
        new_width = duration * PIXELS_PER_SECOND
        item.setPos(new_x, item._track_y)
        item.setRect(QRectF(0, 0, new_width, item._clip_height))
        item._clip_width = new_width
        # Update right trim handle position
        item._right_handle.setRect(QRectF(new_width - 3, 0, 3, item._clip_height))

    def _on_selection_changed(self):
        """Emits selection_changed signal with selected clip data for inspector."""
        selected = [item for item in self._scene.selectedItems()
                    if isinstance(item, TimelineClipItem)]
        clip_data = []
        for item in selected:
            clip_data.append({
                "entry_id": item.entry_id,
                "media_id": item.media_id,
                "track_type": item.track_type,
                "pos_x": item.pos().x(),
                "width": item._clip_width,
            })
        self.selection_changed.emit(clip_data)

    def remove_selected_clips(self):
        """Entfernt alle ausgewaehlten Clips via UndoCommand."""
        selected = [item for item in self._scene.selectedItems()
                    if isinstance(item, TimelineClipItem)]
        if not selected:
            return
        from ui.undo_commands import RemoveClipCommand
        use_macro = len(selected) > 1
        if use_macro:
            self.undo_stack.beginMacro(f"{len(selected)} Clips entfernen")
        for clip_item in selected:
            cmd = RemoveClipCommand(timeline=self, entry_id=clip_item.entry_id)
            self.undo_stack.push(cmd)
        if use_macro:
            self.undo_stack.endMacro()

    def _update_scene_rect(self):
        r = self._scene.itemsBoundingRect()
        r.adjust(-60, -10, 200, 40)
        self._scene.setSceneRect(r)

    def wheelEvent(self, event):
        """Zoom mit Mausrad — sanfter Faktor, nur horizontal, zur Mausposition."""
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.08 if delta > 0 else 1.0 / 1.08
        current_scale = self.transform().m11()
        new_scale = current_scale * factor
        if new_scale < 0.01 or new_scale > 200.0:
            return
        old_zoom = self._current_zoom
        self.scale(factor, 1.0)
        self._current_zoom = new_scale
        # LOD-Update nur bei signifikanter Zoom-Aenderung (Schwellwert-Ueberschreitung)
        old_lod = 4 if old_zoom < 0.5 else (2 if old_zoom < 1.5 else 1)
        new_lod = 4 if new_scale < 0.5 else (2 if new_scale < 1.5 else 1)
        if old_lod != new_lod:
            self._update_beat_grid_lod()

    def mousePressEvent(self, event):
        """Mittlere Maustaste → Panning starten (AUD-71: Space is now Play/Pause)."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position()
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
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
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ── AUD-71: Keyboard Shortcuts (configurable via ShortcutManager) ───

    def keyPressEvent(self, event):
        """Full keyboard shortcut system (AUD-71).

        All bindings are configurable via Settings → Tastaturkürzel.
        Defaults:
          Space       = Play / Pause
          J / K / L   = Shuttle (reverse / pause / forward)
          I           = Set In-Point at playhead
          O           = Set Out-Point at playhead
          M           = Set Anchor on selected clip
          Delete      = Remove selected clips
          Home        = Jump to start
          End         = Jump to end
          Left/Right  = Frame step (0.04s) / Shift: 1s jump
          +/=         = Zoom in
          -           = Zoom out
          Ctrl+Z/Y    = Undo/Redo
          Ctrl+C/V    = Copy/Paste
          Escape      = Stop / deselect
        """
        sm = get_shortcut_manager()
        key = event.key()
        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

        if event.isAutoRepeat():
            # Allow held arrow keys for frame-stepping / fast navigation
            if sm.matches("frame_fwd", event):
                step = 1.0 if shift else 0.04
                self.seek_forward.emit(step)
                return
            if sm.matches("frame_back", event):
                step = 1.0 if shift else 0.04
                self.seek_backward.emit(step)
                return
            return

        # Play / Pause
        if sm.matches("play_pause", event):
            self.play_pause_toggled.emit()
            return

        # Shuttle: J / K / L
        if sm.matches("shuttle_back", event):
            self._shuttle_speed = max(self._shuttle_speed - 1, -2)
            if self._shuttle_speed < 0:
                speed = 2.0 if self._shuttle_speed == -2 else 0.5
                self.seek_backward.emit(speed)
            elif self._shuttle_speed == 0:
                self.play_pause_toggled.emit()
            return
        if sm.matches("shuttle_pause", event):
            self._shuttle_speed = 0
            self.stop_requested.emit()
            return
        if sm.matches("shuttle_fwd", event):
            self._shuttle_speed = min(self._shuttle_speed + 1, 2)
            if self._shuttle_speed > 0:
                speed = 2.0 if self._shuttle_speed == 2 else 0.5
                self.seek_forward.emit(speed)
            elif self._shuttle_speed == 0:
                self.play_pause_toggled.emit()
            return

        # In / Out points
        if sm.matches("set_in", event):
            self.set_in_point.emit(self._playhead_time)
            return
        if sm.matches("set_out", event):
            self.set_out_point.emit(self._playhead_time)
            return

        # Set anchor
        if sm.matches("set_anchor", event):
            self._set_anchor_on_selected()
            return

        # Delete selected clips
        if sm.matches("delete_clip", event) or key == Qt.Key.Key_Backspace:
            self.remove_selected_clips()
            return

        # Jump to start / end
        if sm.matches("jump_start", event):
            self.jump_to_start.emit()
            return
        if sm.matches("jump_end", event):
            self.jump_to_end.emit()
            return

        # Frame step (Shift = 1s jump)
        if sm.matches("frame_back", event):
            self.seek_backward.emit(1.0 if shift else 0.04)
            return
        if sm.matches("frame_fwd", event):
            self.seek_forward.emit(1.0 if shift else 0.04)
            return

        # Zoom (also keep Key_Equal as fallback for unshifted + on some keyboards)
        if sm.matches("zoom_in", event) or key == Qt.Key.Key_Equal:
            self.zoom_in_requested.emit()
            return
        if sm.matches("zoom_out", event):
            self.zoom_out_requested.emit()
            return

        # Undo / Redo
        if sm.matches("undo", event):
            self.undo_stack.undo()
            return
        if sm.matches("redo", event):
            self.undo_stack.redo()
            return

        # Copy / Paste (AUD-71)
        if sm.matches("copy", event):
            self._copy_selected_clips()
            return
        if sm.matches("paste", event):
            self._paste_clips()
            return

        # Stop / deselect all
        if sm.matches("stop", event):
            self._scene.clearSelection()
            self.stop_requested.emit()
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        """No special release handling needed after Space remap (AUD-71)."""
        super().keyReleaseEvent(event)

    def set_playhead_time(self, time_sec: float):
        """Update playhead position (called by video preview position sync)."""
        self._playhead_time = time_sec

    def zoom_by_factor(self, factor: float):
        """Programmatic zoom (for +/- shortcuts)."""
        current_scale = self.transform().m11()
        new_scale = current_scale * factor
        if new_scale < 0.01 or new_scale > 200.0:
            return
        old_zoom = self._current_zoom
        self.scale(factor, 1.0)
        self._current_zoom = new_scale
        old_lod = 4 if old_zoom < 0.5 else (2 if old_zoom < 1.5 else 1)
        new_lod = 4 if new_scale < 0.5 else (2 if new_scale < 1.5 else 1)
        if old_lod != new_lod:
            self._update_beat_grid_lod()

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

    # ── AUD-71: Copy / Paste ─────────────────────────────────────────────

    def _copy_selected_clips(self) -> None:
        """Copy selected clip metadata to internal clipboard."""
        selected = [item for item in self._scene.selectedItems()
                    if isinstance(item, TimelineClipItem)]
        if not selected:
            return
        self._clipboard = [
            {
                "entry_id": item.entry_id,
                "media_id": item.media_id,
                "track_type": item.track_type,
                "start_time": item.pos().x() / PIXELS_PER_SECOND,
                "clip_width": item._clip_width,
                "title": item.title,
            }
            for item in selected
        ]
        if self.console_log:
            self.console_log(f"[Copy] {len(self._clipboard)} Clip(s) kopiert.")

    def _paste_clips(self) -> None:
        """Paste clips from internal clipboard offset by 0.5s."""
        if not getattr(self, "_clipboard", None):
            return
        offset = 0.5  # paste with slight time offset to avoid exact overlap
        for data in self._clipboard:
            new_start = data["start_time"] + offset
            # Re-use the same entry but shift position (visual paste — no DB write)
            # A full DB-backed paste would require duplicating TimelineEntry rows;
            # that is out of scope for AUD-71 (shortcut wiring only).
            if self.console_log:
                self.console_log(
                    f"[Paste] Clip '{data['title']}' würde bei {new_start:.2f}s eingefügt. "
                    "(DB-Paste via Drag-Drop — ziehe Clip aus der Media-Leiste.)"
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
        # Bug-18 Fix: Eine Session für alle Updates statt einer pro Video-Clip
        updates: list[tuple[int, float, float | None]] = []  # (entry_id, new_start, new_end|None)

        def _first_anchor_offset(clip: TimelineClipItem) -> float | None:
            """Get first anchor time_offset from cached _anchor_map (no DB hit)."""
            anchors = self._anchor_map.get(clip.entry_id)
            if not anchors:
                return None
            return min(a.time_offset for a in anchors)

        for audio_clip in audio_clips:
            audio_anchor_offset = _first_anchor_offset(audio_clip)
            if audio_anchor_offset is None:
                continue

            # Absoluter Zeitpunkt des Audio-Ankers auf der Timeline
            audio_clip_start = audio_clip.pos().x() / PIXELS_PER_SECOND
            audio_anchor_abs = audio_clip_start + audio_anchor_offset

            for video_clip in video_clips:
                video_anchor_offset = _first_anchor_offset(video_clip)
                if video_anchor_offset is None:
                    continue

                # Video-Clip verschieben: Anker soll auf audio_anchor_abs landen
                new_video_start = audio_anchor_abs - video_anchor_offset
                new_x = max(0, new_video_start * PIXELS_PER_SECOND)
                video_clip.setPos(new_x, video_clip._track_y)
                updates.append((video_clip.entry_id, new_video_start, None))
                synced = True

        if updates:
            from database import nullpool_session
            with nullpool_session() as session:
                for entry_id, new_start, _ in updates:
                    entry = session.get(TimelineEntry, entry_id)
                    if entry:
                        if entry.end_time is not None:
                            duration = entry.end_time - entry.start_time
                            entry.end_time = round(new_start + duration, 4)
                        entry.start_time = round(new_start, 4)
                session.commit()

        return synced

    # ==================================================================
    # Drag & Drop — Accept clips from Media Pool
    # ==================================================================

    def _detect_track_from_y(self, scene_y: float) -> str | None:
        """Detects which track lane the cursor is over."""
        if AUDIO_TRACK_Y <= scene_y <= AUDIO_TRACK_Y + TRACK_HEIGHT:
            return "audio"
        if VIDEO_TRACK_Y <= scene_y <= VIDEO_TRACK_Y + TRACK_HEIGHT:
            return "video"
        # If between tracks or slightly off, snap to nearest
        mid = (AUDIO_TRACK_Y + TRACK_HEIGHT + VIDEO_TRACK_Y) / 2
        if scene_y < mid:
            return "audio"
        return "video"

    def _clear_drop_indicator(self):
        """Remove the drop-indicator line and ghost rectangle."""
        if self._drop_indicator:
            self._scene.removeItem(self._drop_indicator)
            self._drop_indicator = None
        if self._drop_ghost:
            self._scene.removeItem(self._drop_ghost)
            self._drop_ghost = None

    def _show_drop_indicator(self, scene_pos: QPointF, track_type: str, duration: float = 4.0):
        """Show a vertical line + translucent ghost rect at the drop position."""
        self._clear_drop_indicator()

        x = self._snap_x_to_beat(max(0, scene_pos.x()))
        y = AUDIO_TRACK_Y if track_type == "audio" else VIDEO_TRACK_Y

        # Vertical drop-position line (gold)
        pen = QPen(QColor(212, 175, 55, 220), 2, Qt.PenStyle.DashLine)
        self._drop_indicator = self._scene.addLine(
            x, y, x, y + TRACK_HEIGHT, pen
        )
        self._drop_indicator.setZValue(20)

        # Ghost rectangle showing actual clip placement
        ghost_w = duration * PIXELS_PER_SECOND
        ghost_color = (QColor(45, 85, 150, 60) if track_type == "audio"
                       else QColor(212, 164, 74, 60))
        self._drop_ghost = self._scene.addRect(
            QRectF(x, y, ghost_w, TRACK_HEIGHT),
            QPen(QColor(212, 175, 55, 140), 1, Qt.PenStyle.DashLine),
            QBrush(ghost_color),
        )
        self._drop_ghost.setZValue(19)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(CLIP_MIME_TYPE):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if not event.mimeData().hasFormat(CLIP_MIME_TYPE):
            super().dragMoveEvent(event)
            return
        event.acceptProposedAction()

        scene_pos = self.mapToScene(event.position().toPoint())
        # Determine track and duration from MIME data (preferred) or cursor Y
        duration = 4.0 # default fallback
        try:
            payload = json.loads(
                bytes(event.mimeData().data(CLIP_MIME_TYPE)).decode("utf-8")
            )
            track_type = payload.get("track_type", "video")
            if "duration" in payload:
                duration = float(payload["duration"])
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            track_type = self._detect_track_from_y(scene_pos.y()) or "video"

        self._show_drop_indicator(scene_pos, track_type, duration)

    def dragLeaveEvent(self, event):
        self._clear_drop_indicator()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(CLIP_MIME_TYPE):
            super().dropEvent(event)
            return

        self._clear_drop_indicator()

        try:
            raw = bytes(event.mimeData().data(CLIP_MIME_TYPE)).decode("utf-8")
            payload = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            event.ignore()
            return

        track_type = payload.get("track_type", "video")
        media_id = payload.get("media_id")
        title = payload.get("title", "?")
        if media_id is None:
            event.ignore()
            return

        # Compute drop position (in seconds), snapped to beat
        scene_pos = self.mapToScene(event.position().toPoint())
        drop_x = self._snap_x_to_beat(max(0, scene_pos.x()))
        start_time = drop_x / PIXELS_PER_SECOND

        # Fetch duration from DB
        with DBSession(engine) as session:
            if track_type == "audio":
                obj = session.query(AudioTrack).filter(
                    AudioTrack.id == media_id, AudioTrack.deleted_at.is_(None)
                ).first()
                duration = obj.duration if obj and obj.duration else 30.0
            else:
                obj = session.query(VideoClip).filter(
                    VideoClip.id == media_id, VideoClip.deleted_at.is_(None)
                ).first()
                duration = obj.duration if obj and obj.duration else 10.0

        # Get active project
        from database import get_active_project_id
        project_id = get_active_project_id()

        # Create clip via UndoCommand
        from ui.undo_commands import AddClipCommand
        cmd = AddClipCommand(
            timeline=self,
            project_id=project_id,
            track_type=track_type,
            media_id=media_id,
            title=title,
            start_time=start_time,
            duration=duration,
        )
        self.undo_stack.push(cmd)

        if self.console_log:
            self.console_log(
                f"[Timeline] {track_type.title()} '{title}' per Drag & Drop "
                f"bei {start_time:.1f}s eingefuegt (Dauer: {duration:.1f}s)"
            )

        event.acceptProposedAction()
