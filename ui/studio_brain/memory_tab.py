"""MemoryTab — Studio Brain "Gedächtnis" tab (T11.1).

Design §3 (Structure / Memory / Agent): the Gedächtnis tab surfaces the
memory layer the agent learns from — pacing runs, aggregated learned
patterns, and the decisions that feed them.

T11.1 scope (this file):
  - _RunTimeline       (horizontal strip of run-frames, newest first).
  - _PatternTable      (filterable QTableWidget of mem_learned_pattern rows).
  - _DecisionDrillDown (QListWidget of decisions matching the selected
                        pattern's context fingerprint).
  - _FooterBar         (Reset-learned-patterns QPushButton + status label).
  - MemoryTab          (glue widget; wires filter changes, row selection,
                        and the reset-button flow through BackupService).

Public signals:
  - ``runSelected(int)``   — emitted when the user picks a run frame. The
                             future Audit tab (T11.2) will consume it; for
                             now there is no internal listener.
  - ``patternsReset(int)`` — emitted after a successful reset, carrying the
                             count of rows deleted. Tests assert on this.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from services.backup_service import BackupService
from services.brain_service import BrainService

logger = logging.getLogger(__name__)


# ── Layout / style constants ──────────────────────────────────────────────────

_TIMELINE_HEIGHT = 180
_RUN_FRAME_WIDTH = 160
_RUN_FRAME_HEIGHT = 140
_EMPTY_DRILLDOWN_TEXT = (
    "Wähle ein Muster aus, um die zugehörigen Entscheidungen zu sehen."
)

_FRAME_STYLE = (
    "QFrame#MemoryRunFrame{background:#131922;"
    "border:1px solid rgba(255,255,255,0.07);border-radius:6px;}"
    "QFrame#MemoryRunFrame:hover{"
    "border:1px solid rgba(212,164,74,0.45);background:#161d28;}"
    "QLabel[role='run-title']{color:#e5e7eb;font-size:10px;font-weight:700;}"
    "QLabel[role='run-sub']{color:#9ca3af;font-size:9px;}"
    "QLabel[role='run-badge']{color:#d4a44a;font-size:9px;font-weight:600;}"
)

_COMBO_STYLE = (
    "QComboBox,QDoubleSpinBox,QPushButton{background:#1a2030;"
    "border:1px solid rgba(255,255,255,0.1);border-radius:4px;"
    "color:#e5e7eb;padding:3px 8px;font-size:10px;}"
    "QPushButton:hover{background:#202838;}"
    "QLabel{color:#9ca3af;font-size:9px;}"
)

_TABLE_STYLE = (
    "QTableWidget{background:#0f141d;color:#e5e7eb;font-size:10px;"
    "border:1px solid rgba(255,255,255,0.06);border-radius:4px;"
    "gridline-color:rgba(255,255,255,0.05);}"
    "QHeaderView::section{background:#131922;color:#9ca3af;"
    "border:none;padding:4px 6px;font-size:10px;font-weight:600;}"
)

_STATUS_OK_STYLE = (
    "color:#7ec77d;font-size:10px;padding:4px;"
    "background:#132018;border:1px solid rgba(126,199,125,0.25);"
    "border-radius:4px;"
)
_STATUS_ERR_STYLE = (
    "color:#f5a97b;font-size:10px;padding:4px;"
    "background:#2a1c0e;border:1px solid rgba(245,167,123,0.35);"
    "border-radius:4px;"
)


def _default_db_path() -> Path:
    """Return the canonical app DB path (``<repo>/pb_studio.db``).

    Mirrors what ``database.session`` hard-codes. Kept out of the public
    import path for ``database`` so ``MemoryTab`` can be constructed with an
    explicit ``BackupService`` in tests without touching the real DB file.
    """
    from database.session import APP_ROOT

    return Path(APP_ROOT) / "pb_studio.db"


def _default_backup_dir() -> Path:
    from database.session import APP_ROOT

    return Path(APP_ROOT) / "storage" / "backups"


def _stars(n: Optional[int]) -> str:
    """Pretty rating glyphs for the run-frame header. 0..5; None → em dash."""
    if n is None:
        return "—"
    clamped = max(0, min(5, int(n)))
    return "★" * clamped + "☆" * (5 - clamped)


def _format_timestamp(value: Any) -> str:
    """Format a started_at value (datetime or ISO-string) as ``mm-dd HH:MM``.

    The underlying ``mem_pacing_run.started_at`` column is a DATETIME, but
    SQLAlchemy may hand back either a ``datetime`` (from the ORM type
    coercion) or a raw string (from the ``text()``-based queries used here).
    Both need to render identically.
    """
    if value is None:
        return "—"
    try:
        from datetime import datetime

        if isinstance(value, datetime):
            return value.strftime("%m-%d %H:%M")
        # Raw text — SQLite format is typically "YYYY-MM-DD HH:MM:SS[.ffffff]".
        s = str(value)
        # Split at whitespace, take the last two date/time tokens.
        if " " in s:
            date_part, time_part = s.split(" ", 1)
            mm_dd = "-".join(date_part.split("-")[1:3]) if "-" in date_part else date_part
            hh_mm = ":".join(time_part.split(":")[0:2])
            return f"{mm_dd} {hh_mm}"
        return s
    except Exception:  # pragma: no cover — formatting is best-effort
        return str(value)


def _truncate(s: Optional[str], limit: int = 20) -> str:
    if not s:
        return "—"
    s = str(s)
    # Prefer a basename for file paths.
    base = os.path.basename(s) or s
    if len(base) <= limit:
        return base
    return base[: limit - 1] + "…"


# ── Run timeline ──────────────────────────────────────────────────────────────


class _RunFrame(QFrame):
    """Compact summary card for a single pacing run."""

    clicked = Signal(int)

    def __init__(self, run: dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._run = dict(run)
        self.setObjectName("MemoryRunFrame")
        self.setFixedSize(_RUN_FRAME_WIDTH, _RUN_FRAME_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(_FRAME_STYLE)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(8, 6, 8, 6)
        vl.setSpacing(3)

        title = QLabel(_format_timestamp(run.get("started_at")))
        title.setProperty("role", "run-title")
        vl.addWidget(title)

        fname = QLabel(_truncate(run.get("audio_track_filename")))
        fname.setProperty("role", "run-sub")
        fname.setToolTip(str(run.get("audio_track_filename") or ""))
        vl.addWidget(fname)

        cuts = QLabel(f"{int(run.get('total_cuts') or 0)} Schnitte")
        cuts.setProperty("role", "run-sub")
        vl.addWidget(cuts)

        rating_lbl = QLabel(_stars(run.get("user_rating")))
        rating_lbl.setProperty("role", "run-sub")
        vl.addWidget(rating_lbl)

        if bool(run.get("is_dj_mix")):
            badge = QLabel("DJ-Mix")
            badge.setProperty("role", "run-badge")
            vl.addWidget(badge)

        vl.addStretch()

    @property
    def run_id(self) -> int:
        return int(self._run["id"])

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802 — Qt override
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.run_id)
        super().mousePressEvent(event)


class _RunTimeline(QScrollArea):
    """Horizontal strip of ``_RunFrame`` cards. Newest run on the left."""

    runSelected = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(_TIMELINE_HEIGHT)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}"
            "QWidget#MemoryRunStrip{background:transparent;}"
        )

        self._strip = QWidget()
        self._strip.setObjectName("MemoryRunStrip")
        self.setToolTip(
            "Deine bisherigen Pacing-Runs in chronologischer Reihenfolge "
            "(neueste links). Eine Karte pro Run zeigt Datum, "
            "Audio-Datei, Anzahl Schnitte und ggf. Rating."
        )
        self._hl = QHBoxLayout(self._strip)
        self._hl.setContentsMargins(6, 6, 6, 6)
        self._hl.setSpacing(6)

        self._empty_label = QLabel("Noch keine Pacing-Runs vorhanden.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color:#6b7280;font-size:11px;padding:24px;")
        self._empty_label.setVisible(False)
        self._hl.addWidget(self._empty_label)
        self._hl.addStretch()

        self._frames: list[_RunFrame] = []
        self.setWidget(self._strip)

    def set_runs(self, runs: list[dict[str, Any]]) -> None:
        # Clear old frames (keep the empty-label + stretch sentinels).
        for f in self._frames:
            self._hl.removeWidget(f)
            f.setParent(None)
            f.deleteLater()
        self._frames.clear()

        if not runs:
            self._empty_label.setVisible(True)
            return
        self._empty_label.setVisible(False)

        # Insert frames before the trailing stretch (last item).
        stretch_idx = self._hl.count() - 1
        for run in runs:
            frame = _RunFrame(run, parent=self._strip)
            frame.clicked.connect(self.runSelected)
            self._hl.insertWidget(stretch_idx, frame)
            stretch_idx += 1
            self._frames.append(frame)

    def frame_count(self) -> int:
        return len(self._frames)


# ── Pattern table ────────────────────────────────────────────────────────────


_PATTERN_COLUMNS: tuple[tuple[str, int], ...] = (
    ("Type", 100),
    ("Fingerprint", 260),
    ("Accept", 60),
    ("Reject", 60),
    ("Confidence", 90),
    ("Updated", 140),
)


def _format_fingerprint(fp: Optional[dict[str, Any]]) -> str:
    if not fp or not isinstance(fp, dict):
        return "—"
    bits: list[str] = []
    for k in ("genre", "section_type", "bpm_bucket"):
        v = fp.get(k)
        if v is None:
            continue
        bits.append(f"{k}={v}")
    if not bits:
        return "—"
    return " ".join(bits)


class _PatternTable(QWidget):
    """Filterable table of mem_learned_pattern rows."""

    patternSelected = Signal(int)  # pattern_id
    patternActivated = Signal(int)  # double-click → drill-down trigger
    applyRequested = Signal(dict)   # {"pattern_type": str|None, "min_confidence": float}

    def __init__(
        self,
        brain_service: BrainService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._svc = brain_service
        self._patterns: list[dict[str, Any]] = []
        self._build()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        filter_row = QWidget(self)
        filter_row.setStyleSheet(_COMBO_STYLE)
        hl = QHBoxLayout(filter_row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)

        hl.addWidget(QLabel("Typ:"))
        self._type_combo = QComboBox()
        self._type_combo.addItem("(any)", userData=None)
        for ptype in self._safe_types():
            self._type_combo.addItem(ptype, userData=ptype)
        self._type_combo.setToolTip(
            "Filter: nur Muster eines bestimmten Typs zeigen (harmonic, "
            "style, rhythmic, etc.)."
        )
        hl.addWidget(self._type_combo)

        hl.addWidget(QLabel("Min. Sicherheit:"))
        self._conf_spin = QDoubleSpinBox()
        self._conf_spin.setRange(0.0, 1.0)
        self._conf_spin.setSingleStep(0.05)
        self._conf_spin.setDecimals(2)
        self._conf_spin.setValue(0.0)
        self._conf_spin.setToolTip(
            "Zeigt nur Muster mit mindestens so sicherer "
            "Wilson-Lower-Bound-Konfidenz. 0.7 = nur Muster die sich klar "
            "bewaehrt haben."
        )
        hl.addWidget(self._conf_spin)

        self._apply_btn = QPushButton("Anwenden")
        self._apply_btn.setToolTip("Filter anwenden und Tabelle neu laden.")
        self._apply_btn.clicked.connect(self._emit_apply)
        hl.addWidget(self._apply_btn)
        hl.addStretch()
        outer.addWidget(filter_row)

        self._table = QTableWidget(0, len(_PATTERN_COLUMNS), self)
        self._table.setHorizontalHeaderLabels([c[0] for c in _PATTERN_COLUMNS])
        for idx, (_label, width) in enumerate(_PATTERN_COLUMNS):
            self._table.setColumnWidth(idx, width)
        # Spalten-Tooltips (einsteigerfreundlich).
        _col_tooltips = (
            "Art des Musters (harmonic = basierend auf Musik-Tonart, style = "
            "auf Stil-Bucket, etc.).",
            "Der Kontext unter dem das Muster gilt: Genre/Section/BPM-Bucket.",
            "Wie oft der Clip in diesem Kontext akzeptiert wurde "
            "(User-Verdict 'accept').",
            "Wie oft der Clip in diesem Kontext abgelehnt wurde.",
            "Wilson-Untergrenze der Akzeptanzrate — konservativer Schaetzer, "
            "der kleine Stichproben benachteiligt.",
            "Zeitpunkt der letzten Aggregation.",
        )
        for idx, tip in enumerate(_col_tooltips):
            hdr_item = self._table.horizontalHeaderItem(idx)
            if hdr_item is not None:
                hdr_item.setToolTip(tip)
        self._table.setToolTip(
            "Automatisch gelernte Muster: Welche Clips bevorzugt der Agent "
            "in welchem Kontext. Zeile anklicken -> Details unten."
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self._table.setStyleSheet(_TABLE_STYLE)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.cellDoubleClicked.connect(self._on_double_clicked)
        outer.addWidget(self._table, stretch=1)

    # ── Public API ─────────────────────────────────────────────────────────
    def set_patterns(self, patterns: list[dict[str, Any]]) -> None:
        self._patterns = [dict(p) for p in patterns]
        self._table.setRowCount(0)
        self._table.setRowCount(len(patterns))
        for row, pattern in enumerate(patterns):
            self._table.setItem(row, 0, QTableWidgetItem(str(pattern.get("pattern_type") or "—")))
            self._table.setItem(
                row, 1, QTableWidgetItem(_format_fingerprint(pattern.get("context_fingerprint")))
            )
            self._table.setItem(
                row, 2, QTableWidgetItem(str(int(pattern.get("stat_accept_count") or 0)))
            )
            self._table.setItem(
                row, 3, QTableWidgetItem(str(int(pattern.get("stat_reject_count") or 0)))
            )
            self._table.setItem(
                row, 4, QTableWidgetItem(f"{float(pattern.get('confidence') or 0.0):.3f}")
            )
            self._table.setItem(
                row, 5, QTableWidgetItem(_format_timestamp(pattern.get("last_updated")))
            )
            # Stash the pattern_id on the first item so selection handlers
            # can recover it without a side lookup.
            id_item = self._table.item(row, 0)
            if id_item is not None:
                id_item.setData(Qt.ItemDataRole.UserRole, int(pattern["id"]))

    def current_pattern_id(self) -> Optional[int]:
        row = self._current_row()
        if row is None:
            return None
        item = self._table.item(row, 0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is None:
            return None
        return int(data)

    def current_filter(self) -> dict[str, Any]:
        return {
            "pattern_type": self._type_combo.currentData(),
            "min_confidence": float(self._conf_spin.value()),
        }

    def set_type_filter(self, value: Optional[str]) -> None:
        for i in range(self._type_combo.count()):
            if self._type_combo.itemData(i) == value:
                self._type_combo.setCurrentIndex(i)
                return
        self._type_combo.setCurrentIndex(0)

    def set_min_confidence(self, value: float) -> None:
        self._conf_spin.setValue(float(value))

    def rebuild_type_choices(self, types: list[str]) -> None:
        current = self._type_combo.currentData()
        self._type_combo.blockSignals(True)
        try:
            self._type_combo.clear()
            self._type_combo.addItem("(any)", userData=None)
            for t in types:
                self._type_combo.addItem(t, userData=t)
            # Restore the previous selection if still available.
            if current is not None:
                for i in range(self._type_combo.count()):
                    if self._type_combo.itemData(i) == current:
                        self._type_combo.setCurrentIndex(i)
                        break
        finally:
            self._type_combo.blockSignals(False)

    def row_count(self) -> int:
        return self._table.rowCount()

    def select_row(self, row: int) -> None:
        if 0 <= row < self._table.rowCount():
            self._table.selectRow(row)

    # ── Internal ───────────────────────────────────────────────────────────
    def _emit_apply(self) -> None:
        self.applyRequested.emit(self.current_filter())

    def _current_row(self) -> Optional[int]:
        sel = self._table.selectionModel()
        if sel is None:
            return None
        rows = sel.selectedRows()
        if not rows:
            return None
        return rows[0].row()

    def _on_selection_changed(self) -> None:
        pid = self.current_pattern_id()
        if pid is not None:
            self.patternSelected.emit(pid)

    def _on_double_clicked(self, row: int, _col: int) -> None:
        item = self._table.item(row, 0)
        if item is None:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is not None:
            self.patternActivated.emit(int(data))

    def _safe_types(self) -> list[str]:
        try:
            return list(self._svc.list_distinct_pattern_types())
        except OperationalError as exc:
            logger.warning("MemoryTab: list_distinct_pattern_types failed: %s", exc)
            return []


# ── Decision drill-down ──────────────────────────────────────────────────────


class _DecisionDrillDown(QWidget):
    """Read-only list of decisions matching the selected pattern's fingerprint."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self._header = QLabel(_EMPTY_DRILLDOWN_TEXT)
        self._header.setWordWrap(True)
        self._header.setStyleSheet(
            "color:#e5e7eb;font-size:10px;font-weight:600;padding:4px 0px;"
        )
        outer.addWidget(self._header)

        self._list = QListWidget(self)
        self._list.setStyleSheet(
            "QListWidget{background:#0f141d;color:#e5e7eb;font-size:10px;"
            "border:1px solid rgba(255,255,255,0.06);border-radius:4px;}"
        )
        self._list.setToolTip(
            "Die einzelnen Entscheidungen hinter dem gewaehlten Muster: "
            "Wann wurde der Clip geschnitten, mit welchem Score, was war "
            "der User-Verdict?"
        )
        outer.addWidget(self._list, stretch=1)

    def clear(self) -> None:
        self._list.clear()
        self._header.setText(_EMPTY_DRILLDOWN_TEXT)

    def populate(self, pattern: dict[str, Any], decisions: list[dict[str, Any]]) -> None:
        ptype = pattern.get("pattern_type") or "—"
        fp = _format_fingerprint(pattern.get("context_fingerprint"))
        self._header.setText(f"Muster: {ptype}  |  {fp}")
        self._list.clear()
        for d in decisions:
            ts = float(d.get("at_timestamp_sec") or 0.0)
            scene_id = d.get("scene_id")
            role = d.get("clip_role") or "—"
            mood = d.get("clip_mood_refined") or "—"
            verdict = d.get("user_verdict")
            verdict_suffix = f" [{verdict}]" if verdict else ""
            scene_label = f"scene_{scene_id}" if scene_id is not None else "scene_—"
            text_line = (
                f"[{ts:7.2f}s] {scene_label}  {role}/{mood}{verdict_suffix}"
            )
            QListWidgetItem(text_line, self._list)

    def item_count(self) -> int:
        return self._list.count()


