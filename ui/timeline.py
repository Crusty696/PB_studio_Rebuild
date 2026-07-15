"""Interactive Timeline with draggable clips, anchors, beat markers and zoom."""

import bisect
import json
import logging
import time
from collections import namedtuple
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from services.feedback_service import FeedbackService

from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsRectItem,
    QGraphicsTextItem, QGraphicsLineItem, QGraphicsPolygonItem, QGraphicsPixmapItem, QMenu,
    QGraphicsItem, QStyleOptionGraphicsItem,
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import (
    QPainter, QColor, QFont, QBrush, QPen, QPolygonF, QUndoStack, QPixmap,
)

from sqlalchemy import text, select
from sqlalchemy.orm import Session as DBSession, joinedload, lazyload

from database import engine, AudioTrack, VideoClip, TimelineEntry, Beatgrid, ClipAnchor, StructureSegment, AudioVideoAnchor, WaveformData, nullpool_session

logger = logging.getLogger(__name__)

# B-643: Thumbnails laufen jetzt ueber einen GETEILTEN QThreadPool
# (_TimelineThumbRunnable, siehe unten) statt ueber einen eigenen QThread je
# Thumbnail. Diese Registry wird dadurch nicht mehr befuellt.
#
# Historie B-605 (warum es sie gab): Der einzige GC-Schutz (self._thumb_threads)
# und der einzige Cleanup-Pfad (_on_thumb_worker_done) hingen am Timeline-
# WIDGET. Wurde die Timeline beim Workspace-/Projekt-Wechsel zerstoert waehrend
# ffmpeg-Thumb-Threads liefen, sammelte Python-GC die QThread-Wrapper ein ->
# C++-QThread wurde geloescht WAEHREND der Thread lief -> beim run()-Ende
# feuerte QThread::finished auf freigegebenen Speicher -> nativer Crash
# (CrashDump 2026-07-08 05:45: NULL_CLASS_PTR_WRITE Qt6Core
# QThread::start->finished->qt_static_metacall, kein Python-Frame im
# Crash-Thread).
#
# Der Pool loest genau diese Klasse strukturell: QThreadPool besitzt die
# Threads C++-seitig und ``setAutoDelete(True)`` laesst ihn das Runnable nach
# run() abraeumen — es existiert kein Python-Wrapper mehr, dessen GC einen
# laufenden Thread zerstoeren koennte. Registry und Freigabe bleiben als
# ungenutzte Huelle erhalten (Rueckwaerts-Kompatibilitaet + B-605-Regressions-
# pruefung); sie kosten nichts.
_ACTIVE_THUMB_THREADS: list = []


def _release_thumb_pair(pair) -> None:
    """B-605-Registry-Freigabe. Seit B-643 ungenutzt — der Pool raeumt selbst ab."""
    try:
        _ACTIVE_THUMB_THREADS.remove(pair)
    except ValueError:
        pass

# Timeline-Perf-Diagnose: [PERF]-Timing-Logs nur bei gesetztem Env-Flag
# PB_TIMELINE_PERF=1 (fuer die Timeline-Virtualisierungs-Untersuchung).
# Default AUS -> kein Diagnose-Rauschen im Normalbetrieb. Die Timing-
# Akkumulation selbst ist vernachlaessigbar guenstig und bleibt.
import os as _os
_TIMELINE_PERF = _os.getenv("PB_TIMELINE_PERF", "") == "1"
from services.pacing_service import CutPoint
from ui.shortcut_manager import get_shortcut_manager
from ui.waveform_item import WaveformGraphicsItem
from ui.widgets.lock_icon_item import LockIconItem

# MIME type for internal clip drag & drop (must match media_workspace.py)
CLIP_MIME_TYPE = "application/x-pb-studio-clip"

_EntryStub = namedtuple("_EntryStub", ["start_time"])

from PySide6.QtCore import QThread, QObject

class WaveformLoadWorker(QObject):
    # H-2: Nur Primitive ueber die Thread-Grenze emittieren. Vorher wurde das
    # SQLAlchemy-ORM-Objekt ``track`` emittiert — beim (queued) Slot-Aufruf war
    # die nullpool_session bereits geschlossen -> DetachedInstanceError-Klasse,
    # sobald ein Slot Attribute liest.
    finished = Signal(bool, list, list, list, list)  # (ok, band_low, band_mid, band_high, beat_positions)

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
                    
                    self.finished.emit(True, band_low, band_mid, band_high, beat_positions)
                    return
        except Exception as e:
            logger.error("Async Waveform Load Error: %s", e)
        self.finished.emit(False, [], [], [], [])

# ======================================================================
# Constants
# ======================================================================

PIXELS_PER_SECOND = 25
# Fixplan 2026-07-07 Schritt 8: 80 -> 110 px -> Maengelbehebung 140 px.
# Track-Hoehen und Zoom wirken zusammen. Alle Track-Geometrien leiten
# sich aus dieser Konstante ab (VIDEO_TRACK_Y, Thumb-Hoehe, Handles).
TRACK_HEIGHT = 140
MIN_READABLE_FIT_SCALE = 0.25
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


# ======================================================================
# B-077: Optimistic-UI — Anchor DB-Writes off GUI-Thread
# ======================================================================
# Marker/QGraphicsItem-Erstellung + jeder Marker-/Map-Zugriff bleiben auf
# dem GUI-Thread. Der Pool macht AUSSCHLIESSLICH den ClipAnchor
# INSERT/DELETE (nullpool_session). Ueber die Thread-Grenze gehen nur
# primitive Werte (temp_id/entry_id/time_offset bzw. temp_id/real_id) —
# NIE ein QGraphicsItem oder DB-Objekt. Muster gespiegelt von
# ui/widgets/media_grid.py (_ThumbSignals/_ThumbRunnable + QThreadPool).
from PySide6.QtCore import QThreadPool, QRunnable, Slot  # B-077

# ======================================================================
# B-643: Thumbnail-Extraktion gepoolt statt QThread-je-Thumbnail
# ======================================================================
# Vorher baute _start_thumb_worker fuer JEDES Thumbnail einen eigenen nativen
# QThread (QThread() + moveToThread + start + quit + 2x deleteLater +
# Registry-Eintrag). Weil _extract_thumb_qimage einen Disk-Cache hat, sind die
# Jobs bei Cache-Treffern nach einem Datei-Read fertig — der Loader startete
# dadurch ~30 Threads pro Sekunde. Dieser Thread-Churn (plus je ein
# Scene-Repaint) ist der Hauptverdacht fuer den AppHang aus B-643: der GIL
# hing in nativem Qt-Code, sogar der Watchdog-Thread verstummte.
#
# B-508 hat MediaPoolGrid genau deshalb schon auf einen QThreadPool
# umgestellt; die Timeline blieb am Legacy-Pfad haengen. Das wird hier
# nachgezogen — derselbe Pool wird geteilt, damit app-weit hoechstens
# _THUMB_POOL_MAX_THREADS ffmpeg-Laeufe gleichzeitig laufen.
#
# Der Concurrency-Deckel der Timeline bleibt zusaetzlich der
# ThumbnailLoadManager (max_concurrent=2) — der Pool ersetzt nur die
# Thread-Erzeugung, nicht die Ablaufsteuerung/Dedup.


class _TimelineThumbSignals(QObject):
    """Signal-Holder fuer _TimelineThumbRunnable (QRunnable ist kein QObject).

    Lebt am View (nicht am Runnable!) und ueberlebt damit den einzelnen Job.
    Das ist hier zwingend: haenge der Holder am Runnable, koennte er nach
    ``run()`` per autoDelete/GC verschwinden, BEVOR das QueuedConnection-Event
    zugestellt ist — Qt verwirft pending Events eines zerstoerten Senders.
    ``done`` bliebe aus, der ThumbnailLoadManager haette den Pfad fuer immer in
    ``_inflight`` und wuerde nie wieder ein Thumbnail starten.
    (media_grid haelt den Holder im Runnable — dort haengt kein Cap daran.)
    """

    done = Signal(str, object)  # (file_path, QImage)


class _TimelineThumbRunnable(QRunnable):
    """B-643: gepoolter Thumbnail-Job fuer die Timeline.

    Nutzt dieselbe ffmpeg-/Cache-Logik wie der Legacy-Worker
    (``_extract_thumb_qimage``, B-508 als Modulfunktion herausgezogen).
    """

    def __init__(self, signals: "_TimelineThumbSignals", file_path: str,
                 w: int, h: int) -> None:
        super().__init__()
        self.setAutoDelete(True)  # Pool raeumt das C++-Objekt nach run() ab
        self._signals = signals
        self._path = file_path
        self._w = w
        self._h = h

    def run(self) -> None:  # pool thread
        # done MUSS immer feuern — der ThumbnailLoadManager gibt den
        # inflight-Slot erst in on_done() frei. Ohne emit blieben Cap-Plaetze
        # dauerhaft belegt und die Timeline zeigte nie wieder Thumbnails.
        # Gleiche Garantie wie im Legacy-_ThumbWorker (media_grid.py).
        from PySide6.QtGui import QImage
        from ui.widgets.media_grid import _extract_thumb_qimage
        try:
            img = _extract_thumb_qimage(self._path, self._w, self._h)
        except Exception:  # noqa: BLE001 — Thumbnail darf nie den Pool-Thread killen
            logger.debug("[T1] thumb runnable failed: %s", self._path, exc_info=True)
            img = QImage()
        try:
            self._signals.done.emit(self._path, img)
        except RuntimeError:
            # Holder bereits zerstoert -> die Timeline (und ihr Loader) sind
            # ebenfalls weg. Kein Leak moeglich, still beenden.
            pass


_ANCHOR_DB_POOL: "QThreadPool | None" = None  # B-077


def _get_anchor_db_pool() -> QThreadPool:
    """B-077: modulweiter, auf 1 Thread begrenzter Pool fuer Anchor-DB-Writes.

    maxThreadCount=1 serialisiert INSERT/DELETE in Submit-Reihenfolge — ein
    add gefolgt von remove_all fuehrt so deterministisch zu INSERT-dann-DELETE.
    """
    global _ANCHOR_DB_POOL
    if _ANCHOR_DB_POOL is None:
        pool = QThreadPool()
        pool.setMaxThreadCount(1)
        _ANCHOR_DB_POOL = pool
    return _ANCHOR_DB_POOL


class _AnchorInsertSignals(QObject):
    """B-077: Signal-Holder (QRunnable ist kein QObject). Im GUI-Thread
    erzeugt -> emit aus dem Pool-Thread laeuft als QueuedConnection zurueck
    in den GUI-Thread des Empfaengers."""

    done = Signal(object, object)  # (temp_id, real_id|None)


class _AnchorInsertRunnable(QRunnable):
    """B-077: gepoolter ClipAnchor-INSERT.

    Reicht NUR primitive Werte ueber die Thread-Grenze (temp_id, entry_id,
    time_offset) und liefert die echte DB-id via Signal zurueck. Kein
    QGraphicsItem, kein DB-Objekt cross-thread.
    """

    def __init__(self, temp_id: int, entry_id: int, time_offset: float) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._temp_id = temp_id
        self._entry_id = entry_id
        self._time_offset = time_offset
        self.signals = _AnchorInsertSignals()

    @Slot()
    def run(self) -> None:  # pool thread
        real_id = None
        try:
            with nullpool_session() as session:
                anchor = ClipAnchor(
                    timeline_entry_id=self._entry_id,
                    time_offset=round(self._time_offset, 4),
                )
                session.add(anchor)
                session.commit()
                real_id = anchor.id
        except Exception:  # noqa: BLE001 — DB-Write darf den Pool-Thread nie killen
            logger.error(
                "B-077: Anchor-INSERT fehlgeschlagen (entry=%s)",
                self._entry_id, exc_info=True,
            )
        self.signals.done.emit(self._temp_id, real_id)


