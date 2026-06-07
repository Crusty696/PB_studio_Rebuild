"""Interactive Timeline with draggable clips, anchors, beat markers and zoom."""

import bisect
import json
import logging
from collections import namedtuple
from pathlib import Path

from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsTextItem, QGraphicsLineItem, QGraphicsPolygonItem, QGraphicsPixmapItem, QMenu,
    QGraphicsItem, QStyleOptionGraphicsItem,
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import (
    QPainter, QColor, QFont, QBrush, QPen, QPolygonF, QUndoStack, QPixmap,
)

from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession, joinedload

from database import engine, AudioTrack, VideoClip, TimelineEntry, Beatgrid, ClipAnchor, StructureSegment, nullpool_session

logger = logging.getLogger(__name__)
from services.pacing_service import CutPoint
from ui.shortcut_manager import get_shortcut_manager
from ui.waveform_item import WaveformGraphicsItem
from ui.widgets.lock_icon_item import LockIconItem

# MIME type for internal clip drag & drop (must match media_workspace.py)
CLIP_MIME_TYPE = "application/x-pb-studio-clip"

_EntryStub = namedtuple("_EntryStub", ["start_time"])

from PySide6.QtCore import QThread, QObject

class WaveformLoadWorker(QObject):
    finished = Signal(object, list, list, list, list)  # (track, band_low, band_mid, band_high, beat_positions)

    def __init__(self, media_id: int):
        super().__init__()
        self.media_id = media_id

    def run(self):
        try:
            from database import nullpool_session, AudioTrack
            import json
            with nullpool_session() as session:
                track = session.query(AudioTrack).filter(
                    AudioTrack.id == self.media_id, AudioTrack.deleted_at.is_(None)
                ).first()
                if track and track.waveform_data:
                    wd = track.waveform_data
                    band_low = json.loads(wd.band_low) if isinstance(wd.band_low, str) else (wd.band_low or [])
                    band_mid = json.loads(wd.band_mid) if isinstance(wd.band_mid, str) else (wd.band_mid or [])
                    band_high = json.loads(wd.band_high) if isinstance(wd.band_high, str) else (wd.band_high or [])
                    
                    beat_positions = []
                    if track.beatgrid and track.beatgrid.beat_positions:
                        beat_positions = json.loads(track.beatgrid.beat_positions) if isinstance(track.beatgrid.beat_positions, str) else (track.beatgrid.beat_positions or [])
                    
                    self.finished.emit(track, band_low, band_mid, band_high, beat_positions)
                    return
        except Exception as e:
            logger.error("Async Waveform Load Error: %s", e)
        self.finished.emit(None, [], [], [], [])

# ======================================================================
# Constants
# ======================================================================

PIXELS_PER_SECOND = 20
TRACK_HEIGHT = 80
AUDIO_TRACK_Y = 10
VIDEO_TRACK_Y = AUDIO_TRACK_Y + TRACK_HEIGHT + 12
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
        # B-077: time_offset lokal speichern, damit ``get_first_anchor_time``
        # aus der Marker-Liste lesen kann statt jedes Mal eine sync DB-Query
        # im UI-Thread auszufuehren.
        self.time_offset: float = x_offset / PIXELS_PER_SECOND if PIXELS_PER_SECOND else 0.0
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