# ── Footer bar ───────────────────────────────────────────────────────────────


class _FooterBar(QWidget):
    """Bottom strip: reset-button + transient status label."""

    resetClicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self._status = QLabel("")
        self._status.setVisible(False)
        outer.addWidget(self._status, stretch=1)

        self._reset_btn = QPushButton("Gelerntes zurücksetzen…")
        self._reset_btn.setStyleSheet(_COMBO_STYLE)
        self._reset_btn.setToolTip(
            "ACHTUNG: Loescht alle gelernten Muster. Vorher wird "
            "automatisch ein Backup der Datenbank erstellt. Die "
            "mem_decision-Historie bleibt erhalten — nur die aggregierten "
            "Muster verschwinden."
        )
        self._reset_btn.clicked.connect(self.resetClicked)
        outer.addWidget(self._reset_btn)

    def set_status_ok(self, msg: str) -> None:
        self._status.setText(msg)
        self._status.setStyleSheet(_STATUS_OK_STYLE)
        self._status.setVisible(True)

    def set_status_error(self, msg: str) -> None:
        self._status.setText(msg)
        self._status.setStyleSheet(_STATUS_ERR_STYLE)
        self._status.setVisible(True)

    def clear_status(self) -> None:
        self._status.setText("")
        self._status.setVisible(False)