class _AnchorInsertReceiver(QObject):
    """B-077: GUI-Thread-affiner Empfaenger fuer das Insert-Fertig-Signal.

    Wird im GUI-Thread erzeugt (Auto/Queued-Connection -> Slot laeuft im
    GUI-Thread). Haelt Referenzen auf Marker + _anchor_map-Namespace (beide
    GUI-Thread-Objekte); der Pool-Thread beruehrt sie nie. Traegt die echte
    DB-id nach (Temp-ID -> real_id) und raeumt sich danach ab.
    """

    def __init__(self, marker, ns, parent=None) -> None:
        super().__init__(parent)
        self._marker = marker
        self._ns = ns

    @Slot(object, object)
    def _apply(self, temp_id, real_id) -> None:  # GUI thread
        try:
            if real_id is not None:
                if getattr(self._marker, "anchor_id", None) == temp_id:
                    self._marker.anchor_id = real_id
                if self._ns is not None and getattr(self._ns, "id", None) == temp_id:
                    self._ns.id = real_id
        except RuntimeError:
            pass  # Marker/Clip bereits zerstoert (z.B. remove_all dazwischen)
        finally:
            self.deleteLater()


class _AnchorDeleteRunnable(QRunnable):
    """B-077: gepoolter ClipAnchor-DELETE by timeline_entry_id.

    Fire-and-forget — die UI wurde bereits synchron geleert. Loescht per
    entry_id (NICHT per Anchor-id) -> keine Temp-ID erreicht je die DB.
    """

    def __init__(self, entry_id: int) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._entry_id = entry_id

    @Slot()
    def run(self) -> None:  # pool thread
        try:
            with nullpool_session() as session:
                session.query(ClipAnchor).filter_by(
                    timeline_entry_id=self._entry_id
                ).delete()
                session.commit()
        except Exception:  # noqa: BLE001 — DB-Write darf den Pool-Thread nie killen
            logger.error(
                "B-077: Anchor-DELETE fehlgeschlagen (entry=%s)",
                self._entry_id, exc_info=True,
            )


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


class CutLinesItem(QGraphicsItem):
    """M1.3 Timeline-Virtualisierung (D-066): ALLE Cut-Marker als EIN Item.

    Ersetzt 1400+ einzelne QGraphicsLineItems (set_cut_points) durch ein
    Item mit exposedRect-Culling + bisect — LOD-Ansatz aus BeatGridItem.
    Qt zeichnet nur den sichtbaren Ausschnitt; Show/Polish der Scene muss
    nicht mehr pro Cut-Linie arbeiten.
    """

    COLOR_MAP = {
        "beat": QColor(100, 200, 100, 180),
        "scene": QColor(255, 200, 60, 180),
        "energy": QColor(200, 100, 200, 180),
        "drum": QColor(255, 80, 80, 220),
        "anchor": QColor(255, 0, 255, 220),
        "transition": QColor(0, 200, 255, 220),   # Cyan fuer DJ-Uebergaenge
        "drop": QColor(255, 40, 40, 255),          # Rot fuer Drops
    }
    DEFAULT_COLOR = QColor(180, 180, 180)
    MAX_LINE_H = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        # (time, source, strength), nach time sortiert; _times parallel
        # fuer bisect-Culling im paint.
        self._cuts: list[tuple[float, str, float]] = []
        self._times: list[float] = []
        self.setZValue(5)

    def set_data(self, cuts) -> None:
        self._cuts = sorted(
            (float(cp.time), str(cp.source), float(cp.strength)) for cp in cuts
        )
        self._times = [c[0] for c in self._cuts]
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self) -> QRectF:
        if not self._times:
            return QRectF()
        w = self._times[-1] * PIXELS_PER_SECOND
        return QRectF(0, CUT_MARKERS_Y, w + 10, self.MAX_LINE_H + 2)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        clip_rect = option.exposedRect
        if clip_rect.isEmpty() or not self._cuts:
            return
        t_left = max(0.0, clip_rect.left()) / PIXELS_PER_SECOND
        t_right = clip_rect.right() / PIXELS_PER_SECOND
        idx_start = bisect.bisect_left(self._times, t_left)
        idx_end = bisect.bisect_right(self._times, t_right)
        pens: dict[str, QPen] = {}
        for i in range(idx_start, idx_end):
            t, source, strength = self._cuts[i]
            pen = pens.get(source)
            if pen is None:
                pen = QPen(self.COLOR_MAP.get(source, self.DEFAULT_COLOR), 1)
                pens[source] = pen
            x = t * PIXELS_PER_SECOND
            line_h = int(self.MAX_LINE_H * strength)
            painter.setPen(pen)
            painter.drawLine(x, CUT_MARKERS_Y, x, CUT_MARKERS_Y + line_h)


class BeatMarkersItem(QGraphicsItem):
    """M1.3 Timeline-Virtualisierung (D-066): goldene Beat-Marker als EIN
    Item (vorher ein QGraphicsLineItem pro Beat — bei DJ-Sets 12k+ Items).
    exposedRect-Culling + bisect wie BeatGridItem; Downbeat-Logik
    (jeder 4.) bleibt ueber den absoluten Listen-Index erhalten.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._beat_times: list[float] = []
        self.setZValue(3)

    def set_data(self, beat_times: list[float]) -> None:
        self._beat_times = sorted(float(t) for t in beat_times)
        self.prepareGeometryChange()
        self.update()

    def _marker_bottom(self) -> float:
        return AUDIO_TRACK_Y + TRACK_HEIGHT * 2 + 20

    def boundingRect(self) -> QRectF:
        if not self._beat_times:
            return QRectF()
        w = self._beat_times[-1] * PIXELS_PER_SECOND
        return QRectF(0, AUDIO_TRACK_Y, w + 10,
                      self._marker_bottom() - AUDIO_TRACK_Y)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        clip_rect = option.exposedRect
        if clip_rect.isEmpty() or not self._beat_times:
            return
        gold_pen = QPen(QColor(212, 175, 55, 160), 1)
        downbeat_pen = QPen(QColor(212, 175, 55, 220), 1)
        bottom = self._marker_bottom()
        t_left = max(0.0, clip_rect.left()) / PIXELS_PER_SECOND
        t_right = clip_rect.right() / PIXELS_PER_SECOND
        idx_start = bisect.bisect_left(self._beat_times, t_left)
        idx_end = bisect.bisect_right(self._beat_times, t_right)
        for i in range(idx_start, idx_end):
            x = self._beat_times[i] * PIXELS_PER_SECOND
            painter.setPen(downbeat_pen if (i % 4 == 0) else gold_pen)
            painter.drawLine(x, AUDIO_TRACK_Y, x, bottom)


class DialogAnchorMarkersItem(QGraphicsItem):
    """B-619 Folge: persistierte Dialog-Anker (``AudioVideoAnchor`` mit
    ``anchor_type="dialog"``) als vertikale Marker auf der Audio-Zeitachse.

    Getrennter, rein additiver Layer neben ``BeatMarkersItem`` (Gold) und den
    ClipAnchor-M-Markern. Deutlich unterscheidbare Farbe (Cyan/Tuerkis) statt
    Gold, damit der User Dialog-Anker von Beats trennen kann. Zeichenlogik +
    Zeit->x-Umrechnung sind identisch zu ``BeatMarkersItem`` (x = t *
    PIXELS_PER_SECOND), damit Marker exakt auf derselben Achse liegen.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dialog_times: list[float] = []
        # ueber Beats (zValue 3), damit Dialog-Anker sichtbar bleiben
        self.setZValue(4)

    def set_data(self, dialog_times: list[float]) -> None:
        # B-619: prepareGeometryChange() MUSS vor der boundingRect-Aenderung
        # (== _dialog_times setzen) laufen. Sonst cached die QGraphicsScene den
        # alten (bei __init__ leeren) Index und ruft paint() fuer dieses Item
        # nie auf — genau der Grund, warum die Marker unsichtbar blieben.
        self.prepareGeometryChange()
        self._dialog_times = sorted(float(t) for t in dialog_times)
        self.update()

    def _marker_bottom(self) -> float:
        return AUDIO_TRACK_Y + TRACK_HEIGHT * 2 + 20

    def boundingRect(self) -> QRectF:
        if not self._dialog_times:
            return QRectF()
        w = self._dialog_times[-1] * PIXELS_PER_SECOND
        return QRectF(0, AUDIO_TRACK_Y, w + 10,
                      self._marker_bottom() - AUDIO_TRACK_Y)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        clip_rect = option.exposedRect
        if clip_rect.isEmpty() or not self._dialog_times:
            return
        # Cyan/Tuerkis, klar verschieden vom Gold der Beat-Marker.
        dialog_pen = QPen(QColor(0, 200, 255, 210), 2)
        # B-619: cosmetic -> 2px bildschirm-konstant, zoom-unabhaengig sichtbar.
        # Ohne cosmetic wird die Linie bei starkem Zoom-out (langer Track im
        # Fit-View) auf Sub-Pixel skaliert und verschwindet.
        dialog_pen.setCosmetic(True)
        bottom = self._marker_bottom()
        t_left = max(0.0, clip_rect.left()) / PIXELS_PER_SECOND
        t_right = clip_rect.right() / PIXELS_PER_SECOND
        idx_start = bisect.bisect_left(self._dialog_times, t_left)
        idx_end = bisect.bisect_right(self._dialog_times, t_right)
        painter.setPen(dialog_pen)
        for i in range(idx_start, idx_end):
            x = self._dialog_times[i] * PIXELS_PER_SECOND
            painter.drawLine(x, AUDIO_TRACK_Y, x, bottom)


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
        self._label_item: QGraphicsTextItem | None = None
        self._missing_waveform_label: QGraphicsTextItem | None = None
        # PERF (Timeline-Hang 1352 Clips): QGraphicsTextItem-Erzeugung ist auf
        # Windows teuer (Font-Layout pro Item). ~4000 solcher Items (Label +
        # Status pro Clip) dominierten den Build (live ~29s CPU vs. 1.5s
        # headless ohne Rendering). Fix: Text-Items LAZY erst beim
        # Sichtbarwerden erzeugen (_ensure_content, getriggert vom Viewport-
        # Request). Rect + Placeholder-Pixmap (billig) bleiben sofort da ->
        # clip_items ist vollstaendig, Auswahl/Anker/Trim unveraendert.
        self._content_built = False
        self._content_title = title[:30]
        self._content_height = int(height)
        self._content_status_text: str | None = None
        self._content_missing_waveform = (track_type == "audio" and not has_waveform)
        if track_type == "video":
            pix = _timeline_video_placeholder(self._thumb_w, self._thumb_h, f"#{media_id}")
            self._thumbnail_item = QGraphicsPixmapItem(pix, self)
            self._thumbnail_item.setPos(0, 3)
            self._thumbnail_item.setOpacity(0.85)
            self._thumbnail_item.setZValue(3)
            self._content_status_text = (
                "Thumbnail laedt" if thumbnail_file_path else "Thumbnail fehlt - Datei fehlt"
            )

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

    def _ensure_content(self) -> None:
        """PERF: erzeugt die (auf Windows teuren) Text-Items lazy beim ersten
        Sichtbarwerden des Clips. Idempotent. Label ignoriert die
        View-Transform (B-471 T3: bleibt bei jedem Zoom lesbar)."""
        if self._content_built:
            return
        self._content_built = True
        _font = QFont("Segoe UI Variable Text", 9, QFont.Weight.Bold)
        _ign = QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
        if self._content_status_text is not None and self._thumbnail_item is not None:
            status = QGraphicsTextItem(self._content_status_text, self)
            status.setDefaultTextColor(QColor(245, 205, 105, 230))
            status.setFont(_font)
            status.setPos(10, max(24, self._content_height - 25))
            status.setZValue(5)
            status.setFlag(_ign, True)
            self._thumbnail_status_label = status
        label = QGraphicsTextItem(self._content_title, self)
        label.setDefaultTextColor(QColor(255, 255, 255))
        label.setFont(_font)
        label.setPos(6, 4)
        label.setZValue(6)
        label.setFlag(_ign, True)
        self._label_item = label
        if self._content_missing_waveform:
            missing = QGraphicsTextItem("Waveform fehlt - Audioanalyse starten", self)
            missing.setDefaultTextColor(QColor(220, 230, 245, 210))
            missing.setFont(_font)
            missing.setPos(10, max(22, self._content_height // 2 - 8))
            missing.setZValue(5)
            missing.setFlag(_ign, True)
            self._missing_waveform_label = missing

    def set_thumbnail_pixmap(self, pix) -> None:
        """B-471 T1: setzt das real generierte Thumbnail (vom async Loader)."""
        if self._thumbnail_item is None or pix is None:
            return
        # PERF: falls Content noch nicht lazy gebaut (Clip wurde direkt via
        # Cache befuellt), jetzt nachziehen — sonst fehlt der Status-Label-Ref.
        self._ensure_content()
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

    # B-077: klassenweiter, monoton fallender Temp-ID-Counter. Erzeugt
    # eindeutige, negative Platzhalter-IDs. Echte DB-IDs sind positiv ->
    # nie eine Kollision zwischen Temp- und echter ID.
    _anchor_temp_id_counter: int = 0

    def add_anchor_at(self, local_x: float) -> int | None:
        """Setzt einen neuen Anker an der lokalen X-Position (in Pixeln).

        B-077: Optimistic-UI. Die lokale UI (Marker, ``_anchor_markers``,
        ``_all_anchor_offsets``, ``timeline._anchor_map``) wird SYNCHRON im
        GUI-Thread aktualisiert und sofort eine negative Temp-ID
        zurueckgegeben (``not None`` erfuellt den Truthiness-Check des
        Aufrufers). Der ClipAnchor-INSERT laeuft in einem Pool-Thread; die
        echte DB-id wird via QueuedConnection auf dem GUI-Thread nachgetragen
        (Temp-ID -> echte id in ``marker.anchor_id`` und im
        ``_anchor_map``-Namespace).
        """
        time_offset = local_x / PIXELS_PER_SECOND
        if time_offset < 0:
            time_offset = 0.0

        # B-077: (a) eindeutige negative Temp-ID erzeugen.
        TimelineClipItem._anchor_temp_id_counter -= 1
        temp_id = TimelineClipItem._anchor_temp_id_counter

        # B-077: (b) SYNCHRON lokale UI-/Map-Updates im GUI-Thread.
        marker = AnchorMarkerItem(local_x, self._clip_height, temp_id, parent=self)
        self._anchor_markers.append(marker)
        # B-211: _all_anchor_offsets parallel pflegen.
        self._all_anchor_offsets.append(float(time_offset))
        ns = None
        timeline = self._timeline_view()
        if timeline is not None:
            from types import SimpleNamespace
            ns = SimpleNamespace(id=temp_id, time_offset=float(time_offset))
            timeline._anchor_map.setdefault(self.entry_id, []).append(ns)

        # B-077: (c) DB-INSERT in Pool-Thread auslagern; (d) echte id via
        # QueuedConnection im GUI-Thread nachtragen. Der Empfaenger (GUI-
        # Thread-QObject) haelt die Marker/Namespace-Referenzen; der
        # Runnable bekommt nur primitive Werte.
        runnable = _AnchorInsertRunnable(temp_id, self.entry_id, float(time_offset))
        receiver = _AnchorInsertReceiver(marker, ns, parent=timeline)
        runnable.signals.done.connect(receiver._apply)
        _get_anchor_db_pool().start(runnable)

        # B-077: (e) Temp-ID sofort zurueckgeben.
        return temp_id

    def remove_all_anchors(self):
        """Entfernt alle Anker dieses Clips.

        B-077: Optimistic-UI. Marker + lokale Maps werden SYNCHRON im
        GUI-Thread entfernt; der ClipAnchor-DELETE (by ``timeline_entry_id``)
        laeuft fire-and-forget in einem Pool-Thread.
        """
        # B-077: (a) SYNCHRON lokale UI-/Map-Updates.
        for m in self._anchor_markers:
            m.remove_from_scene()
        self._anchor_markers.clear()
        # B-211: _all_anchor_offsets parallel leeren.
        self._all_anchor_offsets.clear()
        timeline = self._timeline_view()
        if timeline is not None:
            timeline._anchor_map[self.entry_id] = []

        # B-077: (b) DELETE by timeline_entry_id im Pool-Thread. Loescht per
        # entry_id, nicht per Anchor-id -> keine Temp-ID erreicht je die DB.
        _get_anchor_db_pool().start(_AnchorDeleteRunnable(self.entry_id))

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
            from services.brain.brain_v3_service import BrainV3Service

            self._brain_v3_feedback_service = BrainV3Service()
        return self._brain_v3_feedback_service

    def _submit_brain_v3_feedback(self, rating: str) -> int:
        from services.brain.schemas.brain_v3_schemas import FeedbackRequest

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
        if self._locked:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._left_handle.setVisible(False)
            self._right_handle.setVisible(False)
            super().hoverMoveEvent(event)
            return

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
            if not self._locked:
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
            self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, False)
        else:
            self.setPen(QPen(self._base_color.darker(120), 1))
            self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)

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
# M1 Timeline-Virtualisierung (D-066): leichter Clip-Datensatz
# ======================================================================

