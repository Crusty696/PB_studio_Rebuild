"""StoryMapDialog — non-modal QDialog visualising a single pacing run (P12).

Design: this dialog is the user-facing "story map" for one mem_pacing_run —
it shows everything the agent saw when it cut the run, all in one view:

    HeaderBar          run id, audio basename, total duration, export buttons
    WaveformPanel      audio energy curve (only if energy_curve available)
    SectionStripPanel  song-structure regions (only for DJ-mix runs)
    TensionPanel       harmonic-tension snapshot per cut
    MoodStripPanel     mood-over-time as colored rectangles
    ClipStrip          horizontal scroll of clip-card thumbnails (one per cut)

Public API:
    __init__(brain_service, run_id, parent=None)
    data() -> dict | None
    export_png(path) -> Path
    export_svg(path) -> Path | None  (None if QSvgGenerator unavailable)
    Signal: thumbnailClicked(int scene_id, float at_timestamp_sec)

Zoom: Ctrl+Wheel zooms all four time-aligned plots together (waveform,
section, tension, mood). Plain wheel does nothing — accidental wheel
zoom in a non-modal dialog is jarring. The four plots share their
ViewBox X-axis range via pyqtgraph's ``setXLink``.

Triggers: opened from the Audit tab's "Story Map…" button (run-aware) and
from the Timeline's right-click context menu (uses most-recent run).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

import pyqtgraph as pg  # type: ignore[import-untyped]

from services.brain_service import BrainService

logger = logging.getLogger(__name__)


# ── Layout constants ─────────────────────────────────────────────────────────

_DIALOG_DEFAULT_W = 1100
_DIALOG_DEFAULT_H = 700

_WAVEFORM_HEIGHT = 100
_SECTION_HEIGHT = 60
_TENSION_HEIGHT = 100
_MOOD_HEIGHT = 40
_CARD_W = 110
_CARD_H = 130
_THUMB_W = 60
_THUMB_H = 60

_BG = "#0f141d"
_PANEL_BG = "#0f141d"

_HEADER_STYLE = (
    "QLabel{color:#e5e7eb;font-size:12px;font-weight:600;padding:4px 6px;}"
)
_BUTTON_STYLE = (
    "QPushButton{background:#1a2030;color:#e5e7eb;"
    "border:1px solid rgba(255,255,255,0.1);border-radius:4px;"
    "padding:4px 10px;font-size:10px;}"
    "QPushButton:hover{background:#243042;}"
)


# Stable mood→color palette. Mapping is closed over the lifetime of one
# dialog (and across sessions, since the keys are sorted alphabetically
# before we cycle the palette).
_MOOD_COLOR_PALETTE: tuple[tuple[int, int, int], ...] = (
    (90, 140, 220),    # blue
    (200, 90, 90),     # red
    (90, 180, 120),    # green
    (220, 170, 80),    # amber
    (170, 110, 200),   # purple
    (90, 200, 200),    # cyan
    (220, 130, 170),   # pink
    (160, 160, 80),    # olive
)


def _stable_mood_palette(moods: list[str]) -> dict[str, tuple[int, int, int]]:
    unique = sorted({str(m) for m in moods if m is not None})
    palette: dict[str, tuple[int, int, int]] = {}
    for idx, mood in enumerate(unique):
        palette[mood] = _MOOD_COLOR_PALETTE[idx % len(_MOOD_COLOR_PALETTE)]
    return palette


def _format_mmss(timestamp_sec: float) -> str:
    total = int(max(0.0, float(timestamp_sec)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ── _ClipCard ────────────────────────────────────────────────────────────────


class _ClipCard(QFrame):
    """One card in the clip-strip: scene id, role label, placeholder thumb,
    timestamp.

    Emits ``clicked(scene_id, at_timestamp_sec)`` on left-click. The dialog
    forwards via its ``thumbnailClicked`` signal so the surrounding window
    can react (StudioBrainWindow.timelineNavigationRequested).
    """

    clicked = Signal(int, float)

    def __init__(
        self,
        decision: dict[str, Any],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedSize(_CARD_W, _CARD_H)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            "QFrame{background:#131922;border:1px solid rgba(255,255,255,0.08);"
            "border-radius:4px;}"
            "QFrame:hover{border:1px solid rgba(232,204,106,0.4);}"
        )
        self._scene_id: Optional[int] = decision.get("scene_id")
        self._timestamp_sec: float = float(decision.get("at_timestamp_sec") or 0.0)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(2)

        scene_label = QLabel(
            f"#{self._scene_id}" if self._scene_id is not None else "—"
        )
        scene_label.setStyleSheet(
            "color:#e5e7eb;font-size:10px;font-weight:600;"
        )
        scene_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(scene_label)
        _role_text = str(decision.get("clip_role") or "—")
        self.setToolTip(
            f"Szene #{self._scene_id} — {_role_text} bei "
            f"{_format_mmss(self._timestamp_sec)}. "
            "Klick: springt zum Schnitt in der Timeline."
        )

        # Placeholder thumbnail — a flat colored rect. The real preview
        # render is a future polish item; today the card is a click target.
        thumb = QLabel(self)
        thumb.setFixedSize(_THUMB_W, _THUMB_H)
        thumb.setStyleSheet(
            "background:#243042;border-radius:3px;border:1px solid "
            "rgba(255,255,255,0.06);"
        )
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_row = QHBoxLayout()
        thumb_row.setContentsMargins(0, 0, 0, 0)
        thumb_row.addStretch()
        thumb_row.addWidget(thumb)
        thumb_row.addStretch()
        outer.addLayout(thumb_row)

        role_label = QLabel(str(decision.get("clip_role") or "—"))
        role_label.setStyleSheet("color:#9ca3af;font-size:9px;")
        role_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(role_label)

        ts_label = QLabel(_format_mmss(self._timestamp_sec))
        ts_label.setStyleSheet("color:#6b7280;font-size:9px;")
        ts_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(ts_label)

        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            scene_id = (
                int(self._scene_id) if self._scene_id is not None else -1
            )
            self.clicked.emit(scene_id, self._timestamp_sec)
            event.accept()
            return
        super().mousePressEvent(event)


# ── _HeaderBar ───────────────────────────────────────────────────────────────


class _HeaderBar(QWidget):
    """Top label + Export PNG / Export SVG / Close buttons."""

    exportPngClicked = Signal()
    exportSvgClicked = Signal()
    closeClicked = Signal()

    def __init__(
        self,
        run_id: int,
        audio_basename: str,
        total_duration_sec: float,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(8)

        title = (
            f"Story Map — Run #{int(run_id)} — {audio_basename or '(kein Audio)'}"
            f" — {_format_mmss(total_duration_sec)}"
        )
        self._label = QLabel(title)
        self._label.setStyleSheet(_HEADER_STYLE)
        self._label.setToolTip(
            "Story Map fuer diesen Run. Alle Panels teilen sich die "
            "Zeitachse: Ctrl+Mausrad zoomt synchron."
        )
        outer.addWidget(self._label, stretch=1)

        self._export_png_btn = QPushButton("Als PNG exportieren")
        self._export_png_btn.setStyleSheet(_BUTTON_STYLE)
        self._export_png_btn.setToolTip(
            "Rendert den gesamten Dialog-Inhalt als PNG-Datei. Praktisch "
            "fuer Screenshots / Diskussion mit Kollegen."
        )
        self._export_png_btn.clicked.connect(self.exportPngClicked.emit)
        outer.addWidget(self._export_png_btn)

        self._export_svg_btn = QPushButton("Als SVG exportieren")
        self._export_svg_btn.setStyleSheet(_BUTTON_STYLE)
        self._export_svg_btn.setToolTip(
            "Rendert als vektorielle SVG-Datei (nicht pixelig beim "
            "Zoomen). Fuer Druck oder Web."
        )
        self._export_svg_btn.clicked.connect(self.exportSvgClicked.emit)
        outer.addWidget(self._export_svg_btn)

        self._close_btn = QPushButton("Schließen")
        self._close_btn.setStyleSheet(_BUTTON_STYLE)
        self._close_btn.setToolTip(
            "Story-Map-Dialog schliessen und zur Studio-Brain-Ansicht zurueckkehren."
        )
        self._close_btn.clicked.connect(self.closeClicked.emit)
        outer.addWidget(self._close_btn)

    def label_text(self) -> str:
        return self._label.text()


# ── _TimePlot helper (a pyqtgraph PlotWidget that ignores plain wheel) ───────


class _TimePlot(pg.PlotWidget):  # type: ignore[misc]
    """PlotWidget that disables non-Ctrl wheel scroll.

    The dialog hooks Ctrl+Wheel at the dialog level (QDialog.wheelEvent) and
    forwards a controlled zoom to all linked plots. Plain wheel events would
    otherwise zoom one plot independently, breaking the linked-X invariant.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent=parent)
        self.setBackground(_BG)
        self.setMenuEnabled(False)
        self.hideButtons()
        # Allow programmatic X-axis zoom; lock Y so user can't accidentally
        # squash the curve.
        vb = self.getViewBox()
        if vb is not None:
            vb.setMouseEnabled(x=True, y=False)
        # We disable wheel here too — the dialog wheelEvent handler is the
        # single authoritative zoom path.
        self.wheelEvent = self._ignore_wheel

    def _ignore_wheel(self, event: Any) -> None:
        # Plain wheel does nothing; caller will route Ctrl+Wheel via
        # apply_zoom() on the dialog instead.
        event.ignore()


