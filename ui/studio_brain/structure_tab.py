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

T10.2b addition: an InspectorPanel (ui/studio_brain/inspector_panel.py) is
placed on the right side of the grid via QHBoxLayout (grid stretch=3,
inspector stretch=1). `clipSelected(int)` is wired to
`InspectorPanel.populate`.

T10.2d addition: a Grid/Graph mode toggle in the filter bar swaps the left
body between `_GridView` and `GraphView` via a `QStackedWidget`. If the
Graph view decides to fall back (scene_count > 2000), the tab auto-switches
back to Grid and shows a 5-second info banner.

Deliberately out of scope (later dispatches):
  - Boost/Exclude    → T10.2e.
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
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import OperationalError

from services.brain_service import BrainService
from ui.studio_brain.inspector_panel import InspectorPanel
from ui.studio_brain.stats_panel import StatsPanel

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

    Also hosts the Grid/Graph mode selector (T10.2d). Mode changes are
    surfaced as the separate `viewModeChanged(str)` signal — they do not
    trigger a grid refresh.
    """

    filtersChanged = Signal(dict)
    viewModeChanged = Signal(str)

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

        # view mode (leftmost — T10.2d)
        hl.addWidget(QLabel("View:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Grid", userData="Grid")
        self._mode_combo.addItem("Graph", userData="Graph")
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        hl.addWidget(self._mode_combo)

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
    def current_mode(self) -> str:
        return str(self._mode_combo.currentData() or "Grid")

    def set_mode(self, mode: str) -> None:
        """Programmatic setter; emits viewModeChanged exactly once."""
        target = mode if mode in ("Grid", "Graph") else "Grid"
        for i in range(self._mode_combo.count()):
            if self._mode_combo.itemData(i) == target:
                if self._mode_combo.currentIndex() == i:
                    # No index change → no currentIndexChanged. Fire manually
                    # so callers observe a consistent signal contract.
                    self.viewModeChanged.emit(target)
                else:
                    self._mode_combo.setCurrentIndex(i)
                return

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

    def _on_mode_changed(self, *_args) -> None:
        self.viewModeChanged.emit(self.current_mode())

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

    Layout (T10.2a + T10.2b + T10.2c + T10.2d):

        +------------------------------------------------------------+
        | [View v] [Role v] [Mood v] [Style v] [min conf] [min usage]|  _FilterBar
        +---------------------------------------+--------------------+
        | Grid OR Graph (QStackedWidget)        |  Inspector         |  stacked
        | ┌ style-bucket-A (n) ┐                |  (scene detail,    |  left +
        | │  [card][card][card][card]           |   neighbors,       |  right
        | └────────────────────┘                |   usage)           |  column.
        | ┌ style-bucket-B (n) ┐                +--------------------+
        | │  [card][card]                        |  Stats             |
        | └────────────────────┘                |  (counts, lacuna)  |
        +---------------------------------------+--------------------+

    When Graph mode is selected but ``GraphView.render_graph()`` returns
    ``False`` (scene_count > 2000, Feasibility §R5), the tab flips back to
    Grid and shows a dismissable info banner above the body.
    """

    clipSelected = Signal(int)  # scene_id

    def __init__(
        self,
        brain_service: BrainService,
        parent: Optional[QWidget] = None,
    ) -> None:
        # Lazy import avoids a circular import at module load (GraphView
        # reuses _bucket_color from this module).
        from ui.studio_brain.graph_view import GraphView

        super().__init__(parent)
        self._svc = brain_service

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        self._filter_bar = _FilterBar(brain_service, self)
        self._filter_bar.filtersChanged.connect(self._on_filters_changed)
        self._filter_bar.viewModeChanged.connect(self._on_view_mode_changed)
        outer.addWidget(self._filter_bar)

        # Fallback banner — hidden by default; visible for 5s after an
        # auto-fallback from Graph → Grid.
        self._fallback_banner = QLabel("")
        self._fallback_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._fallback_banner.setStyleSheet(
            "color:#f5c97b;font-size:10px;padding:4px;"
            "background:#2a1c0e;border:1px solid rgba(212,164,74,0.35);"
            "border-radius:4px;"
        )
        self._fallback_banner.setVisible(False)
        outer.addWidget(self._fallback_banner)

        self._fallback_timer = QTimer(self)
        self._fallback_timer.setSingleShot(True)
        self._fallback_timer.setInterval(5000)
        self._fallback_timer.timeout.connect(self._fallback_banner.hide)

        # Body: QStackedWidget (Grid @ index 0, Graph @ index 1) on the left
        # (stretch=3), right-side column (Inspector + Stats) on the right
        # (stretch=1).
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)

        self._grid = _GridView(self)
        self._grid.cardClicked.connect(self.clipSelected)

        self._graph = GraphView(brain_service, parent=self)
        self._graph.clipSelected.connect(self.clipSelected)
        self._graph.fellBackToGrid.connect(self._on_graph_fallback)

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._grid)   # index 0
        self._stack.addWidget(self._graph)  # index 1
        body.addWidget(self._stack, stretch=3)

        right_column = QWidget(self)
        right_layout = QVBoxLayout(right_column)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self._inspector = InspectorPanel(brain_service, parent=right_column)
        # External emitters of clipSelected (not just card clicks) also
        # populate the inspector.
        self.clipSelected.connect(self._inspector.populate)
        right_layout.addWidget(self._inspector, stretch=1)

        self._stats = StatsPanel(brain_service, parent=right_column)
        right_layout.addWidget(self._stats, stretch=1)

        body.addWidget(right_column, stretch=1)

        outer.addLayout(body, stretch=1)

        # Initial render.
        self.refresh()

    # ── public API ─────────────────────────────────────────────────────────
    def refresh(self) -> None:
        """Re-read BrainService with the current filter state and rebuild.

        Invalidates the BrainService per-instance lru_cache first so external
        DB mutations (e.g. a completed enrichment run) become visible without
        requiring a new service instance. The Stats panel is also refreshed
        so library-level counts stay in sync with background enrichment
        progress even though the stats themselves don't depend on filters.
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
        self._stats.refresh()

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

    def current_view_mode(self) -> str:
        """Return the currently-selected view mode: ``"Grid"`` or ``"Graph"``."""
        return self._filter_bar.current_mode()

    def set_view_mode(self, mode: str) -> None:
        """Programmatic equivalent of flipping the View combo-box."""
        self._filter_bar.set_mode(mode)

    # ── internal ───────────────────────────────────────────────────────────
    def _on_filters_changed(self, _filters: dict) -> None:
        self.refresh()

    def _on_view_mode_changed(self, mode: str) -> None:
        """Swap the stacked widget; render the graph lazily on first entry."""
        if mode == "Graph":
            self._stack.setCurrentIndex(1)
            try:
                rendered = self._graph.render_graph()
            except OperationalError as exc:
                logger.warning("GraphView.render_graph failed: %s", exc)
                rendered = False
            if not rendered:
                # Auto-switch back; the banner is populated from the
                # fellBackToGrid signal handler, not here, because the signal
                # carries the precise threshold info we want to show.
                self._stack.setCurrentIndex(0)
                # Revert the combo (block signals to avoid re-entering this
                # handler and double-refreshing).
                combo = self._filter_bar._mode_combo
                combo.blockSignals(True)
                try:
                    combo.setCurrentIndex(0)
                finally:
                    combo.blockSignals(False)
        else:
            self._stack.setCurrentIndex(0)
            # Leaving Graph mode hides the fallback banner immediately.
            self._fallback_banner.setVisible(False)
            self._fallback_timer.stop()

    def _on_graph_fallback(self, reason: str) -> None:
        """Handler for ``GraphView.fellBackToGrid(reason)``."""
        self._fallback_banner.setText(reason)
        self._fallback_banner.setVisible(True)
        self._fallback_timer.start()