class BeatGridItem(QGraphicsItem):
    """Adaptive Beatgrid-Zeichnung als einzelnes, optimiertes GraphicsItem.

    Verhindert das Erzeugen/Loeschen von Tausenden QGraphicsLineItems in der Szene.
    Nutzt exposedRect Culling und binary search fuer extrem schnellen Redraw beim Scrollen/Zoom.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._beat_times: list[float] = []
        self._downbeat_times: set[float] = set()
        self._energy_per_beat: list[float] = []
        self._current_zoom: float = 1.0
        self.setZValue(-3)

    def set_data(self, beat_times: list[float], downbeat_times: list[float] | None = None, energy_per_beat: list[float] | None = None, zoom: float = 1.0):
        self._beat_times = sorted(beat_times) if beat_times else []
        self._downbeat_times = set(downbeat_times) if downbeat_times else set()
        self._energy_per_beat = energy_per_beat or []
        self._current_zoom = zoom
        self.prepareGeometryChange()
        self.update()

    def update_zoom(self, zoom: float):
        if abs(self._current_zoom - zoom) > 0.001:
            self._current_zoom = zoom
            self.update()

    def boundingRect(self) -> QRectF:
        if not self._beat_times:
            return QRectF()
        w = self._beat_times[-1] * PIXELS_PER_SECOND
        grid_top = AUDIO_TRACK_Y
        grid_bottom = VIDEO_TRACK_Y + TRACK_HEIGHT
        return QRectF(0, grid_top, w + 100, grid_bottom - grid_top)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        clip_rect = option.exposedRect
        if clip_rect.isEmpty() or not self._beat_times:
            return

        grid_top = AUDIO_TRACK_Y
        grid_bottom = VIDEO_TRACK_Y + TRACK_HEIGHT
        zoom = self._current_zoom

        # Adaptive LOD: Beat-Dichte je nach Zoom
        if zoom < 0.5:
            step = 4  # Nur Downbeats
        elif zoom < 1.5:
            step = 2  # Halbe Beats
        else:
            step = 1  # Alle Beats

        # Pens fuer verschiedene Beat-Typen vorab instanziieren
        downbeat_pen = QPen(QColor(212, 175, 55, 140), 1, Qt.PenStyle.SolidLine)
        beat_pen = QPen(QColor(90, 90, 100, 60), 1, Qt.PenStyle.DotLine)
        half_beat_pen = QPen(QColor(60, 60, 70, 40), 1, Qt.PenStyle.DotLine)

        # Culling via binary search fuer sichtbares Intervall
        t_left = max(0.0, clip_rect.left()) / PIXELS_PER_SECOND
        t_right = clip_rect.right() / PIXELS_PER_SECOND

        idx_start = bisect.bisect_left(self._beat_times, t_left)
        idx_end = bisect.bisect_right(self._beat_times, t_right)

        # Sicherstellen, dass wir an der step-Grenze anfangen
        start_i = max(0, idx_start - (idx_start % step))
        end_i = min(idx_end + 1, len(self._beat_times))

        for i in range(start_i, end_i):
            if i % step != 0:
                continue

            t = self._beat_times[i]
            x = t * PIXELS_PER_SECOND
            is_downbeat = t in self._downbeat_times or (not self._downbeat_times and i % 4 == 0)

            if is_downbeat:
                pen = downbeat_pen
            elif i % 2 == 0:
                pen = beat_pen
            else:
                pen = half_beat_pen

            # Energy-basierte Opacity (falls verfuegbar)
            if self._energy_per_beat and i < len(self._energy_per_beat):
                e = max(0.2, min(1.0, self._energy_per_beat[i]))
                pen_color = pen.color()
                pen_color.setAlphaF(pen_color.alphaF() * e)
                pen = QPen(pen_color, pen.widthF(), pen.style())

            painter.setPen(pen)
            painter.drawLine(x, grid_top, x, grid_bottom)


# ======================================================================
# Draggable Timeline Clip
# ======================================================================

def _timeline_video_placeholder(width: int, height: int, label: str) -> QPixmap:
    pix = QPixmap(max(1, width), max(1, height))
    pix.fill(QColor("#18120a"))
    painter = QPainter(pix)
    painter.setPen(QColor("#d4a44a"))
    painter.setFont(QFont("Segoe UI Variable Text", 8, QFont.Weight.Bold))
    painter.drawText(QRectF(0, 0, width, height), Qt.AlignmentFlag.AlignCenter, label[:18])
    painter.end()
    return pix


def _timeline_video_thumbnail(file_path: str | None, width: int, height: int, label: str) -> QPixmap:
    if file_path:
        try:
            from ui.widgets.media_grid import _thumb_path
            thumb = _thumb_path(file_path)
            if thumb.exists():
                pix = QPixmap(str(thumb))
                if not pix.isNull():
                    return pix.scaled(
                        max(1, width),
                        max(1, height),
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.FastTransformation,
                    )
        except (ImportError, OSError, RuntimeError):
            pass
    return _timeline_video_placeholder(width, height, label)


class TimelineClipItem(QGraphicsRectItem):
    # Audio-Clips: refined slate blue
    AUDIO_COLOR = QColor(12, 18, 28, 35)
    AUDIO_COLOR_NO_WAVEFORM = QColor(45, 82, 145, 205)
    # Video-Clips: Premium Gold / Amber
    VIDEO_COLOR = QColor(212, 164, 74, 210)

    TRIM_ZONE = 6  # px from edge to activate trim handle

    def __init__(self, entry_id: int, media_id: int, track_type: str,
                 title: str, x: float, y: float, width: float, height: float,
                 on_moved=None, on_trimmed=None, has_waveform: bool = False,
                 anchors: list | None = None, thumbnail_file_path: str | None = None):
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

        # B-471 T1: kein synchroner Disk-Read mehr beim Item-Build. Erst
        # Placeholder; das echte Thumbnail wird viewport-lazy + async
        # nachgeladen (TimelineView._request_visible_thumbnails ->
        # set_thumbnail_pixmap). Verhindert 1132x ffmpeg/Disk-I/O auf dem
        # Main-Thread beim Aufbau.
        self.thumbnail_file_path = thumbnail_file_path
        self._thumb_w = max(24, min(int(width), 3000))
        self._thumb_h = max(16, int(height) - 6)
        self._thumbnail_item: QGraphicsPixmapItem | None = None
        self._thumbnail_status_label: QGraphicsTextItem | None = None
        if track_type == "video":
            pix = _timeline_video_placeholder(self._thumb_w, self._thumb_h, f"#{media_id}")
            self._thumbnail_item = QGraphicsPixmapItem(pix, self)
            self._thumbnail_item.setPos(0, 3)
            self._thumbnail_item.setOpacity(0.85)
            self._thumbnail_item.setZValue(3)
            thumb_status = "Thumbnail laedt" if thumbnail_file_path else "Thumbnail fehlt - Datei fehlt"
            status = QGraphicsTextItem(thumb_status, self)
            status.setDefaultTextColor(QColor(245, 205, 105, 230))
            status.setFont(QFont("Segoe UI Variable Text", 9, QFont.Weight.Bold))
            status.setPos(10, max(24, int(height) - 25))
            status.setZValue(5)
            status.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            self._thumbnail_status_label = status

        label = QGraphicsTextItem(title[:30], self)
        label.setDefaultTextColor(QColor(255, 255, 255))
        label.setFont(QFont("Segoe UI Variable Text", 9, QFont.Weight.Bold))
        label.setPos(6, 4)
        label.setZValue(6)
        # B-471 T3: Label ignoriert die View-Transform -> beim horizontalen Zoom
        # (wheelEvent self.scale) wird der Text NICHT mehr gestaucht/gestreckt,
        # sondern bleibt bei jedem Zoom-Level normal lesbar.
        label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self._label_item = label

        self._missing_waveform_label: QGraphicsTextItem | None = None
        if track_type == "audio" and not has_waveform:
            missing = QGraphicsTextItem("Waveform fehlt - Audioanalyse starten", self)
            missing.setDefaultTextColor(QColor(220, 230, 245, 210))
            missing.setFont(QFont("Segoe UI Variable Text", 9, QFont.Weight.Bold))
            missing.setPos(10, max(22, int(height) // 2 - 8))
            missing.setZValue(5)
            missing.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            self._missing_waveform_label = missing

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
        self._brain_v3_feedback_service = None
        self._brain_v3_feedback_context = None
        self._brain_v3_timeline_meta = {}
        self._brain_v3_feedback_enabled = True
        self._brain_v3_feedback_popup = None
        self._context_menu = None
        self._brain_v3_cut_id: int | None = None
        self._brain_v3_confidence: float | None = None
        self._brain_v3_confidence_bar = QGraphicsRectItem(
            QRectF(0, 0, width, 3), self
        )
        self._brain_v3_confidence_bar.setPen(QPen(Qt.PenStyle.NoPen))
        self._brain_v3_confidence_bar.setBrush(QBrush(QColor(255, 0, 48, 220)))
        self._brain_v3_confidence_bar.setZValue(12)
        self._brain_v3_confidence_bar.setVisible(False)
        # B-211: ALLE Anker-time_offsets (auch unsichtbare durch Trim) hier
        # halten. _anchor_markers enthaelt nur sichtbare; get_first_anchor_time
        # darf aber nicht von Trim-Sichtbarkeit abhaengen, sonst ergibt es
        # andere Werte als die DB-Query und ist semantisch broken
        # (besonders fuer eine kuenftige Auto-Edit-Pipeline).
        self._all_anchor_offsets: list[float] = []

        # Lock-Icon — rechts oben (SCHNITT-Redesign Phase 05 Task 5.2)
        self.lock_icon = LockIconItem(parent_width=width, parent_height=height, parent=self)
        self._locked: bool = False

        if anchors is not None:
            self._apply_anchors(anchors)
        else:
            self._load_anchors()

    def set_thumbnail_pixmap(self, pix) -> None:
        """B-471 T1: setzt das real generierte Thumbnail (vom async Loader)."""
        if self._thumbnail_item is None or pix is None:
            return
        try:
            scaled = pix.scaled(
                self._thumb_w, self._thumb_h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._thumbnail_item.setPixmap(scaled)
            if self._thumbnail_status_label is not None:
                self._thumbnail_status_label.setVisible(False)
        except RuntimeError:
            pass

    def _apply_anchors(self, anchors):
        """Zeichnet vorab geladene Anker (vermeidet N+1 DB-Queries)."""
        for anchor in anchors:
            # B-211: time_offset IMMER tracken — auch fuer Anker ausserhalb
            # des sichtbaren Trim-Bereichs. Der visible-Filter unten betrifft
            # nur das Zeichnen.
            self._all_anchor_offsets.append(float(anchor.time_offset))
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

    def _timeline_view(self):
        scene = self.scene()
        if scene is None:
            return None
        for view in scene.views():
            if hasattr(view, "_anchor_map"):
                return view
        return None

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
        # B-211: _all_anchor_offsets parallel pflegen.
        self._all_anchor_offsets.append(float(time_offset))
        timeline = self._timeline_view()
        if timeline is not None:
            from types import SimpleNamespace
            timeline._anchor_map.setdefault(self.entry_id, []).append(
                SimpleNamespace(id=anchor_id, time_offset=float(time_offset))
            )
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
        # B-211: _all_anchor_offsets parallel leeren.
        self._all_anchor_offsets.clear()
        timeline = self._timeline_view()
        if timeline is not None:
            timeline._anchor_map[self.entry_id] = []

    def get_first_anchor_time(self) -> float | None:
        """Gibt den Zeitstempel des ersten Ankers zurueck (relativ zum Clip-Start).

        B-077: Vorher synchroner DB-Read im Main-Thread → spuerbare Freezes
        bei 100+ Clips × HDD/NAS. Jetzt lokal aus ``_all_anchor_offsets``.

        B-211: liest aus ``_all_anchor_offsets`` (alle DB-Anker), NICHT aus
        ``_anchor_markers`` (nur sichtbare). Sonst werden Anker ausserhalb
        des Trim-Bereichs ignoriert → semantisch falsch fuer Auto-Edit-
        Pipelines, die den ersten Anker des Clips brauchen, unabhaengig
        von der UI-Trim-Sichtbarkeit.
        """
        if not self._all_anchor_offsets:
            return None
        return min(self._all_anchor_offsets)

    def contextMenuEvent(self, event):
        """Rechtsklick-Kontextmenue mit Anker-Optionen."""
        self.show_context_menu_at(
            screen_pos=event.screenPos(),
            local_x=event.pos().x(),
        )

    def show_context_menu_at(self, screen_pos, local_x: float) -> None:
        """Zeigt das Clip-Kontextmenue auch fuer View-Fallbacks."""
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background: #1A1A1A; color: #E0E0E0; border: 1px solid #333; }"
            "QMenu::item:selected { background: rgba(212,175,55,0.15); color: #E8CC6A; }"
        )

        # Anker setzen an Mausposition
        time_offset = local_x / PIXELS_PER_SECOND
        set_anchor_action = menu.addAction(f"Anker setzen ({time_offset:.2f}s)")
        set_anchor_action.triggered.connect(lambda: self.add_anchor_at(local_x))

        # Alle Anker entfernen
        # B-384: auch Anker ausserhalb der sichtbaren Clip-Breite (nur in
        # _all_anchor_offsets, ohne Marker) muessen entfernbar bleiben.
        if self._anchor_markers or self._all_anchor_offsets:
            remove_action = menu.addAction("Alle Anker entfernen")
            remove_action.triggered.connect(self.remove_all_anchors)

        menu.addSeparator()
        info_action = menu.addAction(f"Clip: {self.track_type} | ID: {self.media_id}")
        info_action.setEnabled(False)

        if self._brain_v3_feedback_enabled:
            menu.addSeparator()
            brain_action = menu.addAction("Brain V3: Cut bewerten")
            brain_action.triggered.connect(self._open_brain_v3_feedback_popup)

        self._context_menu = menu
        menu.aboutToHide.connect(lambda: setattr(self, "_context_menu", None))
        menu.popup(screen_pos)

    def set_brain_v3_feedback(self, service=None, context=None, enabled: bool = True) -> None:
        """Verdrahtet Brain-V3-Feedback fuer diesen Timeline-Clip."""
        self._brain_v3_feedback_service = service
        self._brain_v3_feedback_context = context
        self._brain_v3_feedback_enabled = bool(enabled)

    def set_brain_v3_cut_id(self, cut_id: int | None) -> None:
        self._brain_v3_cut_id = int(cut_id) if cut_id is not None else None

    def _brain_v3_feedback_cut_id(self) -> int:
        return int(self._brain_v3_cut_id if self._brain_v3_cut_id is not None else self.entry_id)

    def _get_brain_v3_feedback_service(self):
        if self._brain_v3_feedback_service is None:
            from services.brain_v3.brain_v3_service import BrainV3Service

            self._brain_v3_feedback_service = BrainV3Service()
        return self._brain_v3_feedback_service

    def _submit_brain_v3_feedback(self, rating: str) -> int:
        from services.brain_v3.schemas.brain_v3_schemas import FeedbackRequest

        svc = self._get_brain_v3_feedback_service()
        resp = svc.feedback(
            FeedbackRequest(cut_id=self._brain_v3_feedback_cut_id(), rating=rating),
            context=self._brain_v3_feedback_context,
        )
        return int(getattr(resp, "n_buckets_updated", 0))

    def _open_brain_v3_feedback_popup(self) -> None:
        from ui.widgets.brain_v3_feedback_popup import BrainV3FeedbackPopup

        if self._brain_v3_feedback_popup is not None and self._brain_v3_feedback_popup.isVisible():
            self._brain_v3_feedback_popup.raise_()
            self._brain_v3_feedback_popup.activateWindow()
            return
        popup = BrainV3FeedbackPopup(
            cut_id=self._brain_v3_feedback_cut_id(),
            service=self._brain_v3_feedback_service,
            context=self._brain_v3_feedback_context,
            cut_label=f"{self.title} | Timeline #{self.entry_id}",
        )
        self._brain_v3_feedback_popup = popup
        popup.finished.connect(lambda _code: setattr(self, "_brain_v3_feedback_popup", None))
        popup.open()

    def set_brain_v3_confidence(self, confidence: float | None) -> None:
        if confidence is None:
            self._brain_v3_confidence = None
            self._brain_v3_confidence_bar.setVisible(False)
            return
        c = max(0.0, min(1.0, float(confidence)))
        self._brain_v3_confidence = c
        from ui.widgets.brain_v3_feedback_popup import confidence_color_hex

        self._brain_v3_confidence_bar.setBrush(QBrush(QColor(confidence_color_hex(c))))
        self._resize_brain_v3_confidence_bar()
        self._brain_v3_confidence_bar.setVisible(True)

    def _resize_brain_v3_confidence_bar(self) -> None:
        self._brain_v3_confidence_bar.setRect(QRectF(0, 0, self._clip_width, 3))

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
        """Trim-Modus starten wenn auf Handle geklickt; Lock-Icon-Klick togglet."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Lock-Icon zuerst pruefen — hat Vorrang vor Trim-Handle (Phase 05 Task 5.3)
            if self._hit_lock_icon(event.pos()):
                self._handle_lock_icon_click()
                event.accept()
                return
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
        if getattr(self, "_trim_mode", None):
            delta_x = event.scenePos().x() - self._trim_start_mouse_x
            min_width = 10  # minimal 10px

            if self._trim_mode == "right":
                new_width = max(min_width, self._trim_start_width + delta_x)
                self.setRect(QRectF(0, 0, new_width, self._clip_height))
                self._clip_width = new_width
                self._right_handle.setRect(QRectF(new_width - 3, 0, 3, self._clip_height))
                self._resize_brain_v3_confidence_bar()
            elif self._trim_mode == "left":
                max_delta = self._trim_start_width - min_width
                clamped = max(-self._trim_start_pos_x, min(delta_x, max_delta))
                new_width = self._trim_start_width - clamped
                new_x = self._trim_start_pos_x + clamped
                self.setRect(QRectF(0, 0, new_width, self._clip_height))
                self._clip_width = new_width
                self.setPos(new_x, self._track_y)
                self._resize_brain_v3_confidence_bar()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def itemChange(self, change, value):
        if getattr(self, "_trim_mode", None):
            return super().itemChange(change, value)
        if change == QGraphicsRectItem.GraphicsItemChange.ItemPositionChange:
            # Drag-Start merken (erste Bewegung).
            # P8-A1-FIX: Duration aus der Item-Breite ableiten, NICHT aus der DB.
            # Vorher: nullpool_session()+session.get(TimelineEntry) bei JEDEM
            # Drag-Start — blockierte den Qt-Event-Loop bei jeder Maus-Bewegung
            # ueber einen nicht-selektierten Clip. Die Breite ist sowieso im
            # Item gespeichert (wird beim Trim aktualisiert), also lokal.
            if self._drag_start_x is None:
                self._drag_start_x = self.pos().x()
                self._drag_duration = self._clip_width / PIXELS_PER_SECOND
            new_pos = QPointF(max(0, value.x()), self._track_y)
            return new_pos
        if change == QGraphicsRectItem.GraphicsItemChange.ItemPositionHasChanged:
            if self.on_moved:
                self.on_moved(self.entry_id, value.x())
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        """Drag-Start oder Trim beenden."""
        if getattr(self, "_trim_mode", None):
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

    # ------------------------------------------------------------------
    # Lock-State (SCHNITT-Redesign Phase 05 Task 5.2)
    # ------------------------------------------------------------------
    def is_locked(self) -> bool:
        return self._locked

    def set_locked(self, locked: bool) -> None:
        self._locked = bool(locked)
        self.lock_icon.set_locked(self._locked)
        # Goldrand bei Lock
        if self._locked:
            self.setPen(QPen(QColor(212, 164, 74, 255), 2))
        else:
            self.setPen(QPen(self._base_color.darker(120), 1))

    def _hit_lock_icon(self, local_pos) -> bool:
        rect = self.lock_icon.boundingRect().translated(self.lock_icon.pos())
        return rect.contains(local_pos)

    def _handle_lock_icon_click(self, *, force: bool = False) -> None:
        new = not self._locked
        self.set_locked(new)
        from ui.undo_commands import ToggleClipLockCommand
        scene = self.scene()
        view = scene.views()[0] if (scene and scene.views()) else None
        cmd = ToggleClipLockCommand(self.entry_id, new, timeline=view)
        if force:
            # In Tests ohne aktive Scene/UndoStack direkt persistieren
            cmd.redo()
            return
        stack = getattr(view, "undo_stack", None) if view is not None else None
        if stack is not None:
            stack.push(cmd)
        else:
            cmd.redo()