# ── StoryMapDialog ───────────────────────────────────────────────────────────


class StoryMapDialog(QDialog):
    """Non-modal dialog rendering one pacing-run as a Story Map (P12)."""

    thumbnailClicked = Signal(int, float)  # (scene_id, timestamp_sec)

    def __init__(
        self,
        brain_service: BrainService,
        run_id: int,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setModal(False)
        self.setWindowTitle(f"Story Map — Run #{int(run_id)}")
        self.resize(_DIALOG_DEFAULT_W, _DIALOG_DEFAULT_H)
        self.setStyleSheet(f"QDialog{{background:{_BG};}}")

        self._svc = brain_service
        self._run_id = int(run_id)
        self._data: Optional[dict[str, Any]] = None
        self._clip_cards: list[_ClipCard] = []
        self._linked_plots: list[_TimePlot] = []

        # Fetch data up-front; the dialog's contents are static for the
        # lifetime of one open instance (re-open to refresh).
        try:
            self._data = self._svc.story_map_data(self._run_id)
        except Exception as exc:
            logger.warning(
                "StoryMapDialog: story_map_data(%d) failed: %s",
                self._run_id,
                exc,
            )
            self._data = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        # Header bar
        run_dict = (self._data or {}).get("run") or {}
        audio = (self._data or {}).get("audio_track") or {}
        self._header = _HeaderBar(
            run_id=self._run_id,
            audio_basename=audio.get("file_basename", ""),
            total_duration_sec=float(run_dict.get("total_duration_sec", 0.0)),
            parent=self,
        )
        self._header.exportPngClicked.connect(self._on_export_png_clicked)
        self._header.exportSvgClicked.connect(self._on_export_svg_clicked)
        self._header.closeClicked.connect(self.close)
        outer.addWidget(self._header)

        # Splitter holding the four time-aligned plots, then the clip strip.
        self._splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._splitter.setStyleSheet(
            "QSplitter::handle{background:#1a2030;height:2px;}"
        )

        self._waveform_panel = self._build_waveform_panel()
        self._splitter.addWidget(self._waveform_panel)
        self._section_panel = self._build_section_panel()
        self._splitter.addWidget(self._section_panel)
        self._tension_panel = self._build_tension_panel()
        self._splitter.addWidget(self._tension_panel)
        self._mood_panel = self._build_mood_panel()
        self._splitter.addWidget(self._mood_panel)
        self._clip_strip = self._build_clip_strip()
        self._splitter.addWidget(self._clip_strip)

        # Reasonable initial sizes (in proportion to fixed heights).
        self._splitter.setSizes(
            [
                _WAVEFORM_HEIGHT,
                _SECTION_HEIGHT,
                _TENSION_HEIGHT,
                _MOOD_HEIGHT,
                _CARD_H + 30,
            ]
        )

        outer.addWidget(self._splitter, stretch=1)

        # Visibility toggles for empty/non-DJ-mix cases.
        if not (self._data or {}).get("waveform_energy"):
            self._waveform_panel.setVisible(False)
        if not run_dict.get("is_dj_mix"):
            self._section_panel.setVisible(False)

        # Link the X-axis ranges of all (visible) time plots so Ctrl+Wheel
        # zoom is coherent.
        for p in self._linked_plots[1:]:
            p.setXLink(self._linked_plots[0])

    # ── Public API ─────────────────────────────────────────────────────────
    def data(self) -> Optional[dict[str, Any]]:
        """Return the cached story_map_data dict (or None if missing)."""
        return self._data

    def export_png(self, path: str | Path) -> Path:
        """Rasterise the entire dialog into a PNG file."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        pixmap = self.grab()
        ok = bool(pixmap.save(str(out), "PNG"))
        if not ok:  # pragma: no cover — defensive
            logger.warning("StoryMapDialog.export_png: save() returned False")
        return out

    def export_svg(self, path: str | Path) -> Optional[Path]:
        """Render the dialog into an SVG file via QSvgGenerator + QPainter.

        Returns the written ``Path`` on success, or ``None`` if the QtSvg
        module is not available in this Qt build (we log a warning and let the
        caller decide what to do).
        """
        try:
            from PySide6.QtSvg import QSvgGenerator
        except ImportError:  # pragma: no cover — depends on Qt build
            logger.warning(
                "StoryMapDialog.export_svg: QtSvg not available; skipping."
            )
            return None
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        gen = QSvgGenerator()
        gen.setFileName(str(out))
        size = self.size()
        # QSvgGenerator wants a QSize for the viewport, plus a title/desc.
        gen.setSize(size)
        gen.setViewBox(self.rect())
        gen.setTitle(f"Story Map — Run #{self._run_id}")
        gen.setDescription("Generated by PB Studio Studio Brain (P12).")
        painter = QPainter()
        try:
            if not painter.begin(gen):  # pragma: no cover — defensive
                logger.warning(
                    "StoryMapDialog.export_svg: QPainter.begin() failed"
                )
                return None
            # QWidget.render(QPainter) requires the targetOffset argument
            # in PySide6 — pass a zero offset to render at (0,0).
            self.render(painter, QPoint(0, 0))
        finally:
            if painter.isActive():
                painter.end()
        return out

    # ── Wheel handling (Ctrl+Wheel zooms; plain wheel ignored) ────────────
    def wheelEvent(self, event: Any) -> None:
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                event.ignore()
                return
            # Zoom factor: scroll-up zooms in (factor < 1), down zooms out.
            factor = 0.8 if delta > 0 else 1.25
            self.apply_zoom(factor)
            event.accept()
            return
        # Plain wheel: do nothing (tests and contract say so).
        event.ignore()

    def apply_zoom(self, factor: float) -> None:
        """Scale the X-range of all linked time plots about the centre.

        ``factor < 1`` zooms in, ``factor > 1`` zooms out. Linked plots share
        the X-axis via setXLink, so updating the master view propagates.
        """
        if not self._linked_plots:
            return
        master = self._linked_plots[0]
        vb = master.getViewBox()
        if vb is None:
            return
        x_range = vb.viewRange()[0]
        if not x_range or len(x_range) != 2:
            return
        x0, x1 = float(x_range[0]), float(x_range[1])
        if x1 <= x0:
            return
        centre = (x0 + x1) / 2.0
        half = (x1 - x0) / 2.0 * float(factor)
        new_x0 = centre - half
        new_x1 = centre + half
        vb.setXRange(new_x0, new_x1, padding=0)

    # ── Panel builders ─────────────────────────────────────────────────────
    def _build_waveform_panel(self) -> _TimePlot:
        plot = _TimePlot(self)
        plot.setMinimumHeight(_WAVEFORM_HEIGHT)
        plot.setToolTip(
            "Energie-Kurve des Audio-Tracks. Hohe Ausschlaege = laute "
            "Stellen (Drops)."
        )
        plot.getPlotItem().setTitle(
            "Waveform", color="#9ca3af", size="9pt"
        )
        plot.getPlotItem().getAxis("left").setTextPen("#6b7280")
        plot.getPlotItem().getAxis("bottom").setTextPen("#6b7280")
        wf = (self._data or {}).get("waveform_energy") or []
        if wf:
            xs = [float(p["time_sec"]) for p in wf]
            ys = [float(p["energy"]) for p in wf]
            plot.plot(xs, ys, pen=pg.mkPen(color=(80, 140, 220), width=1.5))
            x_max = max(xs) if xs else 1.0
            plot.setXRange(0.0, max(1.0, x_max), padding=0)
        self._linked_plots.append(plot)
        return plot

    def _build_section_panel(self) -> _TimePlot:
        plot = _TimePlot(self)
        plot.setMinimumHeight(_SECTION_HEIGHT)
        plot.setToolTip(
            "Erkannte Song-Abschnitte als farbige Baender. Nur bei "
            "DJ-Mix-Runs sichtbar."
        )
        plot.getPlotItem().getAxis("left").setStyle(showValues=False)
        plot.getPlotItem().getAxis("left").setTextPen("#6b7280")
        plot.getPlotItem().getAxis("bottom").setTextPen("#6b7280")
        plot.setYRange(0, 1, padding=0)
        segments = (self._data or {}).get("structure_segments") or []
        run = (self._data or {}).get("run") or {}
        total_dur = float(run.get("total_duration_sec") or 0.0)
        x_max = total_dur
        if segments:
            x_max = max(x_max, max(float(s["end_sec"]) for s in segments), 1.0)
            colors = [
                (70, 120, 200, 140),
                (200, 120, 70, 140),
                (120, 200, 120, 140),
                (200, 70, 120, 140),
                (200, 200, 70, 140),
            ]
            for idx, seg in enumerate(segments):
                start = float(seg["start_sec"])
                end = float(seg["end_sec"])
                color = colors[idx % len(colors)]
                region = pg.LinearRegionItem(
                    values=(start, end),
                    orientation="vertical",
                    brush=pg.mkBrush(*color),
                    pen=pg.mkPen(color=(255, 255, 255, 60), width=1),
                    movable=False,
                )
                plot.addItem(region)
                label = str(seg.get("label") or "")
                if label:
                    text_item = pg.TextItem(
                        text=label, color="#e5e7eb", anchor=(0.5, 0.5)
                    )
                    text_item.setPos((start + end) / 2.0, 0.5)
                    plot.addItem(text_item)
        plot.setXRange(0.0, max(1.0, x_max), padding=0)
        self._linked_plots.append(plot)
        return plot

    def _build_tension_panel(self) -> _TimePlot:
        plot = _TimePlot(self)
        plot.setMinimumHeight(_TENSION_HEIGHT)
        plot.setToolTip(
            "Harmonic-Tension-Kurve an den Schnittzeitpunkten. Hoehere "
            "Spannung = harmonisch instabiler (Spannungsaufbau)."
        )
        plot.getPlotItem().setTitle(
            "Harmonische Spannung", color="#9ca3af", size="9pt"
        )
        plot.getPlotItem().getAxis("left").setTextPen("#6b7280")
        plot.getPlotItem().getAxis("bottom").setTextPen("#6b7280")
        tension = (self._data or {}).get("tension_curve") or []
        if tension:
            xs = [float(p["time_sec"]) for p in tension]
            ys = [float(p["value"]) for p in tension]
            plot.plot(
                xs,
                ys,
                pen=pg.mkPen(color=(220, 170, 80), width=1.8),
                symbol="o",
                symbolSize=4,
                symbolBrush=(220, 170, 80, 200),
            )
            x_max = max(xs) if xs else 1.0
            plot.setXRange(0.0, max(1.0, x_max), padding=0)
            plot.setYRange(0.0, max(1.0, max(ys)), padding=0)
        else:
            plot.setXRange(0.0, 1.0, padding=0)
            plot.setYRange(0.0, 1.0, padding=0)
        self._linked_plots.append(plot)
        return plot

    def _build_mood_panel(self) -> _TimePlot:
        plot = _TimePlot(self)
        plot.setMinimumHeight(_MOOD_HEIGHT)
        plot.setToolTip(
            "Video-Stimmung der gewaehlten Clips im zeitlichen Verlauf. "
            "Jede Farbe = eine andere Stimmung."
        )
        plot.getPlotItem().getAxis("left").setStyle(showValues=False)
        plot.getPlotItem().getAxis("left").setTextPen("#6b7280")
        plot.getPlotItem().getAxis("bottom").setTextPen("#6b7280")
        plot.setYRange(0, 1, padding=0)
        mood_curve = (self._data or {}).get("mood_curve") or []
        run = (self._data or {}).get("run") or {}
        total_dur = float(run.get("total_duration_sec") or 0.0)
        x_max = max(total_dur, 1.0)
        if mood_curve:
            palette = _stable_mood_palette(
                [p["mood"] for p in mood_curve]
            )
            xs = [float(p["time_sec"]) for p in mood_curve]
            x_max = max(x_max, max(xs))
            # Render rectangles spanning each mood segment up to the next
            # transition (or end of timeline).
            for i, point in enumerate(mood_curve):
                start = float(point["time_sec"])
                end = float(mood_curve[i + 1]["time_sec"]) if i + 1 < len(mood_curve) else x_max
                if end <= start:
                    end = start + 1.0
                color = palette.get(str(point["mood"]), (120, 120, 120))
                region = pg.LinearRegionItem(
                    values=(start, end),
                    orientation="vertical",
                    brush=pg.mkBrush(color[0], color[1], color[2], 180),
                    pen=pg.mkPen(color=(255, 255, 255, 40), width=1),
                    movable=False,
                )
                plot.addItem(region)
        plot.setXRange(0.0, max(1.0, x_max), padding=0)
        self._linked_plots.append(plot)
        return plot

    def _build_clip_strip(self) -> QScrollArea:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setToolTip(
            "Die gewaehlten Clips in Schnitt-Reihenfolge. Klick auf eine "
            "Karte -> Signal 'thumbnailClicked' (wird spaeter mit der "
            "Timeline verknuepft)."
        )
        scroll.setStyleSheet(
            "QScrollArea{background:#0a0d12;border:1px solid "
            "rgba(255,255,255,0.06);border-radius:4px;}"
        )
        host = QWidget(scroll)
        host.setStyleSheet("background:#0a0d12;")
        hl = QHBoxLayout(host)
        hl.setContentsMargins(6, 6, 6, 6)
        hl.setSpacing(6)
        decisions = (self._data or {}).get("decisions") or []
        for decision in decisions:
            card = _ClipCard(decision, parent=host)
            card.clicked.connect(self._on_card_clicked)
            self._clip_cards.append(card)
            hl.addWidget(card)
        hl.addStretch()
        scroll.setWidget(host)
        scroll.setMinimumHeight(_CARD_H + 24)
        return scroll

    # ── Internal slots ─────────────────────────────────────────────────────
    def _on_card_clicked(self, scene_id: int, at_timestamp_sec: float) -> None:
        try:
            sid = int(scene_id)
            ts = float(at_timestamp_sec)
        except (TypeError, ValueError):
            return
        self.thumbnailClicked.emit(sid, ts)

    def _on_export_png_clicked(self) -> None:  # pragma: no cover — UI glue
        from PySide6.QtWidgets import QFileDialog

        target, _ = QFileDialog.getSaveFileName(
            self, "Story Map als PNG exportieren", "", "PNG-Bild (*.png)"
        )
        if target:
            self.export_png(target)

    def _on_export_svg_clicked(self) -> None:  # pragma: no cover — UI glue
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        target, _ = QFileDialog.getSaveFileName(
            self, "Story Map als SVG exportieren", "", "SVG-Bild (*.svg)"
        )
        if not target:
            return
        result = self.export_svg(target)
        if result is None:
            QMessageBox.information(
                self,
                "SVG-Export nicht verfügbar",
                "QtSvg ist in diesem Qt-Build nicht verfügbar.",
            )
