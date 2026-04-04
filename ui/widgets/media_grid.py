"""Media Pool Grid View — Thumbnail/Waveform cards with metadata overlay.

AUD-72: Grid-View fuer Video Pool (Thumbnails) und Audio Pool (Waveform-Miniatur).
  - VideoCard: extracts first frame via ffmpeg (lazy, background thread)
  - AudioCard: paints mini waveform from energy_curve data
  - MediaPoolGrid: responsive flow-grid with integrated Filter/Sort bar
  - Toggle between List (QTableWidget) and Grid view is wired in media_workspace.py
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QScrollArea, QGridLayout, QFrame, QVBoxLayout,
    QHBoxLayout, QLabel, QLineEdit, QComboBox,
)
from PySide6.QtCore import Qt, Signal, QRect, QThread, QObject
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QFont, QFontMetrics

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


def _paint_waveform(w: int, h: int, energy: list[float]) -> QPixmap:
    """Paint a two-tone (top/bottom) waveform pixmap from energy [0..1] data."""
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
                    timeout=10,
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


class MediaCard(QFrame):
    """Base clickable pool card."""
    clicked = Signal(int)  # media_id

    def __init__(self, media_id: int, title: str, parent=None) -> None:
        super().__init__(parent)
        self._id = media_id
        self._title = title
        self.setObjectName("MediaCard")
        self.setFixedSize(_CW, _CH)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(_CARD_STYLE)

    def set_selected(self, sel: bool) -> None:
        self.setStyleSheet(_CARD_SEL_STYLE if sel else _CARD_STYLE)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._id)
        super().mousePressEvent(event)

    @staticmethod
    def _elide(text: str, max_w: int) -> str:
        fm = QFontMetrics(QFont("Segoe UI", 8))
        return fm.elidedText(text, Qt.TextElideMode.ElideRight, max_w)

    @staticmethod
    def _meta_lbl(text: str, color: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color:{color};font-size:8px;background:transparent;border:none;"
        )
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
        self._thumb.setFixedSize(_CW - 8, _TH)
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setStyleSheet(
            "border-radius:4px;background:#0d1117;border:none;"
        )
        self._thumb.setPixmap(_placeholder_pixmap(_CW - 8, _TH, "▶"))
        vl.addWidget(self._thumb)

        title_lbl = QLabel(self._elide(self._title, _CW - 10))
        title_lbl.setStyleSheet(
            "color:#e5e7eb;font-size:9px;font-weight:600;background:transparent;border:none;"
        )
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
        if not pix.isNull():
            scaled = pix.scaled(
                _CW - 8, _TH,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._thumb.setPixmap(scaled)


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
        wave_lbl.setFixedSize(_CW - 8, _TH)
        wave_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wave_lbl.setStyleSheet("border-radius:4px;border:none;")
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
        # Stop pending thumbnail threads
        for t in self._thumb_threads:
            t.quit()
        self._thumb_threads.clear()

        # Remove all cards from layout and delete
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        for data in self._all_items:
            if self._type == "video":
                card: MediaCard = VideoCard(
                    media_id=data["id"],
                    title=data.get("title", ""),
                    file_path=data.get("file_path", ""),
                    resolution=data.get("resolution", ""),
                    fps=data.get("fps"),
                )
                self._start_thumb_loader(card, data["file_path"])
            else:
                energy: list[float] = []
                ec = data.get("energy_curve")
                if ec:
                    try:
                        energy = json.loads(ec)
                    except (json.JSONDecodeError, ValueError) as exc:
                        logger.warning("_populate: failed to parse energy_curve JSON: %s", exc)
                card = AudioCard(
                    media_id=data["id"],
                    title=data.get("title", ""),
                    file_path=data.get("file_path", ""),
                    bpm=data.get("bpm"),
                    key=data.get("key"),
                    mood=data.get("mood"),
                    genre=data.get("genre"),
                    energy_data=energy,
                )

            card.clicked.connect(self._on_card_clicked)
            self._cards.append(card)

        self._filtered = list(self._cards)
        self._apply_filter()

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

        self._thumb_threads.append(thread)
        thread.start()

    def _apply_filter(self) -> None:
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

    def _relayout(self) -> None:
        """Place filtered cards into grid, hide the rest."""
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
        self._container.setMinimumHeight(rows * (_CH + _GAP) + 4)

    def _on_card_clicked(self, media_id: int) -> None:
        for card in self._cards:
            card.set_selected(card._id == media_id)
        self._selected_id = media_id
        self.item_selected.emit(media_id)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._relayout()
