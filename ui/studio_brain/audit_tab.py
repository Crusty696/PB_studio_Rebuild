"""AuditTab — Studio Brain "Audit" tab (T11.2).

Design §3 (Structure / Memory / Agent): the Audit tab is the decision-replay
surface — every cut the pacing agent made in a run is shown with its
context, its soft-score contributions, the near-miss alternatives, and the
budget state at the moment of the cut.

T11.2 scope (this file):
  - _RunSelector       Top bar: QComboBox listing completed runs.
                        Emits ``runChanged(run_id)`` on user or programmatic
                        selection.
  - _SegmentStrip      Visible only when the selected run is a DJ-mix.
                        Renders horizontal bands for ``structure_segments``
                        via pyqtgraph (LinearRegionItem + TextItem labels).
  - _CutTable          QTableWidget with the per-cut summary. Two filter
                        checkboxes above: "rejected only", "fallback only".
                        Emits ``cutSelected(decision_id)`` on row selection.
  - _TermContributions pyqtgraph horizontal bar chart of the chosen cut's
                        ``agent_rationale.contribs`` dict.
  - _Alternatives      QListWidget of at most three near-miss alternatives
                        derived from the rationale's stage_results.
  - _BudgetState       QFormLayout of the rationale's ``budget_state`` dict
                        (iterating whatever keys exist — no hard-coded list).
  - AuditTab           Glue widget; exposes ``select_run(run_id)`` so
                        ``MemoryTab.runSelected`` can route into this tab.

Public signals:
  - ``cutSelected(int)`` — emitted on row-selection in the cut table. The
                           P12 Story-Map dialog will consume this to open
                           the selected cut in context; for now there is no
                           internal listener beyond the local details panel.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import OperationalError

import pyqtgraph as pg

from services.brain_service import BrainService

logger = logging.getLogger(__name__)


# ── Layout / style constants ──────────────────────────────────────────────────

_SEGMENT_STRIP_HEIGHT = 80
_TERM_CHART_HEIGHT = 220
_EMPTY_TERMS_TEXT = "Select a cut to see term contributions."
_EMPTY_ALTS_TEXT = "Select a cut to see alternatives."
_EMPTY_BUDGET_TEXT = "—"

_SELECTOR_STYLE = (
    "QComboBox,QCheckBox{background:#1a2030;color:#e5e7eb;"
    "border:1px solid rgba(255,255,255,0.1);border-radius:4px;"
    "padding:3px 8px;font-size:10px;}"
    "QLabel{color:#9ca3af;font-size:10px;}"
)

_TABLE_STYLE = (
    "QTableWidget{background:#0f141d;color:#e5e7eb;font-size:10px;"
    "border:1px solid rgba(255,255,255,0.06);border-radius:4px;"
    "gridline-color:rgba(255,255,255,0.05);}"
    "QHeaderView::section{background:#131922;color:#9ca3af;"
    "border:none;padding:4px 6px;font-size:10px;font-weight:600;}"
)

_LIST_STYLE = (
    "QListWidget{background:#0f141d;color:#e5e7eb;font-size:10px;"
    "border:1px solid rgba(255,255,255,0.06);border-radius:4px;}"
)

_HEADER_LABEL_STYLE = (
    "color:#e5e7eb;font-size:10px;font-weight:600;padding:4px 0px;"
)

_EMPTY_LABEL_STYLE = "color:#6b7280;font-size:10px;padding:6px;"


# ── Formatting helpers ───────────────────────────────────────────────────────


def _format_mmss(timestamp_sec: float) -> str:
    """Render a timestamp in seconds as ``mm:ss`` (or ``hh:mm:ss`` if >= 1h).

    The cut table shows relative cut times within a run; hours-long DJ-mixes
    need the 3-field format so tests and eyeballs don't get confused at
    minute-60.
    """
    total = int(max(0.0, float(timestamp_sec)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _format_run_option(run: dict) -> str:
    """Compact label for a run entry in the selector combobox."""
    ts = run.get("started_at") or ""
    # Keep it short for the dropdown: #id + timestamp + cuts
    cuts = int(run.get("total_cuts") or 0)
    dj_flag = " [DJ]" if run.get("is_dj_mix") else ""
    return f"#{int(run['id'])}  {ts}  ({cuts} cuts){dj_flag}"


# ── _RunSelector ─────────────────────────────────────────────────────────────


class _RunSelector(QWidget):
    """Top bar: a label + QComboBox of completed runs."""

    runChanged = Signal(int)  # run_id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_SELECTOR_STYLE)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)

        hl.addWidget(QLabel("Run:"))
        self._combo = QComboBox(self)
        self._combo.setMinimumWidth(320)
        self._combo.currentIndexChanged.connect(self._emit_current)
        hl.addWidget(self._combo, stretch=1)
        hl.addStretch()

        self._runs: list[dict] = []

    def set_runs(self, runs: list[dict]) -> None:
        """Populate the combobox with completed runs. Prev selection preserved
        if still present; otherwise the newest run is selected."""
        self._runs = [dict(r) for r in runs]
        previous = self.current_run_id()

        self._combo.blockSignals(True)
        try:
            self._combo.clear()
            if not self._runs:
                self._combo.addItem("(no completed runs)", userData=None)
                self._combo.setEnabled(False)
            else:
                self._combo.setEnabled(True)
                for run in self._runs:
                    self._combo.addItem(
                        _format_run_option(run), userData=int(run["id"])
                    )
                # Restore previous selection if possible, else index 0 (newest).
                if previous is not None:
                    for i in range(self._combo.count()):
                        if self._combo.itemData(i) == previous:
                            self._combo.setCurrentIndex(i)
                            break
                    else:
                        self._combo.setCurrentIndex(0)
                else:
                    self._combo.setCurrentIndex(0)
        finally:
            self._combo.blockSignals(False)

        self._emit_current()

    def current_run_id(self) -> Optional[int]:
        data = self._combo.currentData()
        if data is None:
            return None
        try:
            return int(data)
        except (TypeError, ValueError):
            return None

    def current_run(self) -> Optional[dict]:
        rid = self.current_run_id()
        if rid is None:
            return None
        return next((r for r in self._runs if int(r["id"]) == rid), None)

    def select_run_id(self, run_id: int) -> bool:
        """Programmatically select ``run_id``. Returns True if it was in the
        list (and hence selected), False otherwise."""
        for i in range(self._combo.count()):
            if self._combo.itemData(i) == int(run_id):
                if self._combo.currentIndex() != i:
                    self._combo.setCurrentIndex(i)
                else:
                    # Same index already — force a re-emit so subscribers
                    # reliably re-render even after a refresh().
                    self._emit_current()
                return True
        return False

    def run_count(self) -> int:
        return len(self._runs)

    def _emit_current(self, *_args) -> None:
        rid = self.current_run_id()
        if rid is not None:
            self.runChanged.emit(rid)


# ── _SegmentStrip ────────────────────────────────────────────────────────────


class _SegmentStrip(QFrame):
    """pyqtgraph strip showing ``structure_segments`` horizontally.

    Only materialised when the selected run is a DJ-mix (``is_dj_mix=True``);
    AuditTab calls ``setVisible(False)`` otherwise — see
    ``test_audit_tab_segment_strip_hidden_for_non_dj_mix``.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(_SEGMENT_STRIP_HEIGHT)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("background:#0f141d;border-radius:4px;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(0)

        self._plot = pg.PlotWidget(self)
        self._plot.setBackground("#0f141d")
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.hideButtons()
        self._plot.setMenuEnabled(False)
        self._plot.getPlotItem().hideAxis("left")
        self._plot.getPlotItem().showAxis("bottom")
        self._plot.getPlotItem().getAxis("bottom").setTextPen("#9ca3af")
        self._plot.setYRange(0, 1, padding=0)
        outer.addWidget(self._plot)

        self._segment_count: int = 0

    def set_segments(self, segments: list[dict], total_duration_sec: float) -> None:
        """Render one region per segment across the horizontal axis."""
        self._plot.clear()
        self._segment_count = len(segments)

        if not segments:
            self._plot.setXRange(0, max(1.0, total_duration_sec), padding=0)
            return

        xmax = max(total_duration_sec, max(float(s["end_sec"]) for s in segments), 1.0)
        self._plot.setXRange(0, xmax, padding=0)

        # Deterministic tint cycle — keeps the strip readable without
        # depending on a global palette import.
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
            self._plot.addItem(region)

            # Label in the centre of the segment.
            label = str(seg.get("label") or "")
            if label:
                text_item = pg.TextItem(
                    text=label,
                    color="#e5e7eb",
                    anchor=(0.5, 0.5),
                )
                mid_x = (start + end) / 2.0
                text_item.setPos(mid_x, 0.5)
                self._plot.addItem(text_item)

    def segment_count(self) -> int:
        return self._segment_count


# ── _CutTable ────────────────────────────────────────────────────────────────


_CUT_COLUMNS: tuple[tuple[str, int], ...] = (
    ("#", 48),
    ("Time", 72),
    ("Section", 100),
    ("Scene", 160),
    ("Role", 80),
    ("Score", 72),
    ("Verdict", 80),
)


class _CutTable(QWidget):
    """Per-cut summary table with two filter checkboxes on top."""

    cutSelected = Signal(int)  # decision_id
    filterChanged = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        filter_row = QWidget(self)
        filter_row.setStyleSheet(_SELECTOR_STYLE)
        hl = QHBoxLayout(filter_row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)

        self._rejected_chk = QCheckBox("rejected only")
        self._rejected_chk.stateChanged.connect(self._emit_filter)
        hl.addWidget(self._rejected_chk)

        self._fallback_chk = QCheckBox("fallback only")
        self._fallback_chk.stateChanged.connect(self._emit_filter)
        hl.addWidget(self._fallback_chk)
        hl.addStretch()
        outer.addWidget(filter_row)

        self._table = QTableWidget(0, len(_CUT_COLUMNS), self)
        self._table.setHorizontalHeaderLabels([c[0] for c in _CUT_COLUMNS])
        for idx, (_label, width) in enumerate(_CUT_COLUMNS):
            self._table.setColumnWidth(idx, width)
        self._table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setStyleSheet(_TABLE_STYLE)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        outer.addWidget(self._table, stretch=1)

    # ── Public API ─────────────────────────────────────────────────────────
    def set_cuts(self, cuts: list[dict]) -> None:
        self._table.setRowCount(0)
        self._table.setRowCount(len(cuts))
        for row, cut in enumerate(cuts):
            seq = int(cut.get("sequence_idx") or 0)
            ts = float(cut.get("at_timestamp_sec") or 0.0)
            section = cut.get("at_section_type") or "—"
            scene_label = cut.get("scene_filename") or (
                f"scene_{cut['scene_id']}"
                if cut.get("scene_id") is not None
                else "—"
            )
            role = cut.get("clip_role") or "—"
            score = float(cut.get("agent_score") or 0.0)
            verdict = cut.get("user_verdict") or "—"

            self._table.setItem(row, 0, QTableWidgetItem(str(seq)))
            self._table.setItem(row, 1, QTableWidgetItem(_format_mmss(ts)))
            self._table.setItem(row, 2, QTableWidgetItem(str(section)))
            self._table.setItem(row, 3, QTableWidgetItem(str(scene_label)))
            self._table.setItem(row, 4, QTableWidgetItem(str(role)))
            self._table.setItem(row, 5, QTableWidgetItem(f"{score:.2f}"))
            self._table.setItem(row, 6, QTableWidgetItem(str(verdict)))

            # Stash decision_id in column 0 for selection recovery.
            id_item = self._table.item(row, 0)
            if id_item is not None:
                id_item.setData(Qt.ItemDataRole.UserRole, int(cut["id"]))

    def current_filter(self) -> dict:
        return {
            "rejected_only": bool(self._rejected_chk.isChecked()),
            "fallback_only": bool(self._fallback_chk.isChecked()),
        }

    def current_decision_id(self) -> Optional[int]:
        sel = self._table.selectionModel()
        if sel is None:
            return None
        rows = sel.selectedRows()
        if not rows:
            return None
        item = self._table.item(rows[0].row(), 0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        try:
            return int(data) if data is not None else None
        except (TypeError, ValueError):
            return None

    def row_count(self) -> int:
        return self._table.rowCount()

    def select_row(self, row: int) -> None:
        if 0 <= row < self._table.rowCount():
            self._table.selectRow(row)

    def set_filter(self, *, rejected_only: bool = False, fallback_only: bool = False) -> None:
        # Set state without triggering the normal filterChanged cascade; the
        # caller (AuditTab) is expected to refresh separately.
        self._rejected_chk.blockSignals(True)
        self._fallback_chk.blockSignals(True)
        try:
            self._rejected_chk.setChecked(bool(rejected_only))
            self._fallback_chk.setChecked(bool(fallback_only))
        finally:
            self._rejected_chk.blockSignals(False)
            self._fallback_chk.blockSignals(False)

    # ── Internal ───────────────────────────────────────────────────────────
    def _on_selection_changed(self) -> None:
        did = self.current_decision_id()
        if did is not None:
            self.cutSelected.emit(did)

    def _emit_filter(self, *_args) -> None:
        self.filterChanged.emit(self.current_filter())


# ── _TermContributions ───────────────────────────────────────────────────────


class _TermContributions(QFrame):
    """Horizontal bar chart of the rationale ``contribs`` dict.

    Bars sorted by absolute value (largest impact on top). The ``_bar_count``
    accessor stashed on the widget is a test-only hook so
    ``test_audit_tab_cut_selection_populates_details`` can assert bar count
    without navigating pyqtgraph's internal item list.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("background:#0f141d;border-radius:4px;")
        self.setMinimumHeight(_TERM_CHART_HEIGHT)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(2)

        self._header = QLabel("Term contributions")
        self._header.setStyleSheet(_HEADER_LABEL_STYLE)
        outer.addWidget(self._header)

        self._empty_label = QLabel(_EMPTY_TERMS_TEXT)
        self._empty_label.setStyleSheet(_EMPTY_LABEL_STYLE)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self._empty_label)

        self._plot = pg.PlotWidget(self)
        self._plot.setBackground("#0f141d")
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.hideButtons()
        self._plot.setMenuEnabled(False)
        self._plot.getPlotItem().getAxis("left").setTextPen("#9ca3af")
        self._plot.getPlotItem().getAxis("bottom").setTextPen("#9ca3af")
        self._plot.setVisible(False)
        outer.addWidget(self._plot, stretch=1)

        # Test-only accessor (see class docstring).
        self._bar_count: int = 0

    def clear(self) -> None:
        self._plot.clear()
        self._plot.setVisible(False)
        self._empty_label.setVisible(True)
        self._bar_count = 0

    def set_terms(self, terms: dict[str, float]) -> None:
        if not terms:
            self.clear()
            return

        items = sorted(terms.items(), key=lambda kv: abs(float(kv[1])), reverse=True)
        labels = [k for k, _ in items]
        values = [float(v) for _, v in items]
        n = len(values)

        self._plot.clear()
        y_positions = list(range(n))
        # Colour negative contributions red, positive blue — subtle cue only.
        brushes = [
            pg.mkBrush(200, 80, 80, 210) if v < 0 else pg.mkBrush(80, 140, 200, 210)
            for v in values
        ]
        bar = pg.BarGraphItem(
            x0=[0] * n,
            y=y_positions,
            height=0.7,
            width=values,
            brushes=brushes,
            pen=pg.mkPen(color=(255, 255, 255, 40)),
        )
        self._plot.addItem(bar)

        # Y-axis label mapping: bottom → top sorted by impact (top row most
        # impactful). We invert the Y range so index 0 renders on top.
        ticks = [list(zip(y_positions, labels))]
        self._plot.getPlotItem().getAxis("left").setTicks(ticks)
        self._plot.setYRange(-0.5, n - 0.5, padding=0)
        self._plot.getPlotItem().invertY(True)

        # Xrange padded symmetrically around 0 so negative bars are visible.
        max_abs = max(abs(v) for v in values) or 1.0
        self._plot.setXRange(-max_abs * 1.1, max_abs * 1.1, padding=0)

        self._plot.setVisible(True)
        self._empty_label.setVisible(False)
        self._bar_count = n


# ── _Alternatives ────────────────────────────────────────────────────────────


class _Alternatives(QFrame):
    """QListWidget of up to three near-miss alternatives."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("background:#0f141d;border-radius:4px;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(2)

        self._header = QLabel("Alternatives (top 3)")
        self._header.setStyleSheet(_HEADER_LABEL_STYLE)
        outer.addWidget(self._header)

        self._empty_label = QLabel(_EMPTY_ALTS_TEXT)
        self._empty_label.setStyleSheet(_EMPTY_LABEL_STYLE)
        outer.addWidget(self._empty_label)

        self._list = QListWidget(self)
        self._list.setStyleSheet(_LIST_STYLE)
        self._list.setMaximumHeight(96)
        outer.addWidget(self._list)

    def clear(self) -> None:
        self._list.clear()
        self._empty_label.setVisible(True)
        self._list.setVisible(False)

    def set_alternatives(self, alternatives: list[dict]) -> None:
        self._list.clear()
        if not alternatives:
            self.clear()
            return
        self._empty_label.setVisible(False)
        self._list.setVisible(True)
        for alt in alternatives[:3]:
            scene_ref = alt.get("scene_id")
            clip_id = alt.get("clip_id")
            ident = (
                f"scene_{scene_ref}"
                if scene_ref is not None
                else (f"clip_{clip_id}" if clip_id is not None else "—")
            )
            score = float(alt.get("score") or 0.0)
            role = alt.get("role") or "—"
            QListWidgetItem(f"#{ident} — score {score:.2f} — {role}", self._list)

    def item_count(self) -> int:
        return self._list.count()


# ── _BudgetState ─────────────────────────────────────────────────────────────


class _BudgetState(QFrame):
    """QFormLayout of whatever keys the rationale's ``budget_state`` dict has.

    No hardcoded key list — the pipeline can grow new keys and they show up
    automatically. Empty state → "—".
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("background:#0f141d;border-radius:4px;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        outer.setSpacing(2)

        self._header = QLabel("Budget state at cut")
        self._header.setStyleSheet(_HEADER_LABEL_STYLE)
        outer.addWidget(self._header)

        self._form_host = QWidget(self)
        self._form = QFormLayout(self._form_host)
        self._form.setContentsMargins(4, 2, 4, 2)
        self._form.setSpacing(4)
        outer.addWidget(self._form_host)

        self._empty_label = QLabel(_EMPTY_BUDGET_TEXT)
        self._empty_label.setStyleSheet(_EMPTY_LABEL_STYLE)
        outer.addWidget(self._empty_label)

    def clear(self) -> None:
        self._clear_form()
        self._empty_label.setVisible(True)

    def set_state(self, state: dict) -> None:
        self._clear_form()
        if not state:
            self._empty_label.setVisible(True)
            return
        self._empty_label.setVisible(False)
        for key in sorted(state.keys()):
            label = QLabel(str(key))
            label.setStyleSheet("color:#9ca3af;font-size:10px;")
            value_lbl = QLabel(str(state[key]))
            value_lbl.setStyleSheet("color:#e5e7eb;font-size:10px;")
            self._form.addRow(label, value_lbl)

    def row_count(self) -> int:
        return self._form.rowCount()

    def _clear_form(self) -> None:
        # QFormLayout.rowCount keeps old rows until takeRow is called. Loop
        # from the end to avoid reindexing.
        while self._form.rowCount():
            self._form.removeRow(0)


# ── AuditTab ─────────────────────────────────────────────────────────────────


class AuditTab(QWidget):
    """Top-level widget placed at tab index 2 of StudioBrainWindow (T11.2)."""

    cutSelected = Signal(int)  # decision_id

    def __init__(
        self,
        brain_service: BrainService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._svc = brain_service
        self._current_run_id: Optional[int] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        # Run selector (top bar).
        self._run_selector = _RunSelector(self)
        self._run_selector.runChanged.connect(self._on_run_changed)
        outer.addWidget(self._run_selector)

        # Segment strip (visible only for DJ-mix runs).
        self._segment_strip = _SegmentStrip(self)
        self._segment_strip.setVisible(False)
        outer.addWidget(self._segment_strip)

        # Main body: cut table (left) + details column (right).
        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(6)

        self._cut_table = _CutTable(self)
        self._cut_table.filterChanged.connect(self._on_filter_changed)
        self._cut_table.cutSelected.connect(self._on_cut_selected)
        middle.addWidget(self._cut_table, stretch=2)

        details = QWidget(self)
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.setSpacing(6)

        self._term_contributions = _TermContributions(details)
        details_layout.addWidget(self._term_contributions)

        self._alternatives = _Alternatives(details)
        details_layout.addWidget(self._alternatives)

        self._budget_state = _BudgetState(details)
        details_layout.addWidget(self._budget_state)
        details_layout.addStretch()

        middle.addWidget(details, stretch=1)
        outer.addLayout(middle, stretch=1)

        # Initial render.
        self.refresh()

    # ── Public API ─────────────────────────────────────────────────────────
    def refresh(self) -> None:
        """Invalidate the BrainService cache and reload runs + current cuts."""
        self._svc.invalidate()
        runs = self._safe_call(self._svc.list_runs_for_audit_selector, default=[])
        self._run_selector.set_runs(runs)
        # set_runs emits runChanged → cascades into reload below. If there
        # are no runs, clear everything explicitly so the tab settles.
        if not runs:
            self._current_run_id = None
            self._segment_strip.setVisible(False)
            self._cut_table.set_cuts([])
            self._term_contributions.clear()
            self._alternatives.clear()
            self._budget_state.clear()

    def select_run(self, run_id: int) -> None:
        """Select a run programmatically. Used by
        ``MemoryTab.runSelected.connect(AuditTab.select_run)`` so the two
        tabs stay aligned."""
        try:
            rid = int(run_id)
        except (TypeError, ValueError):
            return
        # If the run isn't already in the selector (e.g. it just completed),
        # refresh once to pick it up.
        if not self._run_selector.select_run_id(rid):
            self._svc.invalidate()
            runs = self._safe_call(
                self._svc.list_runs_for_audit_selector, default=[]
            )
            self._run_selector.set_runs(runs)
            self._run_selector.select_run_id(rid)

    # ── Internal ───────────────────────────────────────────────────────────
    def _on_run_changed(self, run_id: int) -> None:
        try:
            rid = int(run_id)
        except (TypeError, ValueError):
            return
        self._current_run_id = rid

        run = self._run_selector.current_run()
        is_dj_mix = bool(run and run.get("is_dj_mix"))
        total_duration = float((run or {}).get("total_duration_sec") or 0.0)

        if is_dj_mix:
            segments = self._safe_call(
                lambda: self._svc.list_structure_segments_for_run(rid),
                default=[],
            )
            self._segment_strip.set_segments(segments, total_duration)
            self._segment_strip.setVisible(True)
        else:
            self._segment_strip.setVisible(False)

        self._reload_cuts()

        # Clear the right-hand details column — the user hasn't picked a
        # row in the (new) cut table yet.
        self._term_contributions.clear()
        self._alternatives.clear()
        self._budget_state.clear()

    def _on_filter_changed(self, _filt: dict) -> None:
        # Cache invalidation is cheap — the DB is likely untouched, but the
        # filter combo changed the query key.
        self._reload_cuts()

    def _on_cut_selected(self, decision_id: int) -> None:
        try:
            did = int(decision_id)
        except (TypeError, ValueError):
            return
        # Fan out the signal for downstream consumers (P12 Story-Map).
        self.cutSelected.emit(did)

        detail = self._safe_call(
            lambda: self._svc.get_decision_detail(did), default=None
        )
        if not detail:
            self._term_contributions.clear()
            self._alternatives.clear()
            self._budget_state.clear()
            return
        self._term_contributions.set_terms(detail.get("rationale_terms") or {})
        self._alternatives.set_alternatives(detail.get("alternatives") or [])
        self._budget_state.set_state(detail.get("budget_state") or {})

    def _reload_cuts(self) -> None:
        if self._current_run_id is None:
            self._cut_table.set_cuts([])
            return
        filt = self._cut_table.current_filter()
        try:
            cuts = self._svc.list_decisions_for_run(
                self._current_run_id, filters=filt
            )
        except OperationalError as exc:
            logger.warning(
                "AuditTab: list_decisions_for_run(%d) failed: %s",
                self._current_run_id,
                exc,
            )
            cuts = []
        self._cut_table.set_cuts(cuts)

    @staticmethod
    def _safe_call(fn, default):
        try:
            return fn()
        except OperationalError as exc:
            logger.warning("AuditTab: read call failed: %s", exc)
            return default
