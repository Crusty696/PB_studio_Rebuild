"""Media Pool Grid View — Thumbnail/Waveform cards with metadata overlay.

AUD-72: Grid-View fuer Video Pool (Thumbnails) und Audio Pool (Waveform-Miniatur).
  - VideoCard: extracts first frame via ffmpeg (lazy, background thread)
  - AudioCard: paints mini waveform from energy_curve data
  - MediaPoolGrid: responsive flow-grid with integrated Filter/Sort bar
  - Toggle between List (QTableWidget) and Grid view is wired in media_workspace.py
"""

from __future__ import annotations

from collections import OrderedDict
import json
import logging
import os
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QScrollArea, QGridLayout, QFrame, QVBoxLayout,
    QHBoxLayout, QLabel, QLineEdit, QComboBox, QMenu,
)
from PySide6.QtCore import Qt, Signal, QRect, QThread, QObject, QTimer
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QFont, QFontMetrics

from services.timeout_constants import FFMPEG_THUMBNAIL_TIMEOUT_SEC

logger = logging.getLogger(__name__)


# ── Thumbnail cache ───────────────────────────────────────────────────────────

_THUMB_CACHE: Path = (
    Path(os.environ.get("LOCALAPPDATA", "C:/tmp")) / "PBStudio" / "thumbnails"
)


def _ensure_thumb_dir() -> None:
    _THUMB_CACHE.mkdir(parents=True, exist_ok=True)


def _thumb_path(file_path: str) -> Path:
    import hashlib
    h = hashlib.md5(file_path.encode(), usedforsecurity=False).hexdigest()[:14]
    return _THUMB_CACHE / f"{h}.jpg"


# ── Visual helpers ────────────────────────────────────────────────────────────

def _placeholder_pixmap(w: int, h: int, icon: str = "") -> QPixmap:
    pix = QPixmap(w, h)
    pix.fill(QColor("#0d1117"))
    if icon:
        p = QPainter(pix)
        p.setPen(QColor("#374151"))
        p.setFont(QFont("Segoe UI", 18))
        p.drawText(QRect(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, icon)
        p.end()
    return pix


# F-029: Performance & Stabilitäts-Optimierung
# L-37 FIX: Use OrderedDict with LRU eviction instead of full clear
_WAVEFORM_CACHE: OrderedDict = OrderedDict()
_WAVEFORM_CACHE_MAX = 200

def _paint_waveform(w: int, h: int, energy: list[float]) -> QPixmap:
    """Paint a two-tone waveform with caching (Fix F-029)."""
    cache_key = (w, h, tuple(energy[:100]), len(energy)) # Simple heuristic key
    if cache_key in _WAVEFORM_CACHE:
        # L-37 FIX: Move to end to mark as recently used
        _WAVEFORM_CACHE.move_to_end(cache_key)
        return _WAVEFORM_CACHE[cache_key]

    pix = QPixmap(w, h)
    pix.fill(QColor("#0d1117"))
    if not energy:
        return pix

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    n = len(energy)
    step = max(1, n // w)
    samples: list[float] = []
    for i in range(0, n, step):
        chunk = energy[i: i + step]
        samples.append(max(chunk) if chunk else 0.0)
    samples = samples[:w]

    mid = h // 2
    c_top = QColor("#d4a44a")
    c_bot = QColor("#7a5818")

    for x, val in enumerate(samples):
        bar = max(1, int(val * mid * 0.92))
        p.setPen(QPen(c_top, 1))
        p.drawLine(x, mid - bar, x, mid)
        p.setPen(QPen(c_bot, 1))
        p.drawLine(x, mid, x, mid + bar)

    p.end()

    # L-37 FIX: LRU eviction - remove oldest item when cache is full
    if len(_WAVEFORM_CACHE) >= _WAVEFORM_CACHE_MAX:
        _WAVEFORM_CACHE.popitem(last=False)  # Remove oldest (FIFO/LRU)
    _WAVEFORM_CACHE[cache_key] = pix
    return pix


# ── Background thumbnail loader ───────────────────────────────────────────────

class _ThumbWorker(QObject):
    done = Signal(str, object)  # (file_path, QPixmap)

    def __init__(self, file_path: str, w: int, h: int) -> None:
        super().__init__()
        self._path = file_path
        self._w = w
        self._h = h

    def run(self) -> None:
        self.done.emit(self._path, self._extract())

    def _extract(self) -> QPixmap:
        _ensure_thumb_dir()
        dest = _thumb_path(self._path)
        if not self._path or not Path(self._path).exists():
            return _placeholder_pixmap(self._w, self._h, "✖")

        if not dest.exists():
            try:
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-ss", "0", "-i", self._path,
                        "-vframes", "1",
                        "-vf",
                        f"scale={self._w}:{self._h}:force_original_aspect_ratio=decrease,"
                        f"pad={self._w}:{self._h}:(ow-iw)/2:(oh-ih)/2:black",
                        str(dest),
                    ],
                    capture_output=True,
                    timeout=FFMPEG_THUMBNAIL_TIMEOUT_SEC,
                )
            except (subprocess.SubprocessError, OSError, FileNotFoundError):
                return _placeholder_pixmap(self._w, self._h, "▶")
        pix = QPixmap(str(dest))
        return pix if not pix.isNull() else _placeholder_pixmap(self._w, self._h, "▶")


