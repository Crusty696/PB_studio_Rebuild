"""StructureTab — Studio Brain "Struktur" tab (T10.2a: Grid mode + filters).

Design §3 (Structure / Memory / Agent): the Struktur tab reads the clip-tag
enrichment produced by workers/structure_enrichment.py and presents the
scenes grouped by style bucket. Users can filter by role / mood / style
bucket / role-confidence / usage-count.

T10.2a scope (this file):
  - _FilterBar     (QComboBox×3 + QDoubleSpinBox + QSpinBox, debounced signal).
  - _GridView      (QScrollArea with one QGroupBox per style bucket and a
                    QGridLayout of _ClipCard widgets inside each group).
  - _ClipCard      (QFrame with placeholder pixmap + role/mood labels; emits
                    clicked(scene_id) on left-click).
  - StructureTab   (glue widget; exposes refresh / set_filters / current_cards
                    and a clipSelected(int) signal).

Deliberately out of scope (later dispatches):
  - Inspector panel  → T10.2b.
  - Stats panel      → T10.2c.
  - Graph mode       → T10.2d.
  - Boost/Exclude    → T10.2e.

Placeholders for those are rendered as plain "Not implemented yet" QLabels to
keep the layout informative without committing to speculative APIs.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import OperationalError

from services.brain_service import BrainService

logger = logging.getLogger(__name__)


# Card sizing — kept in sync with ui/widgets/media_grid.py look-and-feel.
_CARD_W = 162
_CARD_H = 112
_THUMB_H = 64
_GRID_GAP = 6


# ── Visual helpers ────────────────────────────────────────────────────────────


def _bucket_color(bucket_id: Optional[int]) -> QColor:
    """Deterministic pastel colour per bucket (used for placeholder thumbs)."""
    palette = [
        "#3b4252", "#4c566a", "#5e81ac", "#81a1c1",
        "#88c0d0", "#8fbcbb", "#a3be8c", "#b48ead",
        "#d08770", "#bf616a", "#ebcb8b",
    ]
    if bucket_id is None:
        return QColor("#2e3440")
    return QColor(palette[int(bucket_id) % len(palette)])


def _placeholder_thumb(scene_id: int, bucket_id: Optional[int]) -> QPixmap:
    """Flat-coloured QPixmap with the scene_id drawn in it — no ffmpeg.

    This keeps thumbnails cheap (no disk / process work) and the UI is safe
    to render in headless tests.
    """
    w = _CARD_W - 8
    h = _THUMB_H
    pix = QPixmap(w, h)
    pix.fill(_bucket_color(bucket_id))
    p = QPainter(pix)
    try:
        p.setPen(QColor("#e5e7eb"))
        p.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        p.drawText(
            QRect(0, 0, w, h),
            Qt.AlignmentFlag.AlignCenter,
            f"#{scene_id}",
        )
    finally:
        p.end()
    return pix


# ── Clip card ─────────────────────────────────────────────────────────────────


class _ClipCard(QFrame):
    """Single-scene card: placeholder thumb + scene_id + role + mood labels.

    Emits `clicked(scene_id)` on left mouse press. The outer StructureTab
    re-exposes this as its public `clipSelected(int)` signal.
    """

    clicked = Signal(int)

    def __init__(self, row: dict, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._row = dict(row)
        self._scene_id = int(row["scene_id"])
        self.setObjectName("StructureClipCard")
        self.setFixedSize(_CARD_W, _CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "QFrame#StructureClipCard{background:#131922;"
            "border:1px solid rgba(255,255,255,0.07);border-radius:6px;}"
            "QFrame#StructureClipCard:hover{"
            "border:1px solid rgba(212,164,74,0.45);background:#161d28;}"
        )
        self._build()

    def _build(self) -> None:
        vl = QVBoxLayout(self)
        vl.setContentsMargins(4, 4, 4, 4)
        vl.setSpacing(2)

        thumb = QLabel()
        thumb.setFixedSize(_CARD_W - 8, _THUMB_H)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setPixmap(
            _placeholder_thumb(self._scene_id, self._row.get("style_bucket_id"))
        )
        vl.addWidget(thumb)

        role = self._row.get("role") or "—"
        role_conf = float(self._row.get("role_confidence") or 0.0)
        mood = self._row.get("mood_refined") or "—"
        usage = int(self._row.get("usage_count") or 0)

        role_lbl = QLabel(f"{role}  ({role_conf:.2f})")
        role_lbl.setStyleSheet("color:#e5e7eb;font-size:9px;font-weight:600;")
        vl.addWidget(role_lbl)

        mood_lbl = QLabel(f"mood: {mood}")
        mood_lbl.setStyleSheet("color:#9ca3af;font-size:8px;")
        vl.addWidget(mood_lbl)

        usage_lbl = QLabel(f"used: {usage}×")
        usage_lbl.setStyleSheet("color:#6b7280;font-size:8px;")
        vl.addWidget(usage_lbl)

    @property
    def scene_id(self) -> int:
        return self._scene_id

    @property
    def row(self) -> dict:
        return dict(self._row)

    def mousePressEvent(self, event) -> None:  # noqa: N802 — Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._scene_id)
        super().mousePressEvent(event)


# ── Filter bar ────────────────────────────────────────────────────────────────


_FILTER_STYLE = (
    "QComboBox,QDoubleSpinBox,QSpinBox{background:#1a2030;"
    "border:1px solid rgba(255,255,255,0.1);border-radius:4px;"
    "color:#e5e7eb;padding:1px 5px;font-size:10px;}"
    "QLabel{color:#9ca3af;font-size:9px;}"
)


class _FilterBar(QWidget):
    """Row of controls mapped to BrainService.list_clips_with_tags kwargs.

    Emits `filtersChanged(dict)` whenever any control changes, debounced by
    150 ms so dropdown scrubbing doesn't thrash the DB.
    """

    filtersChanged = Signal(dict)

    def __init__(self, brain_service: BrainService, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._svc = brain_service
        self.setStyleSheet(_FILTER_STYLE)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(150)
        self._debounce.timeout.connect(self._fire)

        self._build()

    def _build(self) -> None:
        hl = QHBoxLayout(self)
        hl.setContentsMargins(4, 4, 4, 4)
        hl.setSpacing(8)

        # role
        hl.addWidget(QLabel("Role:"))
        self._role_combo = QComboBox()
        self._role_combo.addItem("(any)", userData=None)
        for role in self._safe_call(self._svc.list_distinct_roles, []):
            self._role_combo.addItem(role, userData=role)
        self._role_combo.currentIndexChanged.connect(self._schedule)
        hl.addWidget(self._role_combo)

        # mood
        hl.addWidget(QLabel("Mood:"))
        self._mood_combo = QComboBox()
        self._mood_combo.addItem("(any)", userData=None)
        for mood in self._safe_call(self._svc.list_distinct_moods, []):
            self._mood_combo.addItem(mood, userData=mood)
        self._mood_combo.currentIndexChanged.connect(self._schedule)
        hl.addWidget(self._mood_combo)

        # style bucket
        hl.addWidget(QLabel("Style:"))
        self._style_combo = QComboBox()
        self._style_combo.addItem("(any)", userData=None)
        for bucket in self._safe_call(self._svc.list_active_style_buckets, []):
            label = f"{bucket['name']}  ({bucket['member_count']})"
            self._style_combo.addItem(label, userData=int(bucket["id"]))
        self._style_combo.currentIndexChanged.connect(self._schedule)
        hl.addWidget(self._style_combo)

        # min role-confidence
        hl.addWidget(QLabel("Min conf:"))
        self._conf_spin = QDoubleSpinBox()
        self._conf_spin.setRange(0.0, 1.0)
        self._conf_spin.setSingleStep(0.05)
        self._conf_spin.setDecimals(2)
        self._conf_spin.setValue(0.0)
        self._conf_spin.valueChanged.connect(self._schedule)
        hl.addWidget(self._conf_spin)

        # min usage
        hl.addWidget(QLabel("Min usage:"))
        self._usage_spin = QSpinBox()
        self._usage_spin.setRange(0, 9999)
        self._usage_spin.setValue(0)
        self._usage_spin.valueChanged.connect(self._schedule)
        hl.addWidget(self._usage_spin)

        hl.addStretch()

    # ── public API ─────────────────────────────────────────────────────────
    def current_filters(self) -> dict:
        return {
            "role": self._role_combo.currentData(),
            "mood": self._mood_combo.currentData(),
            "style_bucket_id": self._style_combo.currentData(),
            "min_role_confidence": float(self._conf_spin.value()),
            "min_usage_count": int(self._usage_spin.value()),
        }

    def set_filters(self, filters: dict) -> None:
        """Apply filters programmatically. Signals are blocked during the
        update so consumers get exactly one `filtersChanged` notification."""
        widgets = (
            self._role_combo, self._mood_combo, self._style_combo,
            self._conf_spin, self._usage_spin,
        )
        for w in widgets:
            w.blockSignals(True)
        try:
            self._apply_combo(self._role_combo, filters.get("role"))
            self._apply_combo(self._mood_combo, filters.get("mood"))
            self._apply_combo(self._style_combo, filters.get("style_bucket_id"))
            self._conf_spin.setValue(float(filters.get("min_role_confidence", 0.0)))
            self._usage_spin.setValue(int(filters.get("min_usage_count", 0)))
        finally:
            for w in widgets:
                w.blockSignals(False)
        # Emit once, synchronously — tests rely on this.
        self._fire()

    @staticmethod
    def _apply_combo(combo: QComboBox, value) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(0)  # fall back to "(any)"

    # ── internal ───────────────────────────────────────────────────────────
    def _schedule(self, *_args) -> None:
        self._debounce.start()

    def _fire(self) -> None:
        self.filtersChanged.emit(self.current_filters())

    @staticmethod
    def _safe_call(fn, default):
        """Call a BrainService listing method; on missing-schema return `default`.

        Narrowed to sqlalchemy.exc.OperationalError so we only swallow the
        "table does not exist" case on fresh/unmigrated DBs. Everything else
        (SQL typos, misconfigured sessionmaker, bugs in the service) is
        re-raised so real failures surface loudly instead of presenting empty
        dropdowns.
        """
        try:
            return fn()
        except OperationalError as exc:
            logger.warning("FilterBar: listing call failed: %s", exc)
            return default


# ── Grid view ─────────────────────────────────────────────────────────────────


class _GridView(QScrollArea):
    """Scrollable container of bucket-grouped _ClipCard widgets.

    Each style bucket becomes one QGroupBox titled "<bucket_name> (<n>)" with
    the cards laid out in a responsive QGridLayout beneath.
    """

    cardClicked = Signal(int)  # scene_id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            "QWidget#struct_grid_container{background:transparent;}"
            "QGroupBox{color:#e5e7eb;font-size:11px;font-weight:600;"
            "border:1px solid rgba(255,255,255,0.08);border-radius:6px;"
            "margin-top:10px;padding:12px 6px 6px 6px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 4px;}"
        )

        self._container = QWidget()
        self._container.setObjectName("struct_grid_container")
        self._outer = QVBoxLayout(self._container)
        self._outer.setContentsMargins(6, 6, 6, 6)
        self._outer.setSpacing(8)

        self._empty_label = QLabel("No clips match the current filters.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color:#6b7280;font-size:11px;padding:24px;")
        self._empty_label.setVisible(False)
        self._outer.addWidget(self._empty_label)

        self._outer.addStretch()
        self.setWidget(self._container)

        self._cards: list[_ClipCard] = []
        self._rows: list[dict] = []

    # ── public API ─────────────────────────────────────────────────────────
    def current_rows(self) -> list[dict]:
        return [dict(r) for r in self._rows]

    def set_rows(self, rows: list[dict], cols: int = 4) -> None:
        """Replace the current grid with a freshly-built one."""
        self._clear()
        self._rows = [dict(r) for r in rows]

        if not rows:
            self._empty_label.setVisible(True)
            return
        self._empty_label.setVisible(False)

        # Group by (style_bucket_id, style_bucket_name); preserve upstream order.
        groups: list[tuple[Optional[int], Optional[str], list[dict]]] = []
        by_bucket: dict[Optional[int], list[dict]] = {}
        for row in rows:
            key = row.get("style_bucket_id")
            if key not in by_bucket:
                by_bucket[key] = []
                groups.append((key, row.get("style_bucket_name"), by_bucket[key]))
            by_bucket[key].append(row)

        # Insert groups above the stretch (which is always the last item).
        insert_idx = self._outer.count() - 1
        for bucket_id, bucket_name, bucket_rows in groups:
            title = self._format_bucket_title(bucket_id, bucket_name, len(bucket_rows))
            box = QGroupBox(title, self._container)
            gl = QGridLayout(box)
            gl.setContentsMargins(6, 6, 6, 6)
            gl.setHorizontalSpacing(_GRID_GAP)
            gl.setVerticalSpacing(_GRID_GAP)

            for i, row in enumerate(bucket_rows):
                r, c = divmod(i, cols)
                card = _ClipCard(row, box)
                card.clicked.connect(self.cardClicked)
                gl.addWidget(card, r, c)
                self._cards.append(card)

            self._outer.insertWidget(insert_idx, box)
            insert_idx += 1

    # ── internal ───────────────────────────────────────────────────────────
    @staticmethod
    def _format_bucket_title(
        bucket_id: Optional[int], bucket_name: Optional[str], count: int
    ) -> str:
        if bucket_name:
            return f"{bucket_name} ({count})"
        if bucket_id is not None:
            return f"Bucket #{bucket_id} ({count})"
        return f"Unassigned ({count})"

    def _clear(self) -> None:
        self._cards.clear()
        self._rows = []
        # Remove every group box; keep the empty_label + stretch sentinels.
        kept = {self._empty_label}
        to_remove: list[QWidget] = []
        for i in range(self._outer.count()):
            item = self._outer.itemAt(i)
            if item is None:
                continue
            w = item.widget()
            if w is None:
                continue
            if w in kept:
                continue
            to_remove.append(w)
        for w in to_remove:
            self._outer.removeWidget(w)
            w.setParent(None)
            w.deleteLater()


# ── Structure tab ─────────────────────────────────────────────────────────────


class StructureTab(QWidget):
    """Top-level widget placed at tab index 0 of StudioBrainWindow.

    Layout (T10.2a):

        +------------------------------------------------------------+
        | [Role v] [Mood v] [Style v] [min conf] [min usage]         |  _FilterBar
        +------------------------------------------------------------+
        | ┌ style-bucket-A (n) ┐                                      |  _GridView
        | │  [card][card][card][card]                                │
        | └────────────────────┘                                      |
        | ┌ style-bucket-B (n) ┐                                      |
        | │  [card][card]                                             |
        | └────────────────────┘                                      |
        +------------------------------------------------------------+
        | Inspector / Stats / Graph — coming in T10.2b/c/d           |  placeholder
        +------------------------------------------------------------+
    """

    clipSelected = Signal(int)  # scene_id

    def __init__(
        self,
        brain_service: BrainService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._svc = brain_service

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        self._filter_bar = _FilterBar(brain_service, self)
        self._filter_bar.filtersChanged.connect(self._on_filters_changed)
        outer.addWidget(self._filter_bar)

        self._grid = _GridView(self)
        self._grid.cardClicked.connect(self.clipSelected)
        outer.addWidget(self._grid, stretch=1)

        # Placeholder for inspector/stats/graph (future sub-tasks T10.2b-d).
        self._placeholder = QLabel(
            "Inspector / Stats / Graph — not implemented yet (T10.2b/c/d)."
        )
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setStyleSheet(
            "color:#6b7280;font-size:10px;padding:4px;"
            "border-top:1px solid rgba(255,255,255,0.05);"
        )
        outer.addWidget(self._placeholder)

        # Initial render.
        self.refresh()

    # ── public API ─────────────────────────────────────────────────────────
    def refresh(self) -> None:
        """Re-read BrainService with the current filter state and rebuild.

        Invalidates the BrainService per-instance lru_cache first so external
        DB mutations (e.g. a completed enrichment run) become visible without
        requiring a new service instance.
        """
        self._svc.invalidate()
        filters = self._filter_bar.current_filters()
        try:
            rows = self._svc.list_clips_with_tags(**filters)
        except OperationalError as exc:
            # Missing / unmigrated struct_* tables — keep the UI mountable.
            logger.warning("StructureTab.refresh: list_clips_with_tags failed: %s", exc)
            rows = []
        self._grid.set_rows(rows)

    def set_filters(self, filters: dict) -> None:
        """Programmatic filter setter with PATCH semantics.

        The provided `filters` dict is overlaid on top of the current filter
        state, so `set_filters({"role": "hero"})` changes only `role` and
        leaves mood / style / min_confidence / min_usage untouched.
        Triggers exactly one refresh() via _FilterBar.filtersChanged.
        """
        merged = self._filter_bar.current_filters() | dict(filters)
        # _FilterBar.set_filters fires filtersChanged synchronously, which
        # triggers _on_filters_changed → refresh(). So no explicit refresh
        # call needed here.
        self._filter_bar.set_filters(merged)

    def current_cards(self) -> list[dict]:
        """Return the row dicts currently rendered (post-filter)."""
        return self._grid.current_rows()

    # ── internal ───────────────────────────────────────────────────────────
    def _on_filters_changed(self, _filters: dict) -> None:
        self.refresh()