# ======================================================================
# Interactive Timeline (QGraphicsView) — Performance Optimized
# ======================================================================

class InteractiveTimeline(QGraphicsView):
    clip_moved = Signal(int, float)
    selection_changed = Signal(list)  # emits list of dicts with clip data
    _BUILD_BATCH_SIZE = 25

    # T8.1: Feedback shortcut signal — emits event_id after a successful DB write.
    # B-197 F-3: ``_notify_memory_updater`` ruft jetzt direkt
    # ``MemoryUpdaterWorker.notify_feedback()`` auf dem modulweiten Singleton.
    # Das Signal bleibt fuer externe Listener bestehen (z.B. Tests, andere
    # UI-Komponenten die auf Feedback reagieren).
    feedback_event_emitted = Signal(int)

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
        # P8-B1-FIX: Kein Full-Antialiasing mehr. Bei 101 Clips + 7200 Beat-
        # Linien + Waveform-Tiles rechnet Qt sonst AA fuer alle Items bei
        # jedem Paint — merklicher Scroll-Lag. TextAntialiasing reicht fuer
        # Clip-Labels und Ruler; Linien profitieren kaum von AA.
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
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
        self._pending_entry_build: dict | None = None

        # B-471 T1: viewport-lazy thumbnail generation. Nur sichtbare Video-
        # Clips bekommen ihr Thumbnail async (ffmpeg via _ThumbWorker),
        # max 2 parallel, jede Datei genau einmal.
        from ui.timeline_thumbnail_loader import ThumbnailLoadManager
        self._thumb_items_by_path: dict[str, list[TimelineClipItem]] = {}
        self._thumb_threads: list = []
        self._thumb_loader = ThumbnailLoadManager(self._start_thumb_worker, max_concurrent=2)
        self._thumb_request_timer = QTimer(self)
        self._thumb_request_timer.setSingleShot(True)
        self._thumb_request_timer.setInterval(120)
        self._thumb_request_timer.timeout.connect(self._request_visible_thumbnails)
        self.horizontalScrollBar().valueChanged.connect(self._schedule_thumb_request)

        # Beat Grid Overlay + Section Colors (AUD-70)
        self._section_items: list = []        # Section color backgrounds
        self._beat_grid_items: list = []      # Adaptive beat grid lines
        self._drop_markers: list = []         # Drop event markers
        self._current_zoom: float = 1.0       # Current horizontal zoom factor
        self._beat_grid_item = BeatGridItem()
        self._scene.addItem(self._beat_grid_item)

        # Drop indicator (visual feedback during drag-over)
        self._drop_indicator: QGraphicsLineItem | None = None
        self._drop_ghost: QGraphicsRectItem | None = None

        # AUD-71: Playhead, shuttle state and internal clipboard
        self._playhead_time: float = 0.0   # Current playhead position in seconds
        self._shuttle_speed: int = 0        # JKL shuttle: -2,-1,0,1,2
        self._clipboard: list[dict] = []    # Ctrl+C/V internal clip clipboard

        # B-200: In/Out-Point-State. Vorher war das Wiring kaputt — die
        # ``set_in_point`` / ``set_out_point``-Signals feuerten bei den
        # Tasten I / O, aber NIEMAND subscribte. Damit waren die Tasten
        # funktionslos. Bis ein echter Trim-Worker existiert, halten wir
        # die Werte mindestens lokal vor und loggen sie via console_log,
        # damit der User Feedback bekommt.
        self._in_point: float | None = None
        self._out_point: float | None = None
        self.set_in_point.connect(self._on_set_in_point_local)
        self.set_out_point.connect(self._on_set_out_point_local)

        # T8.1: Feedback shortcuts — active pacing run + service
        self._active_pacing_run_id: int | None = None
        from services.feedback_service import FeedbackService
        self._feedback_service: FeedbackService = FeedbackService(
            session_factory=nullpool_session
        )
        self._brain_v3_feedback_service = None
        self._brain_v3_feedback_context = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.viewport().setFocusPolicy(Qt.FocusPolicy.StrongFocus)

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
            QPen(QColor(48, 58, 72, 100), 1), QBrush(QColor(9, 14, 22))
        )
        audio_bg.setZValue(-10)
        self._track_bg_items.append(audio_bg)
        video_bg = self._scene.addRect(
            QRectF(0, VIDEO_TRACK_Y, w, TRACK_HEIGHT),
            QPen(QColor(68, 56, 32, 110), 1), QBrush(QColor(15, 13, 10))
        )
        video_bg.setZValue(-10)
        self._track_bg_items.append(video_bg)

    def _draw_labels(self):
        for label_text, y in [("A1", AUDIO_TRACK_Y), ("V1", VIDEO_TRACK_Y)]:
            txt = self._scene.addText(label_text, QFont("Segoe UI", 11, QFont.Weight.Bold))
            txt.setDefaultTextColor(QColor(150, 160, 175))
            txt.setPos(-42, y + 25)
            txt.setZValue(10)

    def _cancel_pending_db_load(self):
        """M3-FIX: Laufenden DB-Worker canceln/disconnecten bevor ein neuer gestartet wird.
        B-283-FIX: shiboken-Guards und robustere Sequenz.
        """
        logger.debug("[B-283] _cancel_pending_db_load started")
        self._cancel_pending_entry_build()
        
        import shiboken6
        
        if hasattr(self, '_db_worker') and self._db_worker is not None:
            try:
                if shiboken6.isValid(self._db_worker):
                    logger.debug("[B-283] Disconnecting old worker signals")
                    self._db_worker.finished.disconnect(self._on_db_load_finished)
                else:
                    logger.debug("[B-283] Old worker is invalid (already deleted)")
            except (TypeError, RuntimeError) as e:
                logger.debug("[B-283] Disconnect failed (expected): %s", e)
        
        if hasattr(self, '_db_thread') and self._db_thread is not None:
            try:
                if shiboken6.isValid(self._db_thread):
                    if self._db_thread.isRunning():
                        logger.debug("[B-283] Stopping old db_thread")
                        self._db_thread.quit()
                        if not self._db_thread.wait(1500):
                            logger.warning("[B-283] db_thread didn't stop, continuing anyway")
                    else:
                        logger.debug("[B-283] db_thread not running")
                else:
                    logger.debug("[B-283] Old thread is invalid")
            except RuntimeError as e:
                logger.debug("[B-283] Thread wait/check failed: %s", e)
            
            self._db_worker = None
            self._db_thread = None
        logger.debug("[B-283] _cancel_pending_db_load finished")

    def load_from_db(self, project_id: int | None = None):
        """Asynchrones Laden der Timeline-Daten (Fix für Main-Thread Blocking)."""
        logger.debug("[B-283] load_from_db called for project_id=%s", project_id)
        # M3-FIX: Alten Worker canceln bevor ein neuer gestartet wird
        self._cancel_pending_db_load()

        if project_id is None:
            from database import get_active_project_id
            project_id = get_active_project_id()

        # UI sofort bereinigen.
        # B-470 Stack A: Der Szene-Teardown laeuft synchron auf dem Main-Thread.
        # Ohne stummgeschaltete Viewport-Updates triggert JEDES removeItem() einen
        # partiellen Repaint -> bei vielen Items ~7s Freeze beim Projekt-Switch
        # (live gemessen via perf-watchdog Sampled Stack:
        # _on_project_changed -> load_from_db -> clip_items.clear()). Spiegelt die
        # Build-Seite (_start_batched_entry_build), die Updates ebenfalls mutet.
        _vp = self.viewport()
        _vp.setUpdatesEnabled(False)
        try:
            for item in self.clip_items:
                self._scene.removeItem(item)
            self.clip_items.clear()
            # B-471 T1: Thumbnail-Registry + Scheduler zuruecksetzen (Done-Set
            # bleibt erhalten -> bereits generierte Thumbs werden nicht neu erzeugt).
            self._thumb_items_by_path.clear()
            self._thumb_loader.reset()
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
        finally:
            _vp.setUpdatesEnabled(True)

        # Hintergrund-Worker für die Datenbankabfrage
        from PySide6.QtCore import QObject, Signal, QThread
        
        class TimelineDBWorker(QObject):
            # PySide queued signals with typed dict arguments drop dicts that
            # contain detached SQLAlchemy objects. Use object to preserve maps.
            finished = Signal(object, object, object, object, object)  # entries, audio_map, video_map, anchor_map, brain_meta
            
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
                            {t.id: t for t in session.query(AudioTrack).options(
                                joinedload(AudioTrack.waveform_data),
                                joinedload(AudioTrack.beatgrid),
                            ).filter(
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
                        try:
                            from services.brain_v3.timeline_state import (
                                load_current_timeline_metadata,
                            )
                            # B-383: sync_current_timeline_from_entries removed to prevent mutations to state.db on read path
                            pass
                            _brain_meta = load_current_timeline_metadata()
                        except Exception as brain_exc:
                            logger.debug("Brain V3 Timeline-Metadata nicht geladen: %s", brain_exc)
                            _brain_meta = {}

                        self.finished.emit(entries, _audio_map, _video_map, _anchor_map, _brain_meta)
                except Exception as e:
                    logger.error("TimelineDBWorker Fehler: %s", e)
                    self.finished.emit([], {}, {}, {}, {})

        self._db_worker = TimelineDBWorker(project_id)
        self._db_thread = QThread(self)
        self._db_worker.moveToThread(self._db_thread)
        
        self._db_worker.finished.connect(self._on_db_load_finished)
        self._db_worker.finished.connect(self._db_thread.quit)
        self._db_thread.finished.connect(self._db_thread.deleteLater)
        # B-107 / BUG-A11: also schedule the worker for deletion so
        # every project-switch / timeline-reload doesn't leak a
        # TimelineDBWorker C++ shell.
        self._db_thread.finished.connect(self._db_worker.deleteLater)
        self._db_thread.started.connect(self._db_worker.run)
        
        self._db_thread.start()

    def _on_db_load_finished(self, entries, audio_map, video_map, anchor_map, brain_meta=None):
        """Wird aufgerufen, sobald die Daten vom Hintergrund-Thread geladen wurden.

        P8-E-FIX: Viewport-Updates waehrend des Aufbaus von 101+ Items
        stummschalten. Sonst triggert jeder addItem/Draw einen partial
        paint, die Summe blockiert den Main-Thread spuerbar.
        """
        self._anchor_map = anchor_map
        self._brain_v3_timeline_meta = brain_meta or {}
        audio_map, video_map = self._recover_missing_media_maps(entries, audio_map, video_map)
        self._start_batched_entry_build(entries, audio_map, video_map, anchor_map)

    def _recover_missing_media_maps(self, entries, audio_map, video_map):
        """B-471 live hardening: recover media maps if worker delivered entries only."""
        missing_audio_ids = {
            e.media_id for e in entries
            if e.track == "audio" and e.media_id not in audio_map
        }
        missing_video_ids = {
            e.media_id for e in entries
            if e.track == "video" and e.media_id not in video_map
        }
        if not missing_audio_ids and not missing_video_ids:
            return audio_map, video_map

        audio_map = dict(audio_map)
        video_map = dict(video_map)
        try:
            with DBSession(engine) as session:
                if missing_audio_ids:
                    for track in session.query(AudioTrack).options(
                        joinedload(AudioTrack.waveform_data),
                        joinedload(AudioTrack.beatgrid),
                    ).filter(
                        AudioTrack.id.in_(missing_audio_ids),
                        AudioTrack.deleted_at.is_(None),
                    ).all():
                        audio_map[track.id] = track
                if missing_video_ids:
                    for clip in session.query(VideoClip).filter(
                        VideoClip.id.in_(missing_video_ids),
                        VideoClip.deleted_at.is_(None),
                    ).all():
                        video_map[clip.id] = clip
                session.expunge_all()
            logger.warning(
                "[B-471] recovered missing timeline media maps: audio=%d video=%d",
                len(missing_audio_ids), len(missing_video_ids),
            )
        except Exception as exc:
            logger.warning("[B-471] media map recovery failed: %s", exc)
        return audio_map, video_map

    def _cancel_pending_entry_build(self) -> None:
        """Stoppt einen laufenden inkrementellen Scene-Aufbau."""
        if self._pending_entry_build is not None:
            self._pending_entry_build = None
            try:
                self.viewport().setUpdatesEnabled(True)
            except RuntimeError:
                pass

    def _start_batched_entry_build(self, entries, audio_map, video_map, anchor_map) -> None:
        """B-275: baut Timeline-Items in kleinen GUI-Thread-Chunks."""
        self._cancel_pending_entry_build()
        vp = self.viewport()
        vp.setUpdatesEnabled(False)
        self._pending_entry_build = {
            "entries": list(entries),
            "audio_map": audio_map,
            "video_map": video_map,
            "anchor_map": anchor_map,
            "index": 0,
            "max_end": 0.0,
        }
        QTimer.singleShot(0, self._build_entry_batch)

    def _build_entry_batch(self) -> None:
        state = self._pending_entry_build
        if state is None:
            return

        entries = state["entries"]
        start = state["index"]
        end = min(start + self._BUILD_BATCH_SIZE, len(entries))
        for entry in entries[start:end]:
            clip_end = self._build_entry_item(
                entry,
                state["audio_map"],
                state["video_map"],
                state["anchor_map"],
            )
            if clip_end is not None and clip_end > state["max_end"]:
                state["max_end"] = clip_end
        state["index"] = end

        if end < len(entries):
            QTimer.singleShot(0, self._build_entry_batch)
            return

        self._pending_entry_build = None
        self._total_duration = state["max_end"]
        self._draw_track_backgrounds()
        self._update_scene_rect()
        vp = self.viewport()
        vp.setUpdatesEnabled(True)
        vp.update()
        self._schedule_thumb_request()  # B-471 T1: lazy thumbs fuer sichtbare Clips
        logger.info("[T1] build done: registered_paths=%d clips=%d",
                    len(self._thumb_items_by_path), len(self.clip_items))

    def _build_entries(self, entries, audio_map, video_map, anchor_map):
        max_end = 0.0
        for entry in entries:
            clip_end = self._build_entry_item(entry, audio_map, video_map, anchor_map)
            if clip_end is not None and clip_end > max_end:
                max_end = clip_end
        self._total_duration = max_end
        self._draw_track_backgrounds()
        self._update_scene_rect()

    def _build_entry_item(self, entry, audio_map, video_map, anchor_map) -> float | None:
        def _entry_duration(fallback: float) -> float:
            start = float(entry.start_time or 0.0)
            end_time = getattr(entry, "end_time", None)
            if end_time is not None:
                duration = float(end_time) - start
                if duration > 1e-3:
                    return duration
            return fallback

        has_waveform = False
        if entry.track == "audio":
            track = audio_map.get(entry.media_id)
            title = track.title if track else "?"
            dur = _entry_duration(track.duration if track and track.duration else 30.0)
            y = AUDIO_TRACK_Y

            # waveform_data + beatgrid sind im AudioTrack-Model lazy='joined'
            # und werden vom TimelineDBWorker bereits mitgeladen. Kein neuer
            # DBSession/merge-Dance im Main-Thread noetig (P8-Folge-Fix:
            # eliminiert 2s MetaCall-Freeze beim ersten Timeline-Render mit
            # vielen Audio-Clips).
            if track and track.waveform_data:
                has_waveform = True

        elif entry.track == "video":
            clip = video_map.get(entry.media_id)
            title = Path(clip.file_path).stem if clip else "?"
            dur = _entry_duration(clip.duration if clip and clip.duration else 10.0)
            y = VIDEO_TRACK_Y
        else:
            return None

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
            thumbnail_file_path=str(clip.file_path) if entry.track == "video" and clip else None,
        )
        item.set_brain_v3_feedback(
            service=self._brain_v3_feedback_service,
            context=self._brain_v3_feedback_context,
        )
        # SCHNITT-Redesign Phase 05 Task 5.3: locked-Flag aus DB uebernehmen
        item.set_locked(bool(getattr(entry, "locked", False)))
        self._apply_brain_v3_timeline_metadata(item, entry)
        self._scene.addItem(item)
        self.clip_items.append(item)
        self._register_clip_thumbnail(item)

        if entry.track == "audio" and has_waveform:
            # B-471 Follow-up: TimelineDBWorker hat waveform_data bereits
            # geladen. Direkt aus diesem Snapshot zeichnen, sonst endet der
            # Live-Build sichtbar mit waveform_items=0 und die Wellenform
            # taucht erst spaet oder gar nicht auf.
            self._load_waveform_for_track(None, track, entry, dur, y)
        return entry.start_time + dur

    # ── B-471 T1: viewport-lazy thumbnail loading ─────────────────────────
    def _register_clip_thumbnail(self, item: "TimelineClipItem") -> None:
        """Merkt ein Video-Clip-Item fuer spaeteres lazy Thumbnail-Laden."""
        fp = getattr(item, "thumbnail_file_path", None)
        if item.track_type != "video" or not fp:
            return
        self._thumb_items_by_path.setdefault(str(fp), []).append(item)

    def _schedule_thumb_request(self) -> None:
        """Coalesct Viewport-Aenderungen (Scroll/Zoom/Build) zu einem Request."""
        try:
            self._thumb_request_timer.start()
        except RuntimeError:
            pass

    def _request_visible_thumbnails(self) -> None:
        """Fordert Thumbnails fuer aktuell sichtbare Video-Clips an (lazy)."""
        if not self._thumb_items_by_path:
            logger.info("[T1] request_visible: keine registrierten Thumbnail-Pfade")
            return
        try:
            view_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        except RuntimeError:
            return
        # etwas Vorlauf, damit knapp ausserhalb liegende Clips vorgeladen werden
        view_rect.adjust(-300.0, 0.0, 300.0, 0.0)
        requested = 0
        for fp, items in list(self._thumb_items_by_path.items()):
            if self._thumb_loader.is_done(fp):
                continue
            for it in items:
                try:
                    if it.sceneBoundingRect().intersects(view_rect):
                        before = self._thumb_loader.inflight_count + self._thumb_loader.queued_count
                        self._thumb_loader.request(fp)
                        if (self._thumb_loader.inflight_count
                                + self._thumb_loader.queued_count) > before:
                            requested += 1
                        break
                except RuntimeError:
                    continue
        logger.info(
            "[T1] request_visible: paths=%d view=(%.0f..%.0f) new_requests=%d inflight=%d",
            len(self._thumb_items_by_path), view_rect.left(), view_rect.right(),
            requested, self._thumb_loader.inflight_count,
        )

    def _start_thumb_worker(self, file_path: str) -> None:
        """Startet einen async _ThumbWorker (ffmpeg) fuer eine Clip-Datei."""
        try:
            from ui.widgets.media_grid import _ThumbWorker
            logger.info("[T1] thumb worker start: %s", file_path)
            thumb_h = max(16, TRACK_HEIGHT - 6)
            thread = QThread()
            worker = _ThumbWorker(file_path, 220, thumb_h)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.done.connect(self._on_thumb_ready)
            worker.done.connect(lambda _p, _i, t=thread: t.quit())
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(lambda w=worker: w.deleteLater())
            thread.finished.connect(lambda t=thread: self._thumb_threads.remove(t)
                                    if t in self._thumb_threads else None)
            self._thumb_threads.append(thread)
            thread.start()
        except Exception as exc:  # noqa: BLE001 — Thumbnail darf nie die UI killen
            logger.debug("Thumbnail-Worker-Start fehlgeschlagen (%s): %s", file_path, exc)
            self._thumb_loader.on_done(file_path)

    def _on_thumb_ready(self, file_path: str, qimage) -> None:
        """GUI-Thread-Slot: wandelt QImage->QPixmap und setzt es auf alle Items."""
        from PySide6.QtGui import QPixmap
        try:
            pix = QPixmap.fromImage(qimage)
        except (RuntimeError, TypeError):
            pix = None
        if pix is not None and not pix.isNull():
            for it in self._thumb_items_by_path.get(str(file_path), []):
                it.set_thumbnail_pixmap(pix)
        self._thumb_loader.on_done(str(file_path))

    def _style_visible_waveform(self, wf_item: WaveformGraphicsItem, parent_clip: TimelineClipItem | None = None) -> None:
        """Macht 3-Band-Waveform und Beatgrid sichtbar ueber der Clip-Flaeche."""
        try:
            wf_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent, False)
            base_z = parent_clip.zValue() if parent_clip is not None else 2.0
            wf_item.setZValue(base_z + 2.0)
            wf_item.setOpacity(0.96)
        except RuntimeError:
            pass

    def _apply_brain_v3_timeline_metadata(self, item: TimelineClipItem, entry) -> None:
        if item.track_type != "video":
            return
        key = (int(entry.media_id), int(round(float(entry.start_time or 0.0) * 1000.0)))
        meta = self._brain_v3_timeline_meta.get(key)
        if meta is None:
            return
        item.set_brain_v3_cut_id(getattr(meta, "cut_id", None))
        item.set_brain_v3_confidence(getattr(meta, "confidence", None))

    def _load_waveform_async(self, media_id: int, start_time: float, duration: float, y: float, clip_item: TimelineClipItem):
        """Startet das asynchrone Laden der Wellenform im Hintergrund."""
        import shiboken6
        worker = WaveformLoadWorker(media_id)
        thread = QThread(self)
        worker.moveToThread(thread)

        if not hasattr(self, "_waveform_workers"):
            self._waveform_workers = []
        self._waveform_workers.append((worker, thread))

        def on_done(track, band_low, band_mid, band_high, beat_positions):
            try:
                if track and shiboken6.isValid(clip_item):
                    # Erstelle das WaveformGraphicsItem im Main-Thread als Child des Clip-Items
                    wf_item = WaveformGraphicsItem(
                        band_low=band_low,
                        band_mid=band_mid,
                        band_high=band_high,
                        duration=duration,
                        beat_positions=beat_positions,
                        pixels_per_second=self._pps if hasattr(self, "_pps") else PIXELS_PER_SECOND,
                        height=TRACK_HEIGHT,
                        parent=clip_item,
                    )
                    wf_item.setPos(0, 0)  # Position relativ zum Parent
                    self._style_visible_waveform(wf_item, parent_clip=clip_item)
                    self.waveform_items.append(wf_item)
            finally:
                if (worker, thread) in self._waveform_workers:
                    self._waveform_workers.remove((worker, thread))
                thread.quit()

        worker.finished.connect(on_done)
        thread.started.connect(worker.run)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)
        thread.start()

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
        self._style_visible_waveform(wf_item)
        self._scene.addItem(wf_item)
        self.waveform_items.append(wf_item)

    def add_clip(self, entry_id: int, media_id: int, track_type: str,
                 title: str, start_time: float, duration: float):
        y = AUDIO_TRACK_Y if track_type == "audio" else VIDEO_TRACK_Y
        width = duration * PIXELS_PER_SECOND
        x = start_time * PIXELS_PER_SECOND

        # Rekordbox Waveform für Audio-Clips laden
        has_waveform = False
        thumbnail_file_path = None
        if track_type == "audio":
            with DBSession(engine) as session:
                track = session.query(AudioTrack).filter(
                    AudioTrack.id == media_id, AudioTrack.deleted_at.is_(None)
                ).first()
                if track and track.waveform_data:
                    has_waveform = True
        elif track_type == "video":
            with DBSession(engine) as session:
                clip = session.query(VideoClip).filter(
                    VideoClip.id == media_id, VideoClip.deleted_at.is_(None)
                ).first()
                thumbnail_file_path = str(clip.file_path) if clip else None

        item = TimelineClipItem(
            entry_id=entry_id, media_id=media_id, track_type=track_type,
            title=title, x=x, y=y, width=width, height=TRACK_HEIGHT,
            on_moved=self._on_clip_moved, on_trimmed=self._on_clip_trimmed,
            has_waveform=has_waveform,
            anchors=[],  # P8-A2-FIX: neue Clips haben keine Anker → keine DB-Query
            thumbnail_file_path=thumbnail_file_path,
        )
        item.set_brain_v3_feedback(
            service=self._brain_v3_feedback_service,
            context=self._brain_v3_feedback_context,
        )
        self._scene.addItem(item)
        self.clip_items.append(item)
        self._register_clip_thumbnail(item)

        if track_type == "audio" and has_waveform:
            # Asynchrones Laden im Hintergrund, kein UI-Blocking beim Drop
            self._load_waveform_async(media_id, start_time, duration, y, item)
        self._update_scene_rect()
        self._schedule_thumb_request()

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
        """Zeichnet ein adaptives Beat-Grid auf die Timeline via BeatGridItem.

        Das Grid passt die Dichte automatisch an den Zoom-Level an.
        """
        for marker in self._drop_markers:
            if marker not in self._section_items:
                self._scene.removeItem(marker)
        self._drop_markers.clear()

        if not beat_times:
            self._beat_grid_item.set_data([], [], [], self._current_zoom)
            self._beat_times = []
            return

        self._beat_times = beat_times
        self._downbeat_times = downbeat_times or []
        self._energy_per_beat = energy_per_beat or []

        self._beat_grid_item.set_data(
            beat_times,
            downbeat_times,
            energy_per_beat,
            self._current_zoom
        )

    def _clear_beat_grid(self):
        self._beat_grid_item.set_data([], [], [], self._current_zoom)
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
        if not self._beat_times:
            return
        self._beat_grid_item.update_zoom(self._current_zoom)

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

    def _sync_clip_lock_visual(self, entry_id: int, locked: bool) -> None:
        """Synchronisiert die visuelle Lock-Anzeige nach DB-Toggle.

        SCHNITT-Redesign 2026-05-09 Tier-1 Hardening (D11):
        ToggleClipLockCommand.redo/undo ruft das nach dem DB-Write,
        damit Goldrand + Lock-Icon ohne Full-Reload mitziehen.
        """
        item = self._find_clip_item(entry_id)
        if item is not None:
            item.set_locked(bool(locked))

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

    def showEvent(self, event):
        super().showEvent(event)
        # B-471 T1: View wurde sichtbar (z.B. Tab-Wechsel zu SCHNITT). Erst jetzt
        # ist viewport().rect() gueltig -> sichtbare Thumbnails anfordern. Ohne
        # diesen Trigger blieb der Build-Zeit-Request (View noch versteckt) wirkungslos.
        self._schedule_thumb_request()

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
        self._schedule_thumb_request()  # B-471 T1: Zoom aendert sichtbaren Clip-Satz

    def mousePressEvent(self, event):
        """Fokus für Timeline-Hotkeys setzen + mittlere Maustaste startet Panning.

        B-438: Zuvor existierten ZWEI mousePressEvent-Definitionen in dieser
        Klasse — die spätere (nur Fokus) überschrieb die frühere (Panning),
        wodurch Mittlere-Maustaste-Panning tot war. Beide hier zusammengeführt.
        (AUD-71: Space ist Play/Pause.)
        """
        # Fokus immer setzen, damit Timeline-Hotkeys nach einem Klick greifen
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.viewport().setFocus(Qt.FocusReason.MouseFocusReason)
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

        # T8.1: Feedback shortcuts (A/R/S/1-5) — only when a pacing run is active
        # and exactly one TimelineClipItem is selected.
        selected = [
            item
            for item in self._scene.selectedItems()
            if isinstance(item, TimelineClipItem)
        ]
        if len(selected) == 1 and not shift:
            brain_rating_map = {
                Qt.Key.Key_1: "perfect",
                Qt.Key.Key_2: "fits",
                Qt.Key.Key_3: "not_quite",
                Qt.Key.Key_4: "no_match",
            }
            if key in brain_rating_map and selected[0]._brain_v3_feedback_enabled:
                try:
                    selected[0]._submit_brain_v3_feedback(brain_rating_map[key])
                    event.accept()
                except Exception as exc:
                    logger.warning("Brain-V3 timeline feedback failed: %s", exc)
                return

        if self._active_pacing_run_id is not None:
            if len(selected) == 1:
                clip_item = selected[0]
                scene_id = self._resolve_scene_id(clip_item)
                if scene_id is not None:
                    verdict_map = {
                        Qt.Key.Key_A: "accept",
                        Qt.Key.Key_R: "reject",
                        Qt.Key.Key_S: "skip",
                    }
                    if key in verdict_map and not shift:
                        result = self._feedback_service.record_verdict(
                            self._active_pacing_run_id, scene_id, verdict_map[key]
                        )
                        if result.success and result.event_id is not None:
                            self.feedback_event_emitted.emit(result.event_id)
                            self._notify_memory_updater()
                        return
                    # Ratings 1-5
                    for i in range(1, 6):
                        if key == getattr(Qt.Key, f"Key_{i}"):
                            result = self._feedback_service.record_rating(
                                self._active_pacing_run_id, scene_id, i
                            )
                            if result.success and result.event_id is not None:
                                self.feedback_event_emitted.emit(result.event_id)
                                self._notify_memory_updater()
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

    # ── T8.1: Feedback shortcut helpers ─────────────────────────────────────

    def set_active_pacing_run(self, run_id: int | None) -> None:
        """Set the pacing-run id whose decisions are represented by timeline clips.
        Must be called after every pacing run for feedback shortcuts to work.
        None disables the shortcuts."""
        self._active_pacing_run_id = run_id

    def set_feedback_service(self, service: "FeedbackService") -> None:  # type: ignore[name-defined]
        """Inject a custom FeedbackService (for tests). Not used in production."""
        self._feedback_service = service

    def set_brain_v3_feedback_service(self, service, context=None) -> None:
        """Inject Brain-V3 feedback service and propagate to loaded clips."""
        self._brain_v3_feedback_service = service
        self._brain_v3_feedback_context = context
        for item in self.clip_items:
            item.set_brain_v3_feedback(service=service, context=context)

    # SCHNITT-Redesign Phase 05 Task 5.3
    def get_video_clip_items(self) -> list["TimelineClipItem"]:
        """Liefert alle Video-TimelineClipItems der aktuellen Szene."""
        return [it for it in self._scene.items()
                if isinstance(it, TimelineClipItem) and it.track_type == "video"]

    # ── B-200: In/Out-Point-Tracking ───────────────────────────────────────

    def _format_seconds(self, sec: float) -> str:
        """Helper für I/O-Point-Logging — mm:ss.fff."""
        try:
            t = float(sec)
        except (TypeError, ValueError):
            return f"{sec}"
        m = int(t) // 60
        s = t - 60 * m
        return f"{m:02d}:{s:06.3f}"

    def _on_set_in_point_local(self, time_sec: float) -> None:
        """B-200: lokaler Slot für In-Point-Taste (I).

        Speichert die Position als ``_in_point`` und gibt User-Feedback
        via ``console_log`` (falls verfügbar). Solange kein echter Trim-
        Worker existiert, ist das die minimal sichtbare Reaktion auf
        einen Tastendruck — vorher war die Taste komplett funktionslos.
        """
        try:
            self._in_point = float(time_sec)
        except (TypeError, ValueError):
            return
        cb = getattr(self, "console_log", None)
        if callable(cb):
            cb(f"[Timeline] In-Point gesetzt @ {self._format_seconds(self._in_point)}")

    def _on_set_out_point_local(self, time_sec: float) -> None:
        """B-200: lokaler Slot für Out-Point-Taste (O)."""
        try:
            self._out_point = float(time_sec)
        except (TypeError, ValueError):
            return
        cb = getattr(self, "console_log", None)
        if callable(cb):
            cb(f"[Timeline] Out-Point gesetzt @ {self._format_seconds(self._out_point)}")

    @property
    def in_point(self) -> float | None:
        """B-200: aktuell gesetzter In-Point (oder None)."""
        return self._in_point

    @property
    def out_point(self) -> float | None:
        """B-200: aktuell gesetzter Out-Point (oder None)."""
        return self._out_point

    def _notify_memory_updater(self) -> None:
        """B-197 F-3: Triggert die Pattern-Aggregation nach einem
        erfolgreichen Feedback-Write.

        ``MemoryUpdaterWorker.notify_feedback`` ist im Default-Pfad O(1)
        (nur ein Counter-Increment unter Lock). Erst wenn der Counter den
        ``BATCH_SIZE``-Schwellwert erreicht, ruft der Worker intern
        ``run()`` auf — der ist dann teurer (Pattern-SQL-JOIN), warnt
        aber selber sobald er auf dem GUI-Thread laeuft.

        Defensive: best-effort. Wenn das Singleton nicht bereitsteht (z.B.
        DB nicht initialisiert), wird der Aufruf still uebersprungen.
        """
        try:
            from workers.memory_updater import get_memory_updater

            get_memory_updater().notify_feedback()
        except Exception as exc:  # broad: feedback-loop darf UI nicht killen
            logger.debug("B-197 F-3: notify_feedback skipped: %s", exc)

    # ── P12: Story-Map context-menu trigger ────────────────────────────────
    def set_brain_service(self, service) -> None:  # type: ignore[name-defined]
        """Inject a custom ``BrainService`` instance for the Story-Map menu.

        Default is a lazily-constructed module-level singleton (built on
        first ``contextMenuEvent`` so headless test contexts that never
        right-click never pay the import cost). Tests should call this with
        a fresh BrainService bound to their on-disk SQLite DB.
        """
        self._brain_service = service

    def _get_brain_service(self):
        """Return the BrainService for the Story-Map menu, lazily creating
        a default if none was injected. Headless / test setups that don't
        touch the real DB should call ``set_brain_service`` first."""
        existing = getattr(self, "_brain_service", None)
        if existing is not None:
            return existing
        from services.brain_service import BrainService
        self._brain_service = BrainService(session_factory=nullpool_session)
        return self._brain_service

    def contextMenuEvent(self, event):  # type: ignore[override]
        """Right-click context menu — currently a single ``Open Story Map``
        entry that opens the StoryMapDialog for the most-recent run with
        decisions, falling back to a QMessageBox if no such run exists.

        We deliberately keep this minimal: the timeline's interactive
        right-click flows live on the clip items (TimelineClipItem) which
        receive their own contextMenuEvent first; this handler only fires
        on right-clicks over empty timeline space.
        """
        item = self._timeline_clip_item_at(event.pos())
        if item is not None:
            scene_pos = self.mapToScene(event.pos())
            local_x = float(item.mapFromScene(scene_pos).x())
            item.show_context_menu_at(event.globalPos(), local_x)
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1A1A1A; color: #E0E0E0; border: 1px solid #333; }"
            "QMenu::item:selected { background: rgba(212,175,55,0.15); color: #E8CC6A; }"
        )
        story_map_action = menu.addAction("Open Story Map for most recent run")
        story_map_action.triggered.connect(self._open_story_map_for_recent_run)
        menu.exec(event.globalPos())

    def _timeline_clip_item_at(self, view_pos) -> TimelineClipItem | None:
        item = self.itemAt(view_pos)
        while item is not None:
            if isinstance(item, TimelineClipItem):
                return item
            parent = item.parentItem()
            if parent is item:
                break
            item = parent
        return None

    def _open_story_map_for_recent_run(self) -> None:
        """Resolve the newest run with decisions and open the Story-Map dialog."""
        from PySide6.QtWidgets import QMessageBox

        svc = self._get_brain_service()
        try:
            runs = svc.list_runs_with_story_map_data()
        except Exception as exc:
            logger.warning(
                "InteractiveTimeline: list_runs_with_story_map_data failed: %s",
                exc,
            )
            runs = []
        if not runs:
            QMessageBox.information(
                self,
                "Story Map",
                "No runs yet — run the pacing agent first.",
            )
            return
        run_id = int(runs[0]["id"])
        from ui.story_map_dialog import StoryMapDialog

        dialog = StoryMapDialog(svc, run_id, parent=self)
        # Hold a reference so the non-modal dialog is not GC'd.
        if not hasattr(self, "_story_map_dialogs"):
            self._story_map_dialogs = []
        self._story_map_dialogs.append(dialog)
        dialog.finished.connect(
            lambda _result, d=dialog: self._drop_story_map_dialog(d)
        )
        dialog.show()

    def _drop_story_map_dialog(self, dialog) -> None:
        try:
            self._story_map_dialogs.remove(dialog)
        except (AttributeError, ValueError):
            pass

    def _resolve_scene_id(self, clip_item: "TimelineClipItem") -> int | None:
        """Best-effort scene-id lookup for feedback routing.

        TimelineClipItem.entry_id → TimelineEntry row.
        TimelineEntry.media_id is the VideoClip.id for video-track entries.
        We look up the most-recent mem_decision for (active_run_id, scene of
        that video_clip_id) using the DB's own indexes.

        Scene.video_clip_id is the FK column on the scenes table linking a
        scene back to its source VideoClip (confirmed from database/models.py).
        """
        entry_id = getattr(clip_item, "entry_id", None)
        if entry_id is None:
            return None
        try:
            with nullpool_session() as session:
                entry = session.get(TimelineEntry, entry_id)
                if entry is None:
                    return None
                # Find the most-recent mem_decision for this run whose scene
                # belongs to the entry's video_clip_id (= entry.media_id for
                # video-track entries). Uses idx_mem_decision_run + idx_scene_video.
                row = session.execute(
                    text("""
                        SELECT d.scene_id
                        FROM mem_decision d
                        JOIN scenes s ON d.scene_id = s.id
                        WHERE d.run_id = :rid AND s.video_clip_id = :vcid
                        ORDER BY d.sequence_idx DESC
                        LIMIT 1
                    """),
                    {"rid": self._active_pacing_run_id, "vcid": entry.media_id},
                ).fetchone()
                return int(row[0]) if row is not None else None
        except Exception as e:
            logger.debug("_resolve_scene_id failed for entry=%s: %s", entry_id, e)
            return None

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

    def reset_zoom(self):
        """Reset timeline zoom to 100 percent."""
        old_zoom = self._current_zoom
        self.resetTransform()
        self._current_zoom = 1.0
        old_lod = 4 if old_zoom < 0.5 else (2 if old_zoom < 1.5 else 1)
        if old_lod != 2:
            self._update_beat_grid_lod()

    def fit_to_content(self):
        """Fit horizontally while preserving lane height.

        Full ``fitInView(...KeepAspectRatio)`` scales Y as well as X. On wide
        timelines that makes A1/V1 lanes almost disappear, matching B-471 live
        feedback. Timeline fit is a time-axis operation, so keep Y at 1.0.
        """
        rect = self._scene.sceneRect()
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            rect = self._scene.itemsBoundingRect()
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            return
        viewport_w = max(1.0, float(self.viewport().width() - 8))
        x_scale = viewport_w / max(1.0, float(rect.width()))
        x_scale = max(0.01, min(200.0, x_scale))
        self.resetTransform()
        self.scale(x_scale, 1.0)
        self._current_zoom = self.transform().m11()
        self._update_beat_grid_lod()
        self.centerOn(rect.center().x(), AUDIO_TRACK_Y + TRACK_HEIGHT + 5)
        self._schedule_thumb_request()

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
                new_video_start = max(0.0, audio_anchor_abs - video_anchor_offset)
                new_x = new_video_start * PIXELS_PER_SECOND
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

        # Duration aus MIME-Payload verwenden (falls vorhanden),
        # sonst Fallback auf DB-Query. Das MIME-Payload wird beim
        # Drag-Start befuellt und vermeidet den DB-Hit beim Drop.
        duration = payload.get("duration")
        if duration is not None:
            duration = float(duration)
        else:
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