@dataclass
class ClipRecord:
    """Leichter Datensatz pro Timeline-Cut (D-066 M1).

    Haelt alles, um ein TimelineClipItem jederzeit identisch zu
    (re-)materialisieren. ``item`` ist None, solange der Clip ausserhalb
    von Viewport+Puffer liegt. Geometrie (x/width) und Zustand
    (locked/selected) werden beim Entmaterialisieren vom Item
    zurueckgespiegelt — Undo/Lock/Trim-Syncs schreiben record-first.
    """
    entry_id: int
    media_id: int
    track_type: str
    title: str
    x: float
    y: float
    width: float
    height: float
    has_waveform: bool = False
    thumbnail_file_path: str | None = None
    locked: bool = False
    selected: bool = False
    brain_cut_id: int | None = None
    brain_confidence: float | None = None
    item: "TimelineClipItem | None" = None

    def h_intersects(self, rect: QRectF) -> bool:
        """Horizontaler Overlap-Test (Tracks sind vertikal fix, View
        scrollt nur horizontal — Y bewusst ignoriert, damit kleine/
        offscreen Viewports keine falschen Negative liefern)."""
        return self.x < rect.right() and (self.x + self.width) > rect.left()


# ======================================================================
# Interactive Timeline (QGraphicsView) — Performance Optimized
# ======================================================================