# ── Card constants ────────────────────────────────────────────────────────────

_CW = 162   # card width  (px)
_CH = 148   # card height (px)
_TH = 90    # thumbnail / waveform area height
_GAP = 6    # grid gap between cards

_CARD_STYLE = (
    "MediaCard{background:#131922;border:1px solid rgba(255,255,255,0.07);"
    "border-radius:8px;}"
    "MediaCard:hover{border:1px solid rgba(212,164,74,0.45);background:#161d28;}"
)
_CARD_SEL_STYLE = (
    "MediaCard{background:#1a2233;border:1.5px solid #d4a44a;border-radius:8px;}"
)


# F-026 Fix: Shared resources for better performance
_ELIDE_FONT = QFont("Segoe UI", 8)
_ELIDE_METRICS = None

def _get_metrics():
    global _ELIDE_METRICS
    if _ELIDE_METRICS is None:
        _ELIDE_METRICS = QFontMetrics(_ELIDE_FONT)
    return _ELIDE_METRICS

class MediaCard(QFrame):
    """Base clickable pool card."""
    clicked = Signal(int)  # media_id
    show_status_requested = Signal(int)   # media_id — context menu: show analysis status
    run_all_requested = Signal(int)       # media_id — context menu: run all analyses

    def __init__(self, media_id: int, title: str, parent=None) -> None:
        super().__init__(parent)
        self._id = media_id
        self._title = title
        self.setObjectName("MediaCard")
        self.setProperty("selected", False)
        self.setFixedSize(_CW, _CH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def set_selected(self, sel: bool) -> None:
        # P8-F2-FIX: unpolish+polish in Click-Pfad triggerte O(N)-Style-
        # Rebuild ueber alle Child-Widgets (bei vielen Cards laggy bei
        # Shift-Select). polish() ist noetig, damit der Stylesheet
        # [selected="true"] Selektor greift — wir schieben es per
        # QTimer.singleShot(0) aus dem Event-Handler raus, sodass der
        # Klick-Event sofort zurueckkommt und der Repaint danach async.
        if self.property("selected") == sel:
            return
        self.setProperty("selected", sel)
        from PySide6.QtCore import QTimer
        def _repolish(w=self):
            try:
                w.style().unpolish(w)
                w.style().polish(w)
            except RuntimeError:
                pass  # widget wurde schon zerstoert
        QTimer.singleShot(0, _repolish)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._id)
        super().mousePressEvent(event)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:#1a2030;color:#e5e7eb;border:1px solid rgba(255,255,255,0.1);}"
            "QMenu::item:selected{background:#d4a44a;color:#0d1117;}"
        )
        act_status = menu.addAction("Analyse-Status anzeigen")
        act_run = menu.addAction("Alle Analysen starten")
        action = menu.exec(self.mapToGlobal(pos))
        if action == act_status:
            self.show_status_requested.emit(self._id)
        elif action == act_run:
            self.run_all_requested.emit(self._id)

    @staticmethod
    def _elide(text: str, max_w: int) -> str:
        return _get_metrics().elidedText(text, Qt.TextElideMode.ElideRight, max_w)

    @staticmethod
    def _meta_lbl(text: str, color: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{color}; font-size:8px;")
        return lbl


class VideoCard(MediaCard):
    """Video pool card: ffmpeg thumbnail + resolution/fps metadata."""

    def __init__(
        self,
        media_id: int,
        title: str,
        file_path: str,
        resolution: str = "",
        fps: float = None,
        parent=None,
    ) -> None:
        self._file_path = file_path
        self._resolution = resolution or ""
        self._fps = fps
        super().__init__(media_id, title, parent)
        self._build()

    def _build(self) -> None:
        vl = QVBoxLayout(self)
        vl.setContentsMargins(4, 4, 4, 5)
        vl.setSpacing(3)

        self._thumb = QLabel()
        self._thumb.setObjectName("MediaCard_Thumb")
        self._thumb.setFixedSize(_CW - 8, _TH)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setPixmap(_placeholder_pixmap(_CW - 8, _TH, "▶"))
        vl.addWidget(self._thumb)

        title_lbl = QLabel(self._elide(self._title, _CW - 10))
        title_lbl.setObjectName("MediaCard_Title")
        vl.addWidget(title_lbl)

        meta = QHBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(4)
        if self._resolution:
            meta.addWidget(self._meta_lbl(self._resolution, "#60a5fa"))
        if self._fps:
            meta.addWidget(self._meta_lbl(f"{self._fps:.0f}fps", "#6b7280"))
        meta.addStretch()
        vl.addLayout(meta)

    def set_thumbnail(self, pix: QPixmap) -> None:
        # P8-H1-FIX: ffmpeg hat das Thumbnail im Worker bereits auf die
        # Zielgroesse (_CW-8 × _TH) gerendert und gepadded. Zusaetzliche
        # SmoothTransformation-Skalierung im Main-Thread war redundant
        # und bei 100+ Cards im Pool ein Scroll-Freeze.
        if not pix.isNull():
            self._thumb.setPixmap(pix)


class AudioCard(MediaCard):
    """Audio pool card: mini waveform + BPM/Key/Mood metadata."""

    def __init__(
        self,
        media_id: int,
        title: str,
        file_path: str,
        bpm: float = None,
        key: str = None,
        mood: str = None,
        genre: str = None,
        energy_data: list = None,
        parent=None,
    ) -> None:
        self._file_path = file_path
        self._bpm = bpm
        self._key = key
        self._mood = mood
        self._genre = genre
        self._energy = energy_data or []
        super().__init__(media_id, title, parent)
        self._build()

    def _build(self) -> None:
        vl = QVBoxLayout(self)
        vl.setContentsMargins(4, 4, 4, 5)
        vl.setSpacing(3)

        wave_lbl = QLabel()
        wave_lbl.setObjectName("MediaCard_Thumb")
        wave_lbl.setFixedSize(_CW - 8, _TH)
        wave_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self._energy:
            wave_lbl.setPixmap(_paint_waveform(_CW - 8, _TH, self._energy))
        else:
            wave_lbl.setPixmap(_placeholder_pixmap(_CW - 8, _TH, "♪"))
        vl.addWidget(wave_lbl)

        title_lbl = QLabel(self._elide(self._title, _CW - 10))
        title_lbl.setStyleSheet(
            "color:#e5e7eb;font-size:9px;font-weight:600;background:transparent;border:none;"
        )
        vl.addWidget(title_lbl)

        meta = QHBoxLayout()
        meta.setContentsMargins(0, 0, 0, 0)
        meta.setSpacing(4)
        if self._bpm:
            meta.addWidget(self._meta_lbl(f"{self._bpm:.0f}", "#d4a44a"))
            meta.addWidget(self._meta_lbl("BPM", "#4b5563"))
        if self._key:
            meta.addWidget(self._meta_lbl(self._key, "#00e5ff"))
        if self._mood:
            meta.addWidget(self._meta_lbl(self._mood, "#4ade80"))
        meta.addStretch()
        vl.addLayout(meta)


# ── Grid container ────────────────────────────────────────────────────────────

_AUDIO_SORT = ["Name", "BPM ▲", "BPM ▼", "Key", "Genre", "Mood"]
_VIDEO_SORT = ["Name", "Aufloesung", "FPS ▼"]

_FILTER_STYLE = (
    "QLineEdit{background:#1a2030;border:1px solid rgba(255,255,255,0.1);"
    "border-radius:4px;color:#e5e7eb;padding:1px 5px;font-size:9px;}"
    "QComboBox{background:#1a2030;border:1px solid rgba(255,255,255,0.1);"
    "border-radius:4px;color:#e5e7eb;padding:1px 5px;font-size:9px;}"
)


class MediaPoolGrid(QWidget):
    """Responsive flow-grid of MediaCards with Filter/Sort bar.

    Public API:
        set_items(items)     — populate from list of dicts
        clear()              — remove all cards

    Signals:
        item_selected(int)   — emitted on card click (media_id)
    """

    item_selected = Signal(int)
    show_status_requested = Signal(int)   # media_id — show analysis status panel
    run_all_requested = Signal(int)       # media_id — run all pending analyses

    def __init__(self, media_type: str = "audio", parent=None) -> None:
        """
        Args:
            media_type: "audio" or "video"
        """
        super().__init__(parent)
        self._type = media_type
        self._all_items: list[dict] = []
        self._cards: list[MediaCard] = []
        self._filtered: list[MediaCard] = []
        self._selected_id: int | None = None
        self._thumb_threads: list[QThread] = []
        self._in_relayout = False  # Rekursions-Guard (Fix: Freeze)
        
        # Debounce timer fuer Relayout (Fix F-029)
        self._relayout_timer = QTimer(self)
        self._relayout_timer.setSingleShot(True)
        self._relayout_timer.setInterval(100) # Max 10 Layouts pro Sekunde
        self._relayout_timer.timeout.connect(self._do_relayout_debounced)
        
        self._build_ui()

    # ── Construction ─────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # ── Filter bar ──────────────────────────────────────────────
        fbar = QHBoxLayout()
        fbar.setContentsMargins(0, 0, 0, 0)
        fbar.setSpacing(4)
        fbar_widget = QWidget()
        fbar_widget.setLayout(fbar)
        fbar_widget.setStyleSheet(_FILTER_STYLE)

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter…")
        self._filter_edit.setFixedHeight(24)
        self._filter_edit.setMaximumWidth(150)
        self._filter_edit.textChanged.connect(self._apply_filter)
        fbar.addWidget(self._filter_edit)

        if self._type == "audio":
            self._bpm_edit = QLineEdit()
            self._bpm_edit.setPlaceholderText("BPM")
            self._bpm_edit.setFixedSize(54, 24)
            self._bpm_edit.setToolTip("BPM-Filter: z.B. 128 oder 120-140")
            self._bpm_edit.textChanged.connect(self._apply_filter)
            fbar.addWidget(self._bpm_edit)

            self._key_edit = QLineEdit()
            self._key_edit.setPlaceholderText("Key")
            self._key_edit.setFixedSize(46, 24)
            self._key_edit.textChanged.connect(self._apply_filter)
            fbar.addWidget(self._key_edit)

            self._genre_edit = QLineEdit()
            self._genre_edit.setPlaceholderText("Genre")
            self._genre_edit.setFixedSize(68, 24)
            self._genre_edit.textChanged.connect(self._apply_filter)
            fbar.addWidget(self._genre_edit)
        else:
            self._bpm_edit = None
            self._key_edit = None
            self._genre_edit = None

        fbar.addStretch()

        self._sort_combo = QComboBox()
        self._sort_combo.setFixedHeight(24)
        self._sort_combo.addItems(
            _AUDIO_SORT if self._type == "audio" else _VIDEO_SORT
        )
        self._sort_combo.currentIndexChanged.connect(self._apply_filter)
        fbar.addWidget(self._sort_combo)

        outer.addWidget(fbar_widget)

        # ── Scroll area ─────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            "QWidget#grid_container{background:transparent;}"
        )

        self._container = QWidget()
        self._container.setObjectName("grid_container")
        self._grid = QGridLayout(self._container)
        self._grid.setContentsMargins(2, 2, 2, 2)
        self._grid.setSpacing(_GAP)

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll, stretch=1)

    # ── Public API ───────────────────────────────────────────────────

    def set_items(self, items: list[dict]) -> None:
        """Populate grid from a list of media dicts."""
        self._all_items = items
        self._rebuild_cards()

    def clear(self) -> None:
        self._all_items = []
        self._rebuild_cards()

    # ── Internal ─────────────────────────────────────────────────────

    def _rebuild_cards(self) -> None:
        if self._in_relayout:
            return
        self._in_relayout = True
        # P8-F1-FIX: Bulk-Remove triggert sonst N Layout-Recomputes +
        # Paint-Events waehrend des while-Loops. Updates aus fuer die
        # Dauer des Rebuilds stummschalten.
        _parent = self._grid.parentWidget() if hasattr(self._grid, "parentWidget") else None
        if _parent is not None:
            _parent.setUpdatesEnabled(False)
        try:
            # H-27 Fix: Threads sauber beenden mit deleteLater nach finished
            for t in self._thumb_threads:
                t.finished.connect(t.deleteLater)
                t.quit()
            self._thumb_threads.clear()

            # Remove all cards from layout and delete
            while self._grid.count():
                item = self._grid.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self._cards.clear()

            # Fix: Inkrementelles Laden via Timer (F-020)
            self._load_index = 0
            self._load_timer = QTimer(self)
            self._load_timer.timeout.connect(self._load_next_chunk)
            self._load_timer.start(20)  # Alle 20ms ein Chunk (stabiler als 5ms)
        except Exception as e:
            logger.error("Fehler beim Vorbereiten des Card-Rebuilds: %s", e)
            self._in_relayout = False
        finally:
            # P8-F1-FIX: Updates in jedem Fall wieder aktivieren
            if _parent is not None:
                _parent.setUpdatesEnabled(True)

    def _load_next_chunk(self):
        """Erstellt Karten in kleinen Batches um UI-Freeze zu verhindern."""
        chunk_size = 10  # Groessere Batches fuer Effizienz
        end = min(self._load_index + chunk_size, len(self._all_items))
        
        for i in range(self._load_index, end):
            data = self._all_items[i]
            if self._type == "video":
                card = VideoCard(
                    media_id=data["id"],
                    title=data.get("title", ""),
                    file_path=data.get("file_path", ""),
                    resolution=data.get("resolution", ""),
                    fps=data.get("fps"),
                )
            else:
                energy = []
                ec = data.get("energy_curve")
                if ec:
                    # H7-FIX: Column(JSON) deserialisiert automatisch.
                    if isinstance(ec, (list, tuple)):
                        energy = ec
                    elif isinstance(ec, str):
                        try:
                            energy = json.loads(ec)
                        except (json.JSONDecodeError, TypeError):  # B-035 Fix: Specific exception types
                            pass  # Invalid JSON or wrong type — use empty list fallback
                card = AudioCard(
                    media_id=data["id"],
                    title=data.get("title", ""),
                    file_path=data.get("file_path", ""),
                    bpm=data.get("bpm"),
                    key=data.get("key"),
                    energy_data=energy,
                )
            card.clicked.connect(self._on_card_clicked)
            card.show_status_requested.connect(self.show_status_requested)
            card.run_all_requested.connect(self.run_all_requested)
            self._cards.append(card)

        self._load_index = end
        if self._load_index >= len(self._all_items):
            self._load_timer.stop()
            self._filtered = list(self._cards)
            self._in_relayout = False
            self._apply_filter()
        # KEIN processEvents() hier — der Timer gibt Qt bereits genug Zeit zum Zeichnen

    def _start_thumb_loader(self, card: VideoCard, file_path: str) -> None:
        thread = QThread(self)
        worker = _ThumbWorker(file_path, _CW - 8, _TH)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        # Use default args to capture per-iteration values
        worker.done.connect(
            lambda _path, pix, c=card: c.set_thumbnail(pix)
        )
        worker.done.connect(
            lambda _path, _pix, t=thread: t.quit()
        )
        thread.finished.connect(thread.deleteLater)
        # B-107 / BUG-A5: also schedule the worker for deletion. Without
        # this the _ThumbWorker C++ shell leaks once per thumbnail; on
        # DJ-set imports with hundreds of clips that adds up.
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(
            lambda t=thread: self._thumb_threads.remove(t) if t in self._thumb_threads else None
        )

        self._thumb_threads.append(thread)
        thread.start()

    def _apply_filter(self) -> None:
        if self._in_relayout:
            return
        self._in_relayout = True
        try:
            text = self._filter_edit.text().lower().strip()
            bpm_text = self._bpm_edit.text().strip() if self._bpm_edit else ""
            key_text = self._key_edit.text().strip().upper() if self._key_edit else ""
            genre_text = self._genre_edit.text().strip().lower() if self._genre_edit else ""

            bpm_min, bpm_max = None, None
            if bpm_text:
                if "-" in bpm_text:
                    parts = bpm_text.split("-", 1)
                    try:
                        bpm_min, bpm_max = float(parts[0]), float(parts[1])
                    except ValueError as exc:
                        logger.warning("_apply_filter: failed to parse BPM range: %s", exc)
                else:
                    try:
                        v = float(bpm_text)
                        bpm_min, bpm_max = v - 2.0, v + 2.0
                    except ValueError as exc:
                        logger.warning("_apply_filter: failed to parse BPM value: %s", exc)

            pairs: list[tuple[MediaCard, dict]] = []
            for card, data in zip(self._cards, self._all_items):
                title = data.get("title", "").lower()
                if text and text not in title:
                    continue
                if bpm_min is not None:
                    bpm = data.get("bpm")
                    if bpm is None or not (bpm_min <= bpm <= bpm_max):
                        continue
                if key_text and key_text not in (data.get("key") or "").upper():
                    continue
                if genre_text and genre_text not in (data.get("genre") or "").lower():
                    continue
                pairs.append((card, data))

            sort_key = self._sort_combo.currentText()
            if sort_key == "BPM ▲":
                pairs.sort(key=lambda x: x[1].get("bpm") or 0)
            elif sort_key == "BPM ▼":
                pairs.sort(key=lambda x: x[1].get("bpm") or 0, reverse=True)
            elif sort_key == "Key":
                pairs.sort(key=lambda x: x[1].get("key") or "")
            elif sort_key == "Genre":
                pairs.sort(key=lambda x: x[1].get("genre") or "")
            elif sort_key == "Mood":
                pairs.sort(key=lambda x: x[1].get("mood") or "")
            elif sort_key == "Aufloesung":
                pairs.sort(key=lambda x: x[1].get("resolution") or "")
            elif sort_key == "FPS ▼":
                pairs.sort(key=lambda x: x[1].get("fps") or 0, reverse=True)
            else:
                pairs.sort(key=lambda x: x[1].get("title") or "")

            self._filtered = [c for c, _ in pairs]
            self._relayout()
        finally:
            self._in_relayout = False

    def _relayout(self) -> None:
        """Trigger debounced relayout (Fix F-029)."""
        self._relayout_timer.start()

    def _do_relayout_debounced(self) -> None:
        """Place filtered cards into grid, hide the rest."""
        if self._in_relayout or not self.isVisible():
            return
        
        self._in_relayout = True
        try:
            while self._grid.count():
                item = self._grid.takeAt(0)
                if item.widget():
                    item.widget().setParent(None)

            avail_w = max(_CW + _GAP, self._scroll.viewport().width())
            cols = max(1, (avail_w + _GAP) // (_CW + _GAP))

            for i, card in enumerate(self._filtered):
                row, col = divmod(i, cols)
                self._grid.addWidget(card, row, col)
                card.show()

            for card in self._cards:
                if card not in self._filtered:
                    card.hide()

            rows = (len(self._filtered) + cols - 1) // cols if self._filtered else 0
            # Blockiere Signale um Resize-Loops zu vermeiden
            self._container.blockSignals(True)
            self._container.setMinimumHeight(rows * (_CH + _GAP) + 10)
            self._container.blockSignals(False)
        finally:
            self._in_relayout = False

    def _on_card_clicked(self, media_id: int) -> None:
        for card in self._cards:
            card.set_selected(card._id == media_id)
        self._selected_id = media_id
        self.item_selected.emit(media_id)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()
