"""P1.4 / Cycle 11: Pacing-Decision-Explorer Widget.

Zeigt für jede Decision in einem Run:
- Tabellen-Übersicht (run_id, sequence_idx, scene_id, reward, top_component)
- Detail-Panel mit Top-3 Reward-Komponenten + Breakdown
- Quick-Verdict-Buttons (👍 / 👎) die user_verdict in mem_decision schreiben

Konsumiert `services.pacing.decision_explainer.explain_decision` als
headless Logik-Layer (keine UI-Logik dupliziert).

Datenquelle: SQLAlchemy-Session-Factory die mem_decision liest.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text

from services.pacing.decision_explainer import explain_decision
from services.pacing.rl_reward import REWARD_KEYS, RewardComponents

logger = logging.getLogger(__name__)


_TABLE_HEADERS = ("seq", "scene", "section", "reward", "verdict", "top")


class PacingDecisionExplorer(QWidget):
    """Tab-Widget für Pacing-Decision-Replay + Verdict-Editing."""

    decisionSelected = Signal(int)  # decision_id
    verdictChanged = Signal(int, str)  # decision_id, verdict

    def __init__(
        self,
        session_factory: Callable | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._session_factory = session_factory
        self._current_decision_id: int | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header: Run-Selector
        header_row = QHBoxLayout()
        header_row.addWidget(QLabel(self.tr("Run:")))
        self.run_combo = QComboBox()
        self.run_combo.setMinimumWidth(180)
        self.run_combo.setToolTip(
            "Pacing-Run aus dem Lernspeicher waehlen, dessen Entscheidungen untersucht werden sollen."
        )
        self.run_combo.currentIndexChanged.connect(self._on_run_changed)
        header_row.addWidget(self.run_combo)
        self.btn_refresh = QPushButton(self.tr("Aktualisieren"))
        self.btn_refresh.setToolTip(
            "Pacing-Runs und Decision-Tabelle aus der Datenbank neu laden."
        )
        self.btn_refresh.clicked.connect(self.refresh_runs)
        header_row.addWidget(self.btn_refresh)
        header_row.addStretch()
        layout.addLayout(header_row)

        # Splitter: oben Tabelle, unten Detail
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Tabelle
        self.table = QTableWidget()
        self.table.setColumnCount(len(_TABLE_HEADERS))
        self.table.setHorizontalHeaderLabels(list(_TABLE_HEADERS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setToolTip(
            "Entscheidungen eines Runs: Szene, Section, Reward, User-Verdict und wichtigster Reward-Faktor."
        )
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        splitter.addWidget(self.table)

        # Detail-Panel
        detail_widget = QWidget()
        detail_layout = QVBoxLayout(detail_widget)
        detail_layout.setContentsMargins(0, 4, 0, 0)

        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setToolTip(
            "Detailanalyse der ausgewaehlten Entscheidung mit Top-Reward-Komponenten und Roh-Rationale."
        )
        detail_layout.addWidget(self.detail_text)

        # Verdict-Buttons
        verdict_row = QHBoxLayout()
        verdict_row.addWidget(QLabel(self.tr("Verdict:")))
        self.btn_good = QPushButton("👍 Gut")
        self.btn_good.setToolTip(
            "Ausgewaehlte Pacing-Entscheidung als gut bewerten und im Lernspeicher speichern."
        )
        self.btn_good.clicked.connect(lambda: self._set_verdict("good"))
        verdict_row.addWidget(self.btn_good)
        self.btn_bad = QPushButton("👎 Schlecht")
        self.btn_bad.setToolTip(
            "Ausgewaehlte Pacing-Entscheidung als schlecht bewerten und im Lernspeicher speichern."
        )
        self.btn_bad.clicked.connect(lambda: self._set_verdict("bad"))
        verdict_row.addWidget(self.btn_bad)
        verdict_row.addStretch()
        detail_layout.addLayout(verdict_row)

        splitter.addWidget(detail_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter)

        self.refresh_runs()

    # ── Public API ─────────────────────────────────────────────────────────

    def refresh_runs(self) -> None:
        """Lädt Liste der mem_pacing_run-IDs in die Combo."""
        if self._session_factory is None:
            return
        try:
            with self._open_session() as session:
                rows = session.execute(
                    text(
                        "SELECT id, COALESCE(audio_track_id, 0), started_at "
                        "FROM mem_pacing_run ORDER BY id DESC LIMIT 50"
                    )
                ).fetchall()
        except Exception as e:  # broad: DB-Fehler darf Tab nicht crashen
            logger.warning("PacingDecisionExplorer.refresh_runs failed: %s", e)
            return
        self.run_combo.blockSignals(True)
        self.run_combo.clear()
        for run_id, audio_id, started_at in rows:
            self.run_combo.addItem(f"Run {run_id} (audio={audio_id}, {started_at})", run_id)
        self.run_combo.blockSignals(False)
        if self.run_combo.count() > 0:
            self._on_run_changed(0)

    def select_decision(self, decision_id: int) -> None:
        """Externer Hook (z.B. von Audit-Tab): Detail-Panel auf eine
        Decision-ID setzen."""
        self._current_decision_id = decision_id
        self._refresh_detail()

    # ── Slots ──────────────────────────────────────────────────────────────

    def _on_run_changed(self, idx: int) -> None:
        if idx < 0 or self._session_factory is None:
            return
        run_id = self.run_combo.itemData(idx)
        if run_id is None:
            return
        self._load_decisions_for_run(int(run_id))

    def _on_row_selected(self) -> None:
        items = self.table.selectedItems()
        if not items:
            return
        row = items[0].row()
        decision_id_item = self.table.item(row, 0)
        if decision_id_item is None:
            return
        decision_id = decision_id_item.data(Qt.ItemDataRole.UserRole)
        if decision_id is None:
            return
        self._current_decision_id = int(decision_id)
        self.decisionSelected.emit(self._current_decision_id)
        self._refresh_detail()

    def _set_verdict(self, verdict: str) -> None:
        if self._current_decision_id is None or self._session_factory is None:
            return
        try:
            with self._open_session() as session:
                session.execute(
                    text(
                        "UPDATE mem_decision SET user_verdict = :verdict, "
                        "user_verdict_at = datetime('now') WHERE id = :id"
                    ),
                    {"verdict": verdict, "id": self._current_decision_id},
                )
                session.commit()
        except Exception as e:
            logger.warning("Verdict-Update failed: %s", e)
            return
        self.verdictChanged.emit(self._current_decision_id, verdict)
        self._refresh_detail()
        # Tabelle neu laden um Verdict-Spalte zu aktualisieren
        idx = self.run_combo.currentIndex()
        if idx >= 0:
            self._on_run_changed(idx)

    # ── Internals ──────────────────────────────────────────────────────────

    def _open_session(self):
        """Liefert ein Session-Context-Manager."""
        sess = self._session_factory()
        if hasattr(sess, "__enter__"):
            return sess
        # Plain Session — wrap in a minimal contextmanager
        from contextlib import contextmanager

        @contextmanager
        def _wrap():
            try:
                yield sess
            finally:
                close = getattr(sess, "close", None)
                if callable(close):
                    close()

        return _wrap()

    def _load_decisions_for_run(self, run_id: int) -> None:
        try:
            with self._open_session() as session:
                rows = session.execute(
                    text(
                        "SELECT id, sequence_idx, scene_id, at_section_type, "
                        "reward, user_verdict, reward_components "
                        "FROM mem_decision WHERE run_id = :run_id "
                        "ORDER BY sequence_idx"
                    ),
                    {"run_id": run_id},
                ).fetchall()
        except Exception as e:
            logger.warning("Load decisions failed: %s", e)
            return

        self.table.setRowCount(len(rows))
        for r, (did, seq, scene_id, section, reward, verdict, components) in enumerate(rows):
            top_key = self._top_component_key(components)
            cells = [
                str(seq),
                str(scene_id),
                str(section or "-"),
                f"{reward:.3f}" if reward is not None else "-",
                str(verdict or "-"),
                top_key,
            ]
            for c, val in enumerate(cells):
                item = QTableWidgetItem(val)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, did)
                self.table.setItem(r, c, item)

    def _top_component_key(self, components_json: Any) -> str:
        if not components_json:
            return "-"
        try:
            parsed = json.loads(components_json) if isinstance(components_json, str) else components_json
            if not parsed:
                return "-"
            return max(parsed, key=parsed.get)
        except (json.JSONDecodeError, TypeError):
            return "?"

    def _refresh_detail(self) -> None:
        if self._current_decision_id is None or self._session_factory is None:
            self.detail_text.clear()
            return
        try:
            with self._open_session() as session:
                row = session.execute(
                    text(
                        "SELECT id, reward, reward_components, user_verdict, "
                        "agent_rationale, at_section_type, scene_id "
                        "FROM mem_decision WHERE id = :id"
                    ),
                    {"id": self._current_decision_id},
                ).fetchone()
        except Exception as e:
            logger.warning("Detail-Refresh failed: %s", e)
            self.detail_text.setText(f"Fehler beim Laden: {e}")
            return
        if row is None:
            self.detail_text.setText("Decision nicht gefunden.")
            return

        decision_id, reward, components_json, verdict, rationale, section, scene_id = row
        # Parse + explain
        try:
            comps_dict = (
                json.loads(components_json) if isinstance(components_json, str) and components_json
                else {}
            )
        except json.JSONDecodeError:
            comps_dict = {}

        if comps_dict and set(REWARD_KEYS).issubset(comps_dict.keys()):
            comps = RewardComponents(**{k: float(comps_dict[k]) for k in REWARD_KEYS})
            expl = explain_decision(comps, user_verdict=verdict, top_n=3)
        else:
            expl = None

        lines = [
            f"Decision #{decision_id}",
            f"Section: {section or '-'} | Scene: {scene_id} | Verdict: {verdict or '-'}",
            f"Reward: {reward:.3f}" if reward is not None else "Reward: -",
            "",
        ]
        if expl is not None:
            lines.append("Top-3 Komponenten:")
            for c in expl["top_components"]:
                lines.append(
                    f"  {c['key']:14s}  value={c['value']:.3f}  "
                    f"weight={c['weight']:.3f}  → contrib={c['contribution']:.3f}"
                )
            lines.append("")
            lines.append("Breakdown:")
            for k, v in expl["breakdown"].items():
                lines.append(f"  {k:14s}  {v:.4f}")
        else:
            lines.append("(Keine Reward-Komponenten gespeichert.)")
        if rationale:
            lines.append("")
            lines.append("Rationale (raw):")
            lines.append(str(rationale)[:500])

        self.detail_text.setPlainText("\n".join(lines))