class InteractiveTimeline(QGraphicsView):
    clip_moved = Signal(int, float)
    selection_changed = Signal(list)  # emits list of dicts with clip data
    # Timeline-Perf: grosse Batch-Groesse. Der Build laeuft mit deaktivierten
    # Viewport-Updates (setUpdatesEnabled(False)); JEDER Batch-Yield via
    # QTimer.singleShot gibt aber ans Event-Loop zurueck, wo die reale
    # QGraphicsView die wachsende Szene teil-verarbeitet. Bei 1353 Clips
    # verursachten 54 Yields (batch=25) ~33s Build (headless ohne Rendering:
    # 2.3s). Grosse Batches -> nahezu Single-Pass -> minimale Inter-Batch-
    # Event-Verarbeitung. Cancel-Check greift weiterhin pro Batch.
    _BUILD_BATCH_SIZE = 2000

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
    zoom_changed = Signal(float)          # B-616: echter View-Scale nach jedem Zoom-Pfad
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
        # M1 Timeline-Virtualisierung (D-066): clip_records haelt ALLE Cuts
        # als leichte Datensaetze; clip_items enthaelt nur die aktuell
        # materialisierten TimelineClipItems (Viewport + Puffer).
        self.clip_records: list[ClipRecord] = []
        self._records_by_entry: dict[int, ClipRecord] = {}
        # Puffer in Bildschirmbreiten: materialisieren bei <= 2, erst bei
        # > 3 wieder entmaterialisieren (Hysterese gegen Scroll-Flattern).
        self._virt_keep_screens = 2.0
        self._virt_drop_screens = 3.0
        # M2 Show-Entkopplung (D-066): grosse Materialisierungs-Mengen werden
        # in QTimer(0)-Batches NACH dem ersten Paint abgearbeitet, damit der
        # Workspace-Klick sofort reagiert und der Inhalt progressiv erscheint.
        # M4-Haertung 2026-07-10 (Profil Lauf 3: virt dt=17327ms): ZEITBUDGET
        # statt fixer Stueckzahl — unter GIL-/IO-Last (z.B. 5 parallele
        # Stem-Preview-Threads beim ersten SCHNITT-Klick) kostete EIN Item
        # ~115ms statt ~4ms; 150 Stueck am Block = 17s Main-Thread-Freeze.
        # Budget haelt jeden Block klein, egal wie langsam Einzel-Items sind.
        self._VIRT_MAT_BATCH = 150            # Obergrenze pro Tick
        self._VIRT_SYNC_BUDGET_MS = 40.0      # Zeitbudget pro Tick/Sync-Pass
        self._virt_mat_queue: list[ClipRecord] = []
        self._virt_drain_scheduled = False
        self.cut_lines: list[QGraphicsLineItem] = []
        self._cut_points_signature: tuple = ()
        self.waveform_items: list[WaveformGraphicsItem] = []
        self._beat_markers: list[QGraphicsLineItem] = []
        self._beat_times: list[float] = []
        self._beat_marker_signature: tuple = ()
        self._snap_to_beat = True
        self._ruler_items: list = []
        # B-529: entry_id -> {"new_start", "drag_start_x", "duration"}. Die
        # Drag-Start-Daten werden zur Move-Zeit festgehalten (Item-Cache noch
        # gueltig), nicht erst im Flush — mouseReleaseEvent loescht den
        # Item-Cache, bevor der 200ms-Debounce feuert.
        self._pending_moves: dict[int, dict] = {}
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
        # Pfade, deren gecachtes Thumbnail nach einem Rebuild bereits auf die
        # neuen Clip-Items angewendet wurde (verhindert Wiederholung je Poll).
        self._cache_applied_paths: set[str] = set()
        # B-643: EIN Signal-Holder fuer alle Thumbnail-Jobs, am View gehalten.
        # Muss VOR dem Loader stehen — der kann sofort Jobs starten.
        # Bewusst nicht pro Runnable (wie in media_grid): der Holder muss den
        # einzelnen Job ueberleben, sonst koennte das QueuedConnection-Event
        # mit dem Sender verworfen werden und der inflight-Slot des Loaders
        # bliebe fuer immer belegt (siehe _TimelineThumbSignals-Docstring).
        self._thumb_signals = _TimelineThumbSignals()
        # H-1/H-8: UI-erzeugender Slot explizit queued in den GUI-Thread.
        self._thumb_signals.done.connect(
            self._on_thumb_ready, Qt.ConnectionType.QueuedConnection)
        self._thumb_loader = ThumbnailLoadManager(self._start_thumb_worker, max_concurrent=2)
        # Fixplan 2026-07-07 Schritt 6: Pixmap-Cache pro Datei. Vorher galt
        # ein Pfad im Loader dauerhaft als "done", aber das Pixmap wurde nur
        # auf die ZUM FERTIGSTELLUNGSZEITPUNKT registrierten Items gesetzt —
        # nach jedem Timeline-Rebuild (Auto-Edit-Apply, Projekt-Reload)
        # blieben alle neuen Items fuer immer Platzhalter (Log-Beweis:
        # request_visible ... new_requests=0 nach Apply).
        self._thumb_pixmaps: dict[str, "QPixmap"] = {}
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
        # M1.3 (D-066): Cut-Marker + Beat-Marker als je EIN Single-Item mit
        # exposedRect-Culling. Die Legacy-Listen cut_lines/_beat_markers
        # bleiben (leer) fuer Teardown-Kompatibilitaet bestehen.
        self._cut_lines_item = CutLinesItem()
        self._scene.addItem(self._cut_lines_item)
        self._beat_markers_item = BeatMarkersItem()
        self._scene.addItem(self._beat_markers_item)
        # B-619 Folge: eigener Layer fuer persistierte Dialog-Anker
        # (AudioVideoAnchor, anchor_type="dialog"). Rein additiv, getrennt von
        # _beat_markers und _anchor_map. Legacy-Liste _dialog_anchor_markers
        # bleibt (leer) fuer Teardown-Symmetrie zu _beat_markers.
        self._dialog_anchor_markers: list = []
        self._dialog_anchor_times: list[float] = []
        self._dialog_anchor_markers_item = DialogAnchorMarkersItem()
        self._scene.addItem(self._dialog_anchor_markers_item)

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
        # NEUBAU-VOLLINTEGRATION T1.6: Feedback-Tastendruck (A/R/S/1-5) hat
        # jetzt eine sichtbare Bestaetigung — vorher feuerte
        # feedback_event_emitted ohne einen einzigen Subscriber.
        self.feedback_event_emitted.connect(self._on_feedback_confirmed)
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
                        logger.debug("[B-283] Stopping old db_thread (non-blocking)")
                        # H-1: KEIN blockierendes wait() im Main-Thread — das
                        # fror die UI beim Project-Switch bis zu 1,5 s ein.
                        # Der alte Worker ist oben bereits von
                        # _on_db_load_finished disconnected; die bestehende
                        # finished-Signal-Kette (worker.finished -> thread.quit,
                        # thread.finished -> deleteLater fuer Thread + Worker)
                        # raeumt asynchron auf, sobald run() zurueckkehrt.
                        self._db_thread.quit()
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
        teardown_started_at = time.perf_counter()
        teardown_counts = {
            "clips": len(self.clip_items),
            "waveforms": len(self.waveform_items),
            "cut_lines": len(self.cut_lines),
            "beat_markers": len(self._beat_markers),
        }
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
            # B-598/B-575-Fix: Items koennen C++-seitig bereits geloescht sein
            # (z.B. Auto-Edit-Finish -> undo redo -> load_from_db oder
            # re-entrantes "Timeline generieren", waehrend ein
            # WaveformGraphicsItem schon zerstoert wurde). removeItem() auf einem
            # toten Wrapper wirft "Internal C++ object already deleted". Guard via
            # shiboken6.isValid (+ RuntimeError-Netz), konsistent mit B-283 oben.
            import shiboken6

            def _safe_rm(_it):
                try:
                    if shiboken6.isValid(_it):
                        self._scene.removeItem(_it)
                except RuntimeError:
                    pass  # C++-Objekt bereits geloescht

            for item in self.clip_items:
                _safe_rm(item)
            self.clip_items.clear()
            # M1 (D-066): Record-Schicht mit abreissen. Die M2-Materialisierungs-
            # Queue MUSS mit — sie haelt eigene Record-Refs; ein spaeterer Drain
            # wuerde sonst Items des ALTEN Projekts in die neue Scene bauen.
            self.clip_records.clear()
            self._records_by_entry.clear()
            self._virt_mat_queue = []
            # B-471 T1: Thumbnail-Registry + Scheduler zuruecksetzen (Done-Set
            # bleibt erhalten -> bereits generierte Thumbs werden nicht neu erzeugt).
            self._thumb_items_by_path.clear()
            self._thumb_loader.reset()
            self._cache_applied_paths.clear()  # neuer Rebuild -> Cache erneut anwenden
            for wf in self.waveform_items:
                _safe_rm(wf)
            self.waveform_items.clear()
            # Clear old cut lines
            for line in self.cut_lines:
                _safe_rm(line)
            self.cut_lines.clear()
            self._cut_points_signature = ()
            # Clear old beat markers
            for marker in self._beat_markers:
                _safe_rm(marker)
            self._beat_markers.clear()
            self._beat_marker_signature = ()
            # M1.3 (D-066): Single-Item-Daten leeren (Cut-/Beat-Marker).
            self._cut_lines_item.set_data([])
            self._beat_markers_item.set_data([])
            # B-619 Folge: alte Dialog-Anker-Marker leeren (verhindert Doppeln
            # nach Reload). Rein additiv, spiegelt das Beat-Marker-Clear.
            for _dm in self._dialog_anchor_markers:
                _safe_rm(_dm)
            self._dialog_anchor_markers.clear()
            self._dialog_anchor_times = []
            self._dialog_anchor_markers_item.set_data([])
            # Clear sections + beat grid + drop markers (AUD-70)
            self._clear_sections()
            self._clear_beat_grid()
        finally:
            _vp.setUpdatesEnabled(True)
            logger.info(
                "B-598 timeline load_from_db teardown project_id=%s duration_ms=%.1f counts=%s",
                project_id,
                (time.perf_counter() - teardown_started_at) * 1000.0,
                teardown_counts,
            )

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
                        # E5: lazyload("*") verhindert den Selectin-Load ALLER
                        # ClipAnchors + joined Project pro Entry — die Anchors
                        # laedt die explizite ClipAnchor-Query unten ohnehin
                        # (Doppel-Load bei 1428 Entries), entry.project wird
                        # downstream nie gelesen (nur Column-Attribute).
                        entries = session.query(TimelineEntry).options(
                            lazyload("*"),
                        ).filter_by(project_id=self.pid).all()
                        
                        _audio_ids = [e.media_id for e in entries if e.track == "audio"]
                        _video_ids = [e.media_id for e in entries if e.track == "video"]
                        
                        _audio_map = (
                            {t.id: t for t in session.query(AudioTrack).options(
                                lazyload("*"),
                                joinedload(AudioTrack.waveform_data),
                                joinedload(AudioTrack.beatgrid),
                            ).filter(
                                AudioTrack.id.in_(_audio_ids), AudioTrack.deleted_at.is_(None)).all()}
                            if _audio_ids else {}
                        )
                        _video_map = (
                            {c.id: c for c in session.query(VideoClip).options(
                                lazyload("*"),
                            ).filter(
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
                        # B-472: Brain V3 metadata is optional for rendering.
                        # Importing pydantic/brain modules inside this QThread
                        # caused native access violations during timeline load.
                        _brain_meta = {}

                        self._safe_emit(entries, _audio_map, _video_map, _anchor_map, _brain_meta)
                except Exception as e:
                    logger.error("TimelineDBWorker Fehler: %s", e)
                    self._safe_emit([], {}, {}, {}, {})

            def _safe_emit(self, *args) -> None:
                # Nebenbefund B-workspace-switch-freeze-qt-render: beim App-
                # Shutdown kann das C++-Gegenstueck dieses Workers bereits
                # geloescht sein, waehrend run() noch im Worker-Thread
                # weiterlaeuft -> finished.emit() wirft "Internal C++ object
                # (TimelineDBWorker) already deleted". Guard via
                # shiboken6.isValid (+ RuntimeError-Netz), konsistent mit dem
                # B-283-Muster in _cancel_pending_db_load oben.
                import shiboken6
                try:
                    if shiboken6.isValid(self):
                        self.finished.emit(*args)
                except RuntimeError:
                    pass  # C++-Objekt bereits geloescht (App-Shutdown-Race)

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
        # PERF-DIAG (Timeline-Hang-Untersuchung, 1352 Clips): synchroner
        # Recover-Schritt (ggf. DB-Query im UI-Thread) separat messen.
        _rec_t0 = time.perf_counter()
        audio_map, video_map = self._recover_missing_media_maps(entries, audio_map, video_map)
        if _TIMELINE_PERF:
            logger.info(
                "[PERF] recover_missing_media_maps=%.0fms entries=%d",
                (time.perf_counter() - _rec_t0) * 1000.0, len(entries),
            )
        # B-619: Dialog-Anker-Marker werden am ENDE von _build_entry_batch
        # gerendert (Build fertig, Viewport-Updates wieder aktiv). Ein Aufruf
        # HIER — vor dem stummgeschalteten Batch-Build — verpuffte: das Repaint
        # wurde vom setUpdatesEnabled(False)-Zyklus verworfen und paint() nie
        # ausgeloest.
        self._batch_build_started_at = time.perf_counter()
        self._batch_build_cpu_ms = 0.0
        self._start_batched_entry_build(entries, audio_map, video_map, anchor_map)

    def _load_dialog_anchors(self, audio_track_ids=None) -> list[float]:
        """B-619/B-634: laedt die ``audio_time``-Werte (Sekunden) der
        persistierten Dialog-Anker (``AudioVideoAnchor`` mit
        ``anchor_type="dialog"``) des AKTIVEN PROJEKTS.

        B-634: projekt-basiert statt audio_map-abhaengig. Beim reinen
        Projekt-Oeffnen ist audio_map (die frueher uebergebenen
        ``audio_track_ids``) leer/unvollstaendig -> die alte track-id-gefilterte
        Query lieferte [] und es erschienen keine Marker. Es wird jetzt ueber
        ``AudioTrack.project_id == get_active_project_id()`` gejoint.
        ``audio_track_ids`` bleibt als Fallback, falls kein aktives Projekt
        ermittelbar ist. Rein lesend + additiv; strikt auf anchor_type="dialog"
        gefiltert, damit Beat-/M-Tasten-Anker anderer anchor_types unberuehrt
        bleiben.
        """
        try:
            from database import get_active_project_id
            project_id = get_active_project_id()
            with DBSession(engine) as session:
                if project_id is not None:
                    rows = session.query(AudioVideoAnchor.audio_time).join(
                        AudioTrack,
                        AudioVideoAnchor.audio_track_id == AudioTrack.id,
                    ).filter(
                        AudioTrack.project_id == project_id,
                        AudioVideoAnchor.anchor_type == "dialog",
                    ).all()
                else:
                    ids = [int(a) for a in (audio_track_ids or []) if a is not None]
                    if not ids:
                        return []
                    rows = session.query(AudioVideoAnchor.audio_time).filter(
                        AudioVideoAnchor.audio_track_id.in_(ids),
                        AudioVideoAnchor.anchor_type == "dialog",
                    ).all()
            return sorted(float(r[0]) for r in rows if r[0] is not None)
        except Exception as exc:
            logger.warning("[B-634] Dialog-Anker-Load fehlgeschlagen: %s", exc)
            return []

    def set_dialog_anchor_markers(self, audio_times) -> None:
        """B-619 Folge: setzt die Dialog-Anker-Marker (Cyan) auf der Audio-
        Zeitachse. audio_time (Sekunden) -> x via PIXELS_PER_SECOND, identisch
        zur Beat-Marker-Umrechnung. Rein additiv."""
        times = sorted(float(t) for t in (audio_times or []))
        self._dialog_anchor_times = times
        self._dialog_anchor_markers_item.set_data(times)

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
                        lazyload("*"),
                        joinedload(AudioTrack.waveform_data),
                        joinedload(AudioTrack.beatgrid),
                    ).filter(
                        AudioTrack.id.in_(missing_audio_ids),
                        AudioTrack.deleted_at.is_(None),
                    ).all():
                        audio_map[track.id] = track
                if missing_video_ids:
                    for clip in session.query(VideoClip).options(
                        lazyload("*"),
                    ).filter(
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

        # PERF-DIAG: CPU-Zeit pro Batch akkumulieren (zeigt, ob der Build
        # wirklich zwischen Batches ans Event-Loop zurueckgibt oder ein
        # einzelner Batch den 62s-Hang verursacht).
        _batch_t0 = time.perf_counter()
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
        self._batch_build_cpu_ms += (time.perf_counter() - _batch_t0) * 1000.0

        if end < len(entries):
            QTimer.singleShot(0, self._build_entry_batch)
            return

        self._pending_entry_build = None
        self._total_duration = state["max_end"]
        self._draw_track_backgrounds()
        self._update_scene_rect()
        vp = self.viewport()
        vp.setUpdatesEnabled(True)
        # B-619: jetzt (Build fertig, Updates aktiv) die persistierten Dialog-
        # Anker-Marker rendern — VOR dem folgenden vp.update(), damit das volle
        # Viewport-Repaint sie erfasst. audio_map-Keys = AudioTrack.id der
        # Timeline-Audio-Clips. Rein additiv, beruehrt Beat-/ClipAnchor nicht.
        try:
            _dlg_times = self._load_dialog_anchors(list(state["audio_map"].keys()))
            self.set_dialog_anchor_markers(_dlg_times)
        except Exception as _dlg_exc:
            logger.debug("[B-619] Dialog-Anker-Render fehlgeschlagen: %s", _dlg_exc)
        # B-634: die persistierte Dialog-Anker-LISTE (anchor_list-QTreeWidget im
        # Schnitt/Pacing-Panel) synchron zur Marker-Ladung aus der DB befuellen.
        # load_from_db ist der kanonische Projekt-Load-Refresh dieses Panels;
        # der Aufruf haengt sich additiv an, ohne bestehende Pfade zu aendern.
        # Guarded — darf den Build/Render nie brechen; im Headless-Test (Timeline
        # ohne PBWindow) ist window() self -> kein edit_workspace -> No-op.
        try:
            _win = self.window()
            _ew = getattr(_win, "edit_workspace", None) if _win is not None else None
            if _ew is not None and hasattr(_ew, "_populate_anchor_list_from_db"):
                _ew._populate_anchor_list_from_db()
        except Exception as _list_exc:
            logger.debug("[B-634] Dialog-Anker-Listen-Refresh fehlgeschlagen: %s", _list_exc)
        # B-617: Beat-Grid-Overlay + Song-Struktur-Sektionen (INTRO/DROP-Farbflaechen)
        # nach dem Load repopulieren. load_from_db-Teardown ruft _clear_sections/
        # _clear_beat_grid, fuellt aber nie neu -> die Overlays blieben leer trotz
        # DB-Daten. Hier (Build fertig, Viewport-Updates aktiv, nach dem Clear) den
        # bestehenden Repopulator wiederverwenden. audio_map-Keys = AudioTrack.id.
        # Bei mehreren Audio-Tracks das Overlay des ersten zeichnen (Single-Overlay-
        # Semantik von set_beat_grid/load_sections). Kein Audio -> ueberspringen.
        try:
            _audio_ids = list(state["audio_map"].keys())
            if _audio_ids:
                self.load_beat_grid_from_db(_audio_ids[0])
        except Exception as _grid_exc:
            logger.debug("[B-617] Beat-Grid/Section-Repopulate fehlgeschlagen: %s", _grid_exc)
        vp.update()
        try:
            self.fit_to_content()
        except Exception as fit_exc:
            logger.debug("Automatic fit_to_content failed: %s", fit_exc)
        self._schedule_thumb_request()  # B-471 T1: lazy thumbs fuer sichtbare Clips
        logger.info("[T1] build done: registered_paths=%d records=%d materialized=%d",
                    len(self._thumb_items_by_path), len(self.clip_records),
                    len(self.clip_items))
        # PERF-DIAG: Wall-Zeit (inkl. Event-Loop-Yields) vs. reine Build-CPU-Zeit.
        # Grosse Differenz = Build yieldet gut (kein Hang durch den Build);
        # Wall ~= CPU = ein Batch/der Build blockiert durchgehend.
        if _TIMELINE_PERF:
            _wall = (time.perf_counter() - getattr(self, "_batch_build_started_at",
                                                    time.perf_counter())) * 1000.0
            logger.info(
                "[PERF] batched build: wall=%.0fms cpu=%.0fms records=%d materialized=%d batch_size=%d",
                _wall, getattr(self, "_batch_build_cpu_ms", 0.0),
                len(self.clip_records), len(self.clip_items), self._BUILD_BATCH_SIZE,
            )

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

        # M1 Timeline-Virtualisierung (D-066): Build erzeugt nur noch einen
        # leichten ClipRecord. Das echte TimelineClipItem entsteht erst in
        # _materialize_record, wenn der Clip in Viewport+Puffer liegt
        # (_update_virtualization, getriggert vom Thumbnail-Polling-Anker).
        rec = ClipRecord(
            entry_id=entry.id,
            media_id=entry.media_id,
            track_type=entry.track,
            title=title,
            x=x, y=y,
            width=width, height=TRACK_HEIGHT,
            has_waveform=has_waveform,
            thumbnail_file_path=str(clip.file_path) if entry.track == "video" and clip else None,
            locked=bool(getattr(entry, "locked", False)),
        )
        if entry.track == "video":
            key = (int(entry.media_id), int(round(float(entry.start_time or 0.0) * 1000.0)))
            meta = self._brain_v3_timeline_meta.get(key)
            if meta is not None:
                rec.brain_cut_id = getattr(meta, "cut_id", None)
                rec.brain_confidence = getattr(meta, "confidence", None)
        self.clip_records.append(rec)
        self._records_by_entry[rec.entry_id] = rec

        if entry.track == "audio":
            # Audio-Clip (1-3 Stueck, spannt die ganze Timeline): IMMER sofort
            # materialisieren — permanent sichtbar, traegt die Waveform als
            # Child und wird nie entmaterialisiert.
            item = self._materialize_record(rec)
            if item is not None and has_waveform:
                # B-471 Follow-up: TimelineDBWorker hat waveform_data bereits
                # geladen. Direkt aus diesem Snapshot zeichnen, sonst endet der
                # Live-Build sichtbar mit waveform_items=0 und die Wellenform
                # taucht erst spaet oder gar nicht auf.
                # B-553: item (TimelineClipItem) als parent_clip uebergeben
                self._load_waveform_for_track(None, track, entry, dur, y, item)
        return entry.start_time + dur

    # ── M1 Timeline-Virtualisierung (D-066) ──────────────────────────────
    def _materialize_record(self, rec: ClipRecord) -> TimelineClipItem | None:
        """Erzeugt das echte TimelineClipItem fuer einen Record (idempotent).

        Wendet den Record-Zustand (Geometrie, Lock, Selection, Brain-Meta)
        auf das frische Item an; gecachte Thumbnails kommen sofort via
        _register_clip_thumbnail/_thumb_pixmaps.
        """
        if rec.item is not None:
            return rec.item
        item = TimelineClipItem(
            entry_id=rec.entry_id,
            media_id=rec.media_id,
            track_type=rec.track_type,
            title=rec.title,
            x=rec.x, y=rec.y,
            width=rec.width, height=rec.height,
            on_moved=self._on_clip_moved,
            on_trimmed=self._on_clip_trimmed,
            has_waveform=rec.has_waveform,
            anchors=self._anchor_map.get(rec.entry_id, []),
            thumbnail_file_path=rec.thumbnail_file_path,
        )
        item.set_brain_v3_feedback(
            service=self._brain_v3_feedback_service,
            context=self._brain_v3_feedback_context,
        )
        if rec.locked:
            item.set_locked(True)
        if rec.brain_cut_id is not None:
            item.set_brain_v3_cut_id(rec.brain_cut_id)
        if rec.brain_confidence is not None:
            item.set_brain_v3_confidence(rec.brain_confidence)
        self._scene.addItem(item)
        if rec.selected:
            item.setSelected(True)
        rec.item = item
        self.clip_items.append(item)
        self._register_clip_thumbnail(item)
        # PERF: Audio-Content sofort (immer sichtbar, nicht im viewport-lazy
        # Video-Thumbnail-Pfad); Video-Text bleibt lazy (_ensure_content via
        # _request_visible_thumbnails).
        if rec.track_type == "audio":
            item._ensure_content()
        return item

    def _dematerialize_record(self, rec: ClipRecord) -> None:
        """Entfernt das Item eines Records aus der Scene; Zustand wird in den
        Record zurueckgespiegelt, damit Re-Materialisierung identisch ist."""
        item = rec.item
        if item is None:
            return
        rec.item = None
        try:
            import shiboken6
            alive = shiboken6.isValid(item)
        except Exception:
            alive = True
        if alive:
            try:
                rec.x = item.pos().x()
                rec.width = item._clip_width
                rec.locked = item.is_locked()
                rec.selected = item.isSelected()
                self._scene.removeItem(item)
            except RuntimeError:
                pass
        if item in self.clip_items:
            self.clip_items.remove(item)
        fp = rec.thumbnail_file_path
        if fp:
            lst = self._thumb_items_by_path.get(str(fp))
            if lst and item in lst:
                lst.remove(item)

    def _update_virtualization(self, view_rect: QRectF | None = None) -> None:
        """Materialisiert Records im Fenster Viewport ± _virt_keep_screens,
        entmaterialisiert Video-Items ausserhalb ± _virt_drop_screens
        (Hysterese). Anker ist das bestehende 120ms-Polling
        (_request_visible_thumbnails: Scroll/Zoom/Show/Build)."""
        if not self.clip_records:
            return
        _t0 = time.perf_counter()
        if view_rect is None:
            try:
                view_rect = self.mapToScene(self.viewport().rect()).boundingRect()
            except RuntimeError:
                return
        span = max(200.0, view_rect.width())
        keep = QRectF(view_rect).adjusted(-self._virt_keep_screens * span, 0.0,
                                          self._virt_keep_screens * span, 0.0)
        drop = QRectF(view_rect).adjusted(-self._virt_drop_screens * span, 0.0,
                                          self._virt_drop_screens * span, 0.0)
        mat = demat = 0
        to_mat: list[ClipRecord] = []
        vp = self.viewport()
        vp.setUpdatesEnabled(False)
        try:
            for rec in self.clip_records:
                if rec.item is None:
                    if rec.h_intersects(keep):
                        # M2: kleine Mengen sofort (Scroll-Nachladen), grosse
                        # Mengen unten via QTimer(0)-Batches (Show-Entkopplung).
                        # M4: zusaetzlich Zeitbudget — unter Hintergrund-Last
                        # bricht der Sync-Pass frueh ab und der Rest laeuft
                        # progressiv in der Drain-Kette.
                        if (mat < self._VIRT_MAT_BATCH
                                and (time.perf_counter() - _t0) * 1000.0
                                < self._VIRT_SYNC_BUDGET_MS):
                            self._materialize_record(rec)
                            mat += 1
                        else:
                            to_mat.append(rec)
                    continue
                # Audio bleibt permanent materialisiert (Waveform-Parent).
                if rec.track_type != "video":
                    continue
                # Clips mit offenem Interaktions-Zustand nie entziehen:
                # Selection (Inspector/Hotkeys), laufender Drag/Trim,
                # ungeflushte Moves (200ms-Debounce, B-529).
                if rec.entry_id in self._pending_moves:
                    continue
                item = rec.item
                try:
                    if (item.isSelected() or item._drag_start_x is not None
                            or getattr(item, "_trim_mode", None)):
                        continue
                    item_rect = item.sceneBoundingRect()
                except RuntimeError:
                    item_rect = QRectF(rec.x, rec.y, rec.width, rec.height)
                if not (item_rect.left() < drop.right()
                        and item_rect.right() > drop.left()):
                    self._dematerialize_record(rec)
                    demat += 1
        finally:
            vp.setUpdatesEnabled(True)
        # M2: Rest-Materialisierung progressiv nach dem naechsten Paint.
        self._virt_mat_queue = to_mat
        if to_mat and not self._virt_drain_scheduled:
            self._virt_drain_scheduled = True
            QTimer.singleShot(0, self._drain_virt_mat_queue)
        if _TIMELINE_PERF and (mat or demat or to_mat):
            logger.info(
                "[PERF] virt: mat=%d queued=%d demat=%d items=%d records=%d window=(%.0f..%.0f) dt=%.0fms",
                mat, len(to_mat), demat, len(self.clip_items), len(self.clip_records),
                keep.left(), keep.right(), (time.perf_counter() - _t0) * 1000.0,
            )

    def _drain_virt_mat_queue(self) -> None:
        """M2 Show-Entkopplung (D-066): arbeitet die Materialisierungs-Queue
        in QTimer(0)-Batches ab — zwischen den Batches kommt das Event-Loop
        (Paint/Input) dran, der Inhalt erscheint progressiv."""
        self._virt_drain_scheduled = False
        queue = self._virt_mat_queue
        if not queue:
            return
        _t0 = time.perf_counter()
        try:
            vp = self.viewport()
            vp.setUpdatesEnabled(False)
        except RuntimeError:
            return  # View bereits zerstoert
        done = 0
        try:
            # M4-Haertung: Zeitbudget pro Tick (statt fixe Stueckzahl) —
            # unter GIL-/IO-Last bleibt der Main-Thread-Block klein und
            # das Event-Loop (Paint/Input) kommt zwischen den Ticks dran.
            while (queue and done < self._VIRT_MAT_BATCH
                    and (time.perf_counter() - _t0) * 1000.0
                    < self._VIRT_SYNC_BUDGET_MS):
                rec = queue.pop(0)
                if rec.item is None:
                    self._materialize_record(rec)
                done += 1
        finally:
            vp.setUpdatesEnabled(True)
        if _TIMELINE_PERF:
            logger.info(
                "[PERF] virt drain: batch=%d rest=%d items=%d dt=%.0fms",
                done, len(queue), len(self.clip_items),
                (time.perf_counter() - _t0) * 1000.0,
            )
        if queue:
            self._virt_drain_scheduled = True
            QTimer.singleShot(0, self._drain_virt_mat_queue)
        else:
            # Fertig: Thumbnails/Content fuer die neuen Items anfordern.
            self._schedule_thumb_request()

    def materialize_all(self) -> None:
        """Materialisiert ALLE Records — fuer Tests und Nicht-Viewport-Pfade,
        die vollstaendige clip_items erwarten. Kein Produktions-Hot-Path."""
        for rec in self.clip_records:
            self._materialize_record(rec)

    def _find_clip_record(self, entry_id: int) -> "ClipRecord | None":
        return self._records_by_entry.get(int(entry_id))

    # ── B-471 T1: viewport-lazy thumbnail loading ─────────────────────────
    def _register_clip_thumbnail(self, item: "TimelineClipItem") -> None:
        """Merkt ein Video-Clip-Item fuer spaeteres lazy Thumbnail-Laden.

        Schritt 6: Liegt das Pixmap schon im Cache (Datei wurde in dieser
        Session bereits generiert), wird es SOFORT gesetzt — sonst bleiben
        Items nach einem Rebuild dauerhaft Platzhalter, weil der Loader den
        Pfad als done dedupliziert.
        """
        fp = getattr(item, "thumbnail_file_path", None)
        if item.track_type != "video" or not fp:
            return
        self._thumb_items_by_path.setdefault(str(fp), []).append(item)
        cached = self._thumb_pixmaps.get(str(fp))
        if cached is not None:
            item.set_thumbnail_pixmap(cached)

    def _schedule_thumb_request(self) -> None:
        """Coalesct Viewport-Aenderungen (Scroll/Zoom/Build) zu einem Request."""
        try:
            self._thumb_request_timer.start()
        except RuntimeError:
            pass

    def _request_visible_thumbnails(self) -> None:
        """Fordert Thumbnails fuer aktuell sichtbare Video-Clips an (lazy)."""
        # M2 Show-Entkopplung (D-066): eine VERSTECKTE Timeline baut nichts —
        # weder Items noch Thumbnails. Der Workspace-Klick zeigt dadurch eine
        # fast leere Scene (Track-BGs + Audio + Single-Items = billig);
        # showEvent triggert diesen Pfad erneut und fuellt progressiv.
        if not self.isVisible():
            return
        try:
            view_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        except RuntimeError:
            return
        # etwas Vorlauf, damit knapp ausserhalb liegende Clips vorgeladen werden
        view_rect.adjust(-300.0, 0.0, 300.0, 0.0)
        # M1 (D-066): Materialisierungs-Fenster VOR der Thumbnail-Logik
        # nachfuehren — neu materialisierte Items nehmen direkt am
        # _ensure_content-/Thumbnail-Pass unten teil.
        self._update_virtualization(view_rect)
        # PERF: Text-Content (Label/Status) fuer aktuell sichtbare Clips lazy
        # nachbauen (siehe TimelineClipItem._ensure_content). Idempotent +
        # billiger Intersects-Check; baut nur neu-sichtbare. Deckt auch
        # bereits-thumbnail-geladene Clips ab (die im Pfad-Loop uebersprungen
        # werden). Muss VOR dem _thumb_items_by_path-Early-Return laufen.
        for _it in self.clip_items:
            try:
                if not _it._content_built and _it.sceneBoundingRect().intersects(view_rect):
                    _it._ensure_content()
            except RuntimeError:
                continue
        if not self._thumb_items_by_path:
            logger.info("[T1] request_visible: keine registrierten Thumbnail-Pfade")
            return
        requested = 0
        for fp, items in list(self._thumb_items_by_path.items()):
            if self._thumb_loader.is_done(fp):
                # Pfad bereits geladen. Nach einem Timeline-Rebuild sind die
                # Clip-Items neu, haben aber noch kein Bild -> das gecachte
                # Thumbnail direkt anwenden statt zu skippen (sonst bleiben die
                # Clips dauerhaft auf "Thumbnail laedt"). Nur einmal je Pfad.
                if fp not in self._cache_applied_paths:
                    self._apply_cached_thumb(fp, items)
                    self._cache_applied_paths.add(fp)
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
        """Reiht einen Thumbnail-Job (ffmpeg) fuer eine Clip-Datei in den Pool ein.

        B-643: Frueher entstand hier pro Thumbnail ein eigener nativer QThread.
        Weil ``_extract_thumb_qimage`` einen Disk-Cache hat, sind die Jobs bei
        Cache-Treffern sofort fertig — der Loader erzeugte dadurch ~30 Threads
        pro Sekunde (live belegt). Dieser Thread-Churn ist der Hauptverdacht
        fuer den AppHang (GIL-Halt in nativem Qt-Code). Jetzt laeuft der Job
        ueber den geteilten Pool aus media_grid (B-508-Muster) — die Threads
        werden wiederverwendet statt erzeugt und zerstoert.

        Der frueher hier noetige B-605-Schutz (Registry + widget-unabhaengige
        Beendigungskette gegen GC-Zerstoerung eines laufenden QThread) entfaellt
        strukturell: der Pool besitzt die Threads C++-seitig, ``setAutoDelete``
        raeumt das Runnable ab.

        Aufrufer ist ausschliesslich der ThumbnailLoadManager (max_concurrent=2),
        der Dedup + Reihenfolge macht. Faellt der Start aus, muss ``on_done``
        gerufen werden, sonst bleibt der inflight-Slot belegt.
        """
        try:
            from ui.widgets.media_grid import _get_thumb_pool
            logger.info("[T1] thumb worker start: %s", file_path)
            thumb_h = max(16, TRACK_HEIGHT - 6)
            _get_thumb_pool().start(
                _TimelineThumbRunnable(self._thumb_signals, file_path, 220, thumb_h)
            )
        except Exception as exc:  # noqa: BLE001 — Thumbnail darf nie die UI killen
            logger.debug("Thumbnail-Job-Start fehlgeschlagen (%s): %s", file_path, exc)
            self._thumb_loader.on_done(file_path)
            self._thumb_loader.on_done(file_path)

    def _on_thumb_ready(self, file_path: str, qimage) -> None:
        """GUI-Thread-Slot: wandelt QImage->QPixmap und setzt es auf alle Items."""
        from PySide6.QtGui import QPixmap
        try:
            pix = QPixmap.fromImage(qimage)
        except (RuntimeError, TypeError):
            pix = None
        if pix is not None and not pix.isNull():
            # Schritt 6: cachen, damit nach Timeline-Rebuilds neue Items das
            # Thumbnail sofort aus dem Cache bekommen (siehe
            # _register_clip_thumbnail).
            self._thumb_pixmaps[str(file_path)] = pix
            for it in self._thumb_items_by_path.get(str(file_path), []):
                it.set_thumbnail_pixmap(pix)
        self._thumb_loader.on_done(str(file_path))

    def _apply_cached_thumb(self, file_path: str, items) -> None:
        """Wendet ein bereits auf Platte gecachtes Thumbnail direkt auf die
        Items an (kein erneuter ffmpeg-Lauf) — fuer ``is_done``-Pfade nach einem
        Timeline-Rebuild, deren neue Clip-Items sonst auf 'Thumbnail laedt' blieben.
        """
        from PySide6.QtGui import QPixmap, QImage
        from ui.widgets.media_grid import _thumb_path
        try:
            dest = _thumb_path(str(file_path))
            if not dest.exists():
                return  # kein Disk-Cache -> normaler async Load-Pfad kuemmert sich
            qimg = QImage(str(dest))  # nur Disk lesen, KEIN ffmpeg im GUI-Thread
            pix = QPixmap.fromImage(qimg)
        except (RuntimeError, TypeError, OSError):
            return
        if pix is not None and not pix.isNull():
            for it in items:
                try:
                    it.set_thumbnail_pixmap(pix)
                except RuntimeError:
                    continue

    def _style_visible_waveform(self, wf_item: WaveformGraphicsItem, parent_clip: TimelineClipItem | None = None) -> None:
        """Macht 3-Band-Waveform und Beatgrid sichtbar ueber der Clip-Flaeche."""
        try:
            wf_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent, False)
            base_z = parent_clip.zValue() if parent_clip is not None else 2.0
            wf_item.setZValue(base_z + 2.0)
            wf_item.setOpacity(0.96)
        except RuntimeError:
            pass

    def _load_waveform_async(self, media_id: int, start_time: float, duration: float, y: float, clip_item: TimelineClipItem):
        """Startet das asynchrone Laden der Wellenform im Hintergrund."""
        import shiboken6
        worker = WaveformLoadWorker(media_id)
        thread = QThread(self)
        worker.moveToThread(thread)

        if not hasattr(self, "_waveform_workers"):
            self._waveform_workers = []
        self._waveform_workers.append((worker, thread))

        def on_done(ok, band_low, band_mid, band_high, beat_positions):
            try:
                if ok and shiboken6.isValid(clip_item):
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
                # H-8: feste Reihenfolge — erst quit(), dann Registry-
                # Entfernung; selbst wenn remove() wirft, wird der Thread
                # gestoppt. deleteLater haengt bereits an thread.finished.
                try:
                    thread.quit()
                finally:
                    if (worker, thread) in self._waveform_workers:
                        self._waveform_workers.remove((worker, thread))

        # H-1/B-222: Explizit QueuedConnection. ``on_done`` ist ein kontext-
        # freier Python-Callable — mit AutoConnection liefe er direkt im
        # Worker-Thread und wuerde dort ein WaveformGraphicsItem (UI-Objekt)
        # erzeugen (Qt-Undefined-Behavior, Crash-Klasse B-222). Queued landet
        # der Aufruf im Thread, in dem connect() lief (Main-Thread).
        worker.finished.connect(on_done, Qt.ConnectionType.QueuedConnection)
        thread.started.connect(worker.run)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(worker.deleteLater)
        thread.start()

    def _load_waveform_for_track(self, session, track, entry, dur, y, parent_clip: TimelineClipItem | None = None):
        """Lädt Rekordbox-Wellenform aus DB und fügt sie zur Scene oder als Child zum Clip hinzu."""
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
            parent=parent_clip,
        )
        if parent_clip:
            wf_item.setPos(0, 0)
            self._style_visible_waveform(wf_item, parent_clip=parent_clip)
        else:
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
                # B-090/B-630: column-select statt ORM-Voll-Laden (waveform_data
                # JSON-Blob band_low/mid/high). Reiner Existenz-Check ueber Child-PK
                # ohne Blob-Load; nutzt nur WaveformData.id. Der async Waveform-Load
                # bleibt unveraendert.
                has_waveform = session.execute(
                    select(WaveformData.id).where(
                        WaveformData.audio_track_id == media_id
                    )
                ).first() is not None
        elif track_type == "video":
            with DBSession(engine) as session:
                # B-090/B-630: column-select statt ORM-Voll-Laden (VideoClip.scenes
                # eager-Relationships); nutzt nur file_path.
                row = session.execute(
                    select(VideoClip.file_path).where(
                        VideoClip.id == media_id, VideoClip.deleted_at.is_(None)
                    )
                ).first()
                thumbnail_file_path = str(row.file_path) if row else None

        # M1 (D-066): Record anlegen + sofort materialisieren — ein Drop/Add
        # passiert immer im sichtbaren Bereich. Neue Clips haben keine Anker
        # (P8-A2-FIX: _anchor_map hat keinen Eintrag -> leere Liste, kein
        # DB-Query).
        rec = ClipRecord(
            entry_id=entry_id, media_id=media_id, track_type=track_type,
            title=title, x=x, y=y, width=width, height=TRACK_HEIGHT,
            has_waveform=has_waveform,
            thumbnail_file_path=thumbnail_file_path,
        )
        self.clip_records.append(rec)
        self._records_by_entry[entry_id] = rec
        item = self._materialize_record(rec)

        if track_type == "audio" and has_waveform:
            # Asynchrones Laden im Hintergrund, kein UI-Blocking beim Drop
            self._load_waveform_async(media_id, start_time, duration, y, item)
        self._update_scene_rect()
        self._schedule_thumb_request()

    def set_cut_points(self, cuts: list[CutPoint], total_duration: float):
        started_at = time.perf_counter()
        signature = (
            round(float(total_duration or 0.0), 3),
            tuple(
                (
                    round(float(cp.time), 3),
                    str(cp.source),
                    round(float(cp.strength), 3),
                )
                for cp in cuts
            ),
        )
        if signature == self._cut_points_signature:
            logger.info(
                "B-598 timeline set_cut_points no-op count=%d duration_ms=%.1f",
                len(cuts),
                (time.perf_counter() - started_at) * 1000.0,
            )
            return
        self._cut_points_signature = signature
        vp = self.viewport()
        vp.setUpdatesEnabled(False)
        try:
            # M1.3 (D-066): Legacy-Einzel-Items raeumen (nach dem Umbau leer),
            # dann alle Cuts als Daten in das EINE CutLinesItem geben —
            # kein QGraphicsLineItem pro Cut mehr (vorher 1400+ Items).
            for line in self.cut_lines:
                self._scene.removeItem(line)
            self.cut_lines.clear()
            self._cut_lines_item.set_data(cuts)

            # Update total duration and redraw backgrounds if needed
            if total_duration > self._total_duration:
                self._total_duration = total_duration
                self._draw_track_backgrounds()

            self._draw_ruler(total_duration)
            self._update_scene_rect()
        finally:
            vp.setUpdatesEnabled(True)
            logger.info(
                "B-598 timeline set_cut_points count=%d duration_ms=%.1f",
                len(cuts),
                (time.perf_counter() - started_at) * 1000.0,
            )

    def set_beat_markers(self, beat_times: list[float]) -> None:
        """Zeichnet goldene Beat-Marker auf der Timeline (AI-Funktion)."""
        started_at = time.perf_counter()
        signature = tuple(round(float(t), 3) for t in sorted(beat_times))
        if signature == self._beat_marker_signature:
            logger.info(
                "B-598 timeline set_beat_markers no-op count=%d duration_ms=%.1f",
                len(beat_times),
                (time.perf_counter() - started_at) * 1000.0,
            )
            return
        self._beat_marker_signature = signature
        vp = self.viewport()
        vp.setUpdatesEnabled(False)
        try:
            # M1.3 (D-066): Legacy-Einzel-Items raeumen (nach dem Umbau leer),
            # dann alle Beats als Daten in das EINE BeatMarkersItem geben —
            # kein QGraphicsLineItem pro Beat mehr (DJ-Sets: 12k+ Items).
            for line in self._beat_markers:
                self._scene.removeItem(line)
            self._beat_markers.clear()
            self._beat_times = list(signature)
            self._beat_markers_item.set_data(self._beat_times)
        finally:
            vp.setUpdatesEnabled(True)
            logger.info(
                "B-598 timeline set_beat_markers count=%d duration_ms=%.1f",
                len(beat_times),
                (time.perf_counter() - started_at) * 1000.0,
            )

    # ── AUD-70: Beat Grid Overlay + Section Colors ───────────────

    # Section color mapping: label -> (background_color, border_color)
    SECTION_COLORS = {
        "DROP":      (QColor(180, 40, 40, 35),   QColor(255, 60, 60, 100)),
        "BUILDUP":   (QColor(200, 170, 30, 30),  QColor(255, 210, 40, 90)),
        "BREAKDOWN": (QColor(40, 90, 180, 30),   QColor(60, 130, 255, 90)),
        # B-617-Nachtrag (GUI-Verify 2026-07-15): VERSE/WARMUP sind echte,
        # haeufige Labels (waren nicht im Dict -> fielen auf INTRO-Grau zurueck).
        "VERSE":     (QColor(50, 150, 90, 30),   QColor(70, 200, 120, 90)),
        "WARMUP":    (QColor(180, 110, 40, 30),  QColor(240, 150, 60, 90)),
        "INTRO":     (QColor(100, 100, 100, 20), QColor(140, 140, 140, 60)),
        "OUTRO":     (QColor(100, 100, 100, 20), QColor(140, 140, 140, 60)),
    }

    def load_sections(self, audio_track_id: int) -> None:
        """Laedt StructureSegments aus der DB und zeichnet farbige Sektions-Hintergruende."""
        self._clear_sections()
        with DBSession(engine) as session:
            # B-090/B-630: column-select statt ORM-Voll-Laden (StructureSegment.
            # audio_track lazy='joined' zieht AudioTrack-Blobs); nutzt nur
            # label/start_time/end_time/energy. Der column-select vermeidet den
            # relationship-join automatisch.
            segments = session.execute(
                select(
                    StructureSegment.label, StructureSegment.start_time,
                    StructureSegment.end_time, StructureSegment.energy,
                )
                .where(StructureSegment.audio_track_id == audio_track_id)
                .order_by(StructureSegment.start_time)
            ).all()
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
            # B-617: column-select statt ORM-Voll-Laden. Beatgrid.audio_track ist
            # lazy='joined' (models.py:292) und wuerde ueber AudioTrack.waveform_data/
            # beatgrid (lazy='joined', 195/196) die grossen JSON-Blobs eager ziehen ->
            # GUI-Freeze (B-090/B-630-Klasse), sobald dieser frueher tote Code aktiv
            # wird. column-select vermeidet den relationship-join automatisch und
            # laedt nur die 3 real genutzten JSON-Arrays.
            row = session.execute(
                select(
                    Beatgrid.beat_positions,
                    Beatgrid.downbeat_positions,
                    Beatgrid.energy_per_beat,
                ).where(Beatgrid.audio_track_id == audio_track_id)
            ).first()
            if not row:
                return

            beat_times = []
            downbeat_times = []
            energy_per_beat = []

            # H7-FIX: Column(JSON) deserialisiert automatisch.
            # isinstance-Check fuer Backward-compat mit alten doppelt-serialisierten Daten.
            if row.beat_positions:
                try:
                    beat_times = (json.loads(row.beat_positions)
                                  if isinstance(row.beat_positions, str)
                                  else row.beat_positions)
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning("load_beat_grid: failed to parse beat_positions: %s", exc)

            if row.downbeat_positions:
                try:
                    downbeat_times = (json.loads(row.downbeat_positions)
                                      if isinstance(row.downbeat_positions, str)
                                      else row.downbeat_positions)
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning("load_beat_grid: failed to parse downbeat_positions: %s", exc)

            if row.energy_per_beat:
                try:
                    energy_per_beat = (json.loads(row.energy_per_beat)
                                       if isinstance(row.energy_per_beat, str)
                                       else row.energy_per_beat)
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
        # B-529: Drag-Start/Dauer JETZT festhalten (waehrend des Drags ist der
        # Item-Cache gueltig). mouseReleaseEvent loescht ihn, bevor der
        # 200ms-Debounce _flush_pending_moves feuert -> sonst ging das
        # MoveClipCommand verloren und Strg+Z entfernte stattdessen
        # Clip-Hinzufuegungen.
        clip_item = self._find_clip_item(entry_id)
        drag_start_x = getattr(clip_item, "_drag_start_x", None) if clip_item else None
        duration = getattr(clip_item, "_drag_duration", None) if clip_item else None
        prev = self._pending_moves.get(entry_id)
        # Den ersten erfassten Drag-Start behalten (Beginn der Drag-Geste).
        if isinstance(prev, dict) and prev.get("drag_start_x") is not None:
            drag_start_x = prev["drag_start_x"]
            if prev.get("duration") is not None:
                duration = prev["duration"]
        self._pending_moves[entry_id] = {
            "new_start": new_start,
            "drag_start_x": drag_start_x,
            "duration": duration,
        }
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
            for entry_id, rec in moves.items():
                clip_item = self._find_clip_item(entry_id)
                if not clip_item:
                    continue

                # B-529: bevorzugt die zur Move-Zeit festgehaltenen Werte; der
                # Item-Cache ist nach mouseReleaseEvent bereits geloescht.
                new_start = rec["new_start"]
                drag_start_x = rec.get("drag_start_x")
                duration = rec.get("duration")
                if drag_start_x is None:
                    drag_start_x = clip_item._drag_start_x
                if duration is None:
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
        """Aktualisiert die Position eines Clips (fuer Undo/Redo).

        M1 (D-066): record-first — der Record ist die Wahrheit fuer alle
        (auch entmaterialisierte) Clips; das Item zieht nach, falls es
        gerade materialisiert ist.
        """
        new_x = start_time * PIXELS_PER_SECOND
        rec = self._find_clip_record(entry_id)
        if rec is not None:
            rec.x = new_x
        item = self._find_clip_item(entry_id)
        if item:
            item.setPos(new_x, item._track_y)

    def _remove_clip_item(self, entry_id: int):
        """Entfernt einen Clip (Record + Item, fuer Undo/Redo)."""
        rec = self._records_by_entry.pop(int(entry_id), None)
        if rec is not None and rec in self.clip_records:
            self.clip_records.remove(rec)
        item = rec.item if rec is not None else self._find_clip_item(entry_id)
        if rec is not None:
            rec.item = None
        if item:
            try:
                self._scene.removeItem(item)
            except RuntimeError:
                pass
            if item in self.clip_items:
                self.clip_items.remove(item)
            fp = getattr(item, "thumbnail_file_path", None)
            if fp:
                lst = self._thumb_items_by_path.get(str(fp))
                if lst and item in lst:
                    lst.remove(item)

    def _sync_clip_lock_visual(self, entry_id: int, locked: bool) -> None:
        """Synchronisiert die Lock-Anzeige nach DB-Toggle.

        SCHNITT-Redesign 2026-05-09 Tier-1 Hardening (D11):
        ToggleClipLockCommand.redo/undo ruft das nach dem DB-Write,
        damit Goldrand + Lock-Icon ohne Full-Reload mitziehen.
        M1 (D-066): record-first, Item nur falls materialisiert.
        """
        rec = self._find_clip_record(entry_id)
        if rec is not None:
            rec.locked = bool(locked)
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
        """Aktualisiert Position und Breite eines Clips nach Trim (fuer Undo/Redo).

        M1 (D-066): record-first — Geometrie landet immer im Record; das
        Item zieht nur nach, falls es gerade materialisiert ist.
        """
        rec = self._find_clip_record(entry_id)
        item = self._find_clip_item(entry_id)
        if rec is None and item is None:
            return
        old_width = (item._clip_width if item is not None
                     else rec.width)
        new_x = start * PIXELS_PER_SECOND
        duration = (end - start) if end is not None else old_width / PIXELS_PER_SECOND
        new_width = duration * PIXELS_PER_SECOND
        if rec is not None:
            rec.x = new_x
            rec.width = new_width
        if item is None:
            return
        item.setPos(new_x, item._track_y)
        item.setRect(QRectF(0, 0, new_width, item._clip_height))
        item._clip_width = new_width
        # Update right trim handle position
        item._right_handle.setRect(QRectF(new_width - 3, 0, 3, item._clip_height))

    def refresh_clip_geometry_from_db(self, entry_id: int) -> None:
        """B-523-FIX: aktualisiert NUR die Geometrie des betroffenen Clips aus
        der DB (Position/Breite), statt die gesamte Timeline via load_from_db()
        abzureissen. Der frueher vom SchnittController genutzte Voll-Teardown
        liess die Szene bei async-Reload-Fehlern komplett leer zurueck (A1/V1
        verschwanden bis App-Neustart). Spiegelt den bewaehrten Undo/Redo-Pfad
        ueber _sync_clip_after_trim.
        """
        # M1 (D-066): Record reicht — _sync_clip_after_trim ist record-first,
        # ein gerade entmaterialisierter Clip bekommt die Geometrie trotzdem.
        if self._find_clip_record(entry_id) is None and self._find_clip_item(entry_id) is None:
            return
        try:
            with nullpool_session() as session:
                entry = session.get(TimelineEntry, entry_id)
                if entry is None:
                    return
                start = entry.start_time or 0.0
                end = entry.end_time
        except Exception as exc:  # noqa: BLE001 — Inspector-Edit darf UI nie killen
            logger.warning("[B-523] refresh_clip_geometry_from_db fehlgeschlagen: %s", exc)
            return
        self._sync_clip_after_trim(entry_id, start, end)

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

    def toggle_clip_lock_by_id(self, entry_id: int, locked: bool) -> None:
        """B-295: Lock-Status eines Cuts per entry_id setzen (CutListPanel-Kontextmenue).

        Nutzt denselben ToggleClipLockCommand wie der Lock-Icon-Klick — also
        Undo + DB-Persistenz. Aktualisiert zusaetzlich das Lock-Visual des Clips.
        """
        from ui.undo_commands import ToggleClipLockCommand
        cmd = ToggleClipLockCommand(int(entry_id), bool(locked), timeline=self)
        stack = getattr(self, "undo_stack", None)
        if stack is not None:
            stack.push(cmd)
        else:
            cmd.redo()
        self._sync_clip_lock_visual(int(entry_id), bool(locked))

    def remove_clip_by_id(self, entry_id: int) -> None:
        """B-295: Cut per entry_id entfernen (CutListPanel-Kontextmenue).

        Nutzt denselben RemoveClipCommand wie remove_selected_clips — also
        Undo + DB-Loeschung + Scene-Cleanup.
        """
        from ui.undo_commands import RemoveClipCommand
        cmd = RemoveClipCommand(timeline=self, entry_id=int(entry_id))
        stack = getattr(self, "undo_stack", None)
        if stack is not None:
            stack.push(cmd)
        else:
            cmd.redo()

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
        """Zoom mit Mausrad; Shift+Rad oder horizontales Rad-Delta scrollt seitlich."""
        angle = event.angleDelta()
        # B-645: Shift+Mausrad (Standard bei DaVinci/Studio One/Rekordbox) oder
        # natives horizontales Delta (Trackpad-Swipe) scrollt statt zu zoomen.
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier or angle.x() != 0:
            hs = self.horizontalScrollBar()
            step = angle.x() if angle.x() != 0 else angle.y()
            hs.setValue(hs.value() - step)
            event.accept()
            return
        delta = angle.y()
        if delta == 0:
            return
        factor = 1.08 if delta > 0 else 1.0 / 1.08
        current_scale = self.transform().m11()
        new_scale = current_scale * factor
        if new_scale < 0.01 or new_scale > 200.0:
            return
        old_zoom = self._current_zoom
        vscroll = self.verticalScrollBar().value()  # B-645: Zoom darf Y nicht verschieben
        self.scale(factor, 1.0)
        self.verticalScrollBar().setValue(vscroll)
        self._current_zoom = new_scale
        # LOD-Update nur bei signifikanter Zoom-Aenderung (Schwellwert-Ueberschreitung)
        old_lod = 4 if old_zoom < 0.5 else (2 if old_zoom < 1.5 else 1)
        new_lod = 4 if new_scale < 0.5 else (2 if new_scale < 1.5 else 1)
        if old_lod != new_lod:
            self._update_beat_grid_lod()
        self._schedule_thumb_request()  # B-471 T1: Zoom aendert sichtbaren Clip-Satz
        self.zoom_changed.emit(new_scale)

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
        elif event.button() == Qt.MouseButton.LeftButton:
            # B-553: RubberBandDrag verhindern, wenn auf Clip oder dessen Kinder geklickt wird
            item = self.itemAt(event.position().toPoint())
            while item:
                if isinstance(item, TimelineClipItem):
                    self.setDragMode(QGraphicsView.DragMode.NoDrag)
                    break
                item = item.parentItem()
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
        # B-553: RubberBandDrag wieder aktivieren
        if event.button() == Qt.MouseButton.LeftButton:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

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

    def _on_feedback_confirmed(self, event_id: int) -> None:
        """NEUBAU-VOLLINTEGRATION T1.6: sichtbare Bestaetigung fuer
        Feedback-Tastendruecke (A/R/S/1-5). Console-Log falls verdrahtet,
        sonst mindestens App-Log."""
        msg = (
            f"[Feedback] Bewertung gespeichert (Event #{event_id}) — "
            "fliesst in das Pacing-Lernen ein."
        )
        cb = getattr(self, "console_log", None)
        if callable(cb):
            cb(msg)
        else:
            logger.info(msg)

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
        from services.brain import BrainService
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
        vscroll = self.verticalScrollBar().value()  # B-645: Zoom darf Y nicht verschieben
        self.scale(factor, 1.0)
        self.verticalScrollBar().setValue(vscroll)
        self._current_zoom = new_scale
        old_lod = 4 if old_zoom < 0.5 else (2 if old_zoom < 1.5 else 1)
        new_lod = 4 if new_scale < 0.5 else (2 if new_scale < 1.5 else 1)
        if old_lod != new_lod:
            self._update_beat_grid_lod()
        self.zoom_changed.emit(new_scale)

    def reset_zoom(self):
        """Reset timeline zoom to 100 percent."""
        old_zoom = self._current_zoom
        vscroll = self.verticalScrollBar().value()  # B-645: Zoom darf Y nicht verschieben
        self.resetTransform()
        self.verticalScrollBar().setValue(vscroll)
        self._current_zoom = 1.0
        old_lod = 4 if old_zoom < 0.5 else (2 if old_zoom < 1.5 else 1)
        if old_lod != 2:
            self._update_beat_grid_lod()
        self.zoom_changed.emit(1.0)

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
        x_scale = max(MIN_READABLE_FIT_SCALE, min(200.0, x_scale))
        self.resetTransform()
        self.scale(x_scale, 1.0)
        self._current_zoom = self.transform().m11()
        self._update_beat_grid_lod()
        self.centerOn(rect.center().x(), AUDIO_TRACK_Y + TRACK_HEIGHT + 5)
        self._schedule_thumb_request()
        self.zoom_changed.emit(self._current_zoom)

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
        # M1 (D-066): arbeitet auf Records — deckt auch entmaterialisierte
        # Video-Clips ab. Bei materialisierten Items ist item.pos() die
        # frischeste Position (laufende Drags), sonst record.x.
        audio_clips = [r for r in self.clip_records if r.track_type == "audio"]
        video_clips = [r for r in self.clip_records if r.track_type == "video"]

        if not audio_clips or not video_clips:
            return False

        synced = False
        # Bug-18 Fix: Eine Session für alle Updates statt einer pro Video-Clip
        updates: list[tuple[int, float, float | None]] = []  # (entry_id, new_start, new_end|None)

        def _first_anchor_offset(rec: ClipRecord) -> float | None:
            """Get first anchor time_offset from cached _anchor_map (no DB hit)."""
            anchors = self._anchor_map.get(rec.entry_id)
            if not anchors:
                return None
            return min(a.time_offset for a in anchors)

        def _rec_x(rec: ClipRecord) -> float:
            if rec.item is not None:
                try:
                    return rec.item.pos().x()
                except RuntimeError:
                    pass
            return rec.x

        for audio_clip in audio_clips:
            audio_anchor_offset = _first_anchor_offset(audio_clip)
            if audio_anchor_offset is None:
                continue

            # Absoluter Zeitpunkt des Audio-Ankers auf der Timeline
            audio_clip_start = _rec_x(audio_clip) / PIXELS_PER_SECOND
            audio_anchor_abs = audio_clip_start + audio_anchor_offset

            for video_clip in video_clips:
                video_anchor_offset = _first_anchor_offset(video_clip)
                if video_anchor_offset is None:
                    continue

                # Video-Clip verschieben: Anker soll auf audio_anchor_abs landen
                new_video_start = max(0.0, audio_anchor_abs - video_anchor_offset)
                new_x = new_video_start * PIXELS_PER_SECOND
                video_clip.x = new_x
                if video_clip.item is not None:
                    try:
                        video_clip.item.setPos(new_x, video_clip.item._track_y)
                    except RuntimeError:
                        pass
                updates.append((video_clip.entry_id, new_video_start, None))
                synced = True

        if updates:
            from database import nullpool_session
            with nullpool_session() as session:
                # E7: EIN Bulk-Load statt session.get() pro Update —
                # session.get() lud pro Entry zusaetzlich joined Project +
                # selectin Anchors. Fehlende IDs werden wie bisher
                # uebersprungen (get->None-Semantik via dict.get). Doppelte
                # entry_ids in updates treffen dank Identity-Map/Dict
                # dasselbe Objekt — letzter Schreiber gewinnt, wie vorher.
                _ids = [entry_id for entry_id, _, _ in updates]
                _entries_by_id = {
                    e.id: e
                    for e in session.query(TimelineEntry).options(
                        lazyload("*"),
                    ).filter(TimelineEntry.id.in_(_ids)).all()
                }
                for entry_id, new_start, _ in updates:
                    entry = _entries_by_id.get(entry_id)
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
            # team-sweep 2026-07-15: Crash-Guard — float()-Konvertierung des MIME-Payload absichern
            try:
                duration = float(duration)
            except (ValueError, TypeError):
                duration = 30.0 if track_type == "audio" else 10.0
        else:
            with DBSession(engine) as session:
                if track_type == "audio":
                    # B-090/B-630: column-select statt ORM-Voll-Laden (AudioTrack
                    # beatgrid/waveform_data lazy='joined' Blobs); nutzt nur duration.
                    row = session.execute(
                        select(AudioTrack.duration).where(
                            AudioTrack.id == media_id, AudioTrack.deleted_at.is_(None)
                        )
                    ).first()
                    duration = row.duration if row and row.duration else 30.0
                else:
                    # B-090/B-630: column-select statt ORM-Voll-Laden (VideoClip.scenes
                    # eager-Relationships); nutzt nur duration.
                    row = session.execute(
                        select(VideoClip.duration).where(
                            VideoClip.id == media_id, VideoClip.deleted_at.is_(None)
                        )
                    ).first()
                    duration = row.duration if row and row.duration else 10.0

        # Get active project
        from database import get_active_project_id
        project_id = get_active_project_id()
        if project_id is None:
            # Sweep-2 (2026-07-14): get_active_project_id() liefert bewusst None
            # wenn kein Projekt aktiv ist (database/session.py — kein Fallback auf
            # ID=1). AddClipCommand -> TimelineEntry(project_id NOT NULL) wuerde
            # beim flush eine IntegrityError werfen, die roh aus diesem Qt-Drop-
            # Handler propagiert und die App beendet. Statt Crash: Drop ignorieren.
            logger.warning("[Timeline] Drop ignoriert — kein aktives Projekt geladen.")
            if self.console_log:
                self.console_log("[Timeline] Drop ignoriert — kein aktives Projekt geladen.")
            event.ignore()
            return

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
