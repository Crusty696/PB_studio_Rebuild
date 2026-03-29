"""Interactive Timeline with draggable clips, anchors, beat markers and zoom."""

import bisect
from collections import namedtuple
from pathlib import Path

from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsTextItem, QGraphicsLineItem, QGraphicsPolygonItem, QMenu,
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QBrush, QPen, QPolygonF

from sqlalchemy.orm import Session as DBSession

from database import engine, AudioTrack, VideoClip, TimelineEntry, Beatgrid, ClipAnchor
from services.pacing_service import CutPoint
from ui.waveform_item import WaveformGraphicsItem

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
    # Audio-Clips: halbtransparent, damit Rekordbox-Wellenform durchscheint
    AUDIO_COLOR = QColor(30, 60, 120, 60)
    AUDIO_COLOR_NO_WAVEFORM = QColor(70, 130, 220, 200)
    VIDEO_COLOR = QColor(230, 140, 50, 200)

    def __init__(self, entry_id: int, media_id: int, track_type: str,
                 title: str, x: float, y: float, width: float, height: float,
                 on_moved=None, has_waveform: bool = False,
                 anchors: list | None = None):
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
        with DBSession(engine) as session:
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
            m.remove_from_scene()
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

class InteractiveTimeline(QGraphicsView):
    clip_moved = Signal(int, float)
    _RULER_FONT = QFont("Segoe UI", 7)  # cached — avoid per-tick QFont creation

    def __init__(self, console_log=None):
        super().__init__()
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setMinimumHeight(120)
        self.setStyleSheet("background-color: #141414; border: 1px solid #222222;")
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
        self._pending_move = None
        self._move_timer = QTimer(self)
        self._move_timer.setSingleShot(True)
        self._move_timer.setInterval(200)
        self._move_timer.timeout.connect(self._flush_pending_move)

        self._total_duration: float = 0.0
        self._anchor_map: dict[int, list] = {}  # entry_id -> list[ClipAnchor]
        self._track_bg_items: list[QGraphicsRectItem] = []

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

    def load_from_db(self, project_id: int | None = None):
        if project_id is None:
            from database import get_active_project_id
            project_id = get_active_project_id()
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

        with DBSession(engine) as session:
            entries = (
                session.query(TimelineEntry)
                .filter_by(project_id=project_id)
                .all()
            )
            # Bug-17 Fix: Bulk-Load AudioTracks und VideoClips — verhindert N+1
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

            # Bulk-Load aller ClipAnchors — verhindert N+1 pro Clip
            _entry_ids = [e.id for e in entries]
            _all_anchors = (
                session.query(ClipAnchor).filter(
                    ClipAnchor.timeline_entry_id.in_(_entry_ids)
                ).all() if _entry_ids else []
            )
            self._anchor_map = {}
            for anc in _all_anchors:
                self._anchor_map.setdefault(anc.timeline_entry_id, []).append(anc)
            _anchor_map = self._anchor_map

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
                    anchors=_anchor_map.get(entry.id, []),
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
                track = session.get(AudioTrack, media_id)
                if track and track.waveform_data:
                    has_waveform = True
                    entry_stub = _EntryStub(start_time=start_time)
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
        # Pending-Move merken, DB-Write per Timer debounced
        self._pending_move = (entry_id, new_start)
        self._move_timer.start()

    def _flush_pending_move(self):
        """Schreibt den letzten Drag-Zustand in die DB (nach Debounce)."""
        if self._pending_move is None:
            return
        entry_id, new_start = self._pending_move
        self._pending_move = None
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
        factor = 1.08 if delta > 0 else 1.0 / 1.08
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
            with DBSession(engine) as session:
                for entry_id, new_start, _ in updates:
                    entry = session.get(TimelineEntry, entry_id)
                    if entry:
                        if entry.end_time is not None:
                            duration = entry.end_time - entry.start_time
                            entry.end_time = round(new_start + duration, 4)
                        entry.start_time = round(new_start, 4)
                session.commit()

        return synced