# ── Memory tab ───────────────────────────────────────────────────────────────


class MemoryTab(QWidget):
    """Top-level widget placed at tab index 1 of StudioBrainWindow."""

    runSelected = Signal(int)
    patternsReset = Signal(int)

    def __init__(
        self,
        brain_service: BrainService,
        backup_service: Optional[BackupService] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._svc = brain_service
        self._backup_service = backup_service if backup_service is not None else self._build_default_backup_service()
        self._selected_pattern: Optional[dict[str, Any]] = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        self._timeline = _RunTimeline(self)
        self._timeline.runSelected.connect(self.runSelected)
        outer.addWidget(self._timeline)

        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(6)

        self._pattern_table = _PatternTable(brain_service, self)
        self._pattern_table.patternSelected.connect(self._on_pattern_selected)
        self._pattern_table.patternActivated.connect(self._on_pattern_selected)
        self._pattern_table.applyRequested.connect(self._on_filter_apply)
        middle.addWidget(self._pattern_table, stretch=2)

        self._drill_down = _DecisionDrillDown(self)
        middle.addWidget(self._drill_down, stretch=1)

        outer.addLayout(middle, stretch=1)

        self._footer = _FooterBar(self)
        self._footer.resetClicked.connect(self._on_reset_clicked)
        outer.addWidget(self._footer)

        # Initial render.
        self.refresh()

    # ── Public API ─────────────────────────────────────────────────────────
    def refresh(self) -> None:
        """Invalidate the BrainService cache and re-render every panel."""
        self._svc.invalidate()
        runs: list[dict[str, Any]] = self._safe_call(
            self._svc.list_pacing_runs, default=[]
        )
        self._timeline.set_runs(runs)

        types: list[str] = self._safe_call(
            self._svc.list_distinct_pattern_types, default=[]
        )
        self._pattern_table.rebuild_type_choices(types)

        self._reload_patterns()

    # ── Internal ───────────────────────────────────────────────────────────
    def _reload_patterns(self) -> None:
        filt = self._pattern_table.current_filter()
        try:
            patterns = self._svc.list_learned_patterns(
                pattern_type=filt["pattern_type"],
                min_confidence=float(filt["min_confidence"]),
            )
        except OperationalError as exc:
            logger.warning("MemoryTab: list_learned_patterns failed: %s", exc)
            patterns = []
        self._pattern_table.set_patterns(patterns)
        # Previously-selected pattern may be gone → clear drill-down.
        if self._selected_pattern is not None:
            still_there = any(
                int(p["id"]) == int(self._selected_pattern["id"]) for p in patterns
            )
            if not still_there:
                self._selected_pattern = None
                self._drill_down.clear()

    def _on_filter_apply(self, _filt: dict[str, Any]) -> None:
        self._svc.invalidate()
        self._reload_patterns()

    def _on_pattern_selected(self, pattern_id: int) -> None:
        try:
            pid = int(pattern_id)
        except (TypeError, ValueError):
            return
        # Find the pattern dict we already have cached in the table.
        patterns = self._pattern_table._patterns
        pattern = next(
            (p for p in patterns if int(p["id"]) == pid), None
        )
        if pattern is None:
            return
        self._selected_pattern = pattern
        try:
            decisions = self._svc.list_decisions_for_pattern(pid)
        except OperationalError as exc:
            logger.warning(
                "MemoryTab: list_decisions_for_pattern(%d) failed: %s", pid, exc
            )
            decisions = []
        self._drill_down.populate(pattern, decisions)

    def _on_reset_clicked(self) -> None:
        reply = QMessageBox.question(
            self,
            "Gelerntes zurücksetzen",
            (
                "Das löscht dauerhaft alle gelernten Muster.\n"
                "Vorher wird automatisch ein Backup erstellt.\n"
                "Weiter?"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            deleted_count, backup_path = self._perform_reset()
        except Exception as exc:  # noqa: BLE001 — surfaced to the user
            logger.exception("MemoryTab: pattern reset failed")
            QMessageBox.critical(
                self,
                "Zurücksetzen fehlgeschlagen",
                f"Konnte gelernte Muster nicht zurücksetzen:\n{exc}",
            )
            self._footer.set_status_error(
                f"Zurücksetzen fehlgeschlagen: {exc}"
            )
            return

        self._svc.invalidate()
        self.refresh()
        self._footer.set_status_ok(
            f"{deleted_count} Muster gelöscht. Backup unter {backup_path}."
        )
        self.patternsReset.emit(int(deleted_count))

    def _perform_reset(self) -> tuple[int, Path]:
        """Run the destructive SQL inside a BackupService-guarded context.

        Returns ``(deleted_count, backup_path)``. The backup path is read
        off ``BackupService.list_backups()`` post-hoc so we don't have to
        plumb the return value of ``backup()`` through the context manager.
        """
        svc = self._backup_service
        if svc is None:
            raise RuntimeError("No BackupService configured for MemoryTab.")

        deleted_count = 0
        with svc.pattern_reset_context(reason="learned_patterns_reset"):
            session, ownership = self._open_session()
            try:
                deleted_count = int(
                    session.execute(
                        text("SELECT COUNT(*) FROM mem_learned_pattern")
                    ).scalar()
                    or 0
                )
                session.execute(text("DELETE FROM mem_learned_pattern"))
                commit = getattr(session, "commit", None)
                if callable(commit):
                    commit()
            finally:
                self._close_session(session, ownership)

        backups = svc.list_backups()
        backup_path = backups[0].path if backups else Path("<unknown>")
        return deleted_count, backup_path

    # ── Session helpers (mirror BrainService) ──────────────────────────────
    def _open_session(self) -> tuple[Any, bool]:
        factory = getattr(self._svc, "_session_factory", None)
        if factory is None:
            raise RuntimeError(
                "MemoryTab requires a BrainService with a session_factory."
            )
        session = factory()
        ownership = False
        if hasattr(session, "__enter__") and not hasattr(session, "execute"):
            session = session.__enter__()
            ownership = True
        return session, ownership

    @staticmethod
    def _close_session(session: Any, ownership: bool) -> None:
        try:
            if ownership:
                session.__exit__(None, None, None)
            else:
                close = getattr(session, "close", None)
                if callable(close):
                    close()
        except Exception:  # best-effort cleanup
            pass

    # ── Defaults ───────────────────────────────────────────────────────────
    @staticmethod
    def _build_default_backup_service() -> Optional[BackupService]:
        """Return a BackupService wired to the app-default DB + storage dir.

        Gracefully returns ``None`` if the real DB file does not exist — tests
        that don't want backup behaviour can construct MemoryTab directly with
        ``backup_service=None`` or swap in a mock. The ``BackupService.__init__``
        call itself always succeeds (it just ``mkdir``s the backup dir).
        """
        try:
            db_path = _default_db_path()
            backup_dir = _default_backup_dir()
            return BackupService(db_path=db_path, backup_dir=backup_dir)
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("MemoryTab: default BackupService construction failed: %s", exc)
            return None

    @staticmethod
    def _safe_call(fn: Callable[[], T], default: T) -> T:
        try:
            return fn()
        except OperationalError as exc:
            logger.warning("MemoryTab: listing call failed: %s", exc)
            return default
