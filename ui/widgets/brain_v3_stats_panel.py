"""Brain V3 — Stats-Panel-Widget (Phase 5, 06_PHASES.md Z.421-427).

Neuer Tab/Widget mit:
- Total Klicks
- Cold-Start vs Learned Achsen-Status (x/17 cold, y/17 learned)
- Top-5 staerkste positive Buckets
- Top-5 staerkste negative Buckets
- Reset-Button mit two-step Confirmation

NICHT eingebaut in `studio_brain_window.py` — eigenstaendig pluggable
in jedes Layout (NavBar-Tab, Side-Panel, etc.).
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.brain_v3.brain_v3_service import BrainV3Service
from services.brain_v3.schemas.brain_v3_schemas import ResetRequest
from ui.widgets.brain_v3_learning_dialog import BrainV3LearningSessionDialog

logger = logging.getLogger(__name__)


class BrainV3StatsPanel(QWidget):
    """Read-only Status + Reset-Action."""

    stats_refreshed = Signal()
    reset_done = Signal()

    def __init__(
        self,
        service: Optional[BrainV3Service] = None,
        auto_refresh_ms: int = 5000,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._service = service or BrainV3Service()
        self._learning_dialog: BrainV3LearningSessionDialog | None = None
        self._build_ui()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(auto_refresh_ms)
        self._refresh_timer.timeout.connect(self._refresh_if_visible)
        self._refresh_timer.start()
        # Erstmal sofort laden, aber nur wenn der Tab wirklich sichtbar ist.
        QTimer.singleShot(0, self._refresh_if_visible)

    # --- UI -------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel("Brain V3 — Lernstatus")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        root.addWidget(title)

        # Total Klicks
        self._lbl_total_clicks = QLabel("Total Klicks: —")
        root.addWidget(self._lbl_total_clicks)

        # Cold/Learned
        learned_row = QHBoxLayout()
        self._lbl_learned = QLabel("Gelernte Achsen: —/17")
        self._bar_learned = QProgressBar()
        self._bar_learned.setRange(0, 17)
        self._bar_learned.setFormat("%v / 17")
        self._bar_learned.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        learned_row.addWidget(self._lbl_learned, 1)
        learned_row.addWidget(self._bar_learned, 2)
        root.addLayout(learned_row)

        # Last feedback at
        self._lbl_last = QLabel("Letztes Feedback: nie")
        self._lbl_last.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px;")
        root.addWidget(self._lbl_last)

        # Trennline
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: rgba(255,255,255,0.08);")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # Top positive
        root.addWidget(QLabel("Top 5 positive Buckets:"))
        self._tree_pos = self._make_bucket_tree()
        root.addWidget(self._tree_pos)

        # Top negative
        root.addWidget(QLabel("Top 5 negative Buckets:"))
        self._tree_neg = self._make_bucket_tree()
        root.addWidget(self._tree_neg)

        # Action-Row
        actions = QHBoxLayout()
        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.clicked.connect(self.refresh)
        actions.addWidget(self._btn_refresh)
        self._btn_learning = QPushButton("Lern-Session")
        self._btn_learning.setToolTip("Brain-V3-Lern-Session mit echten Preview-Pfaden oeffnen.")
        self._btn_learning.setAccessibleName("Brain V3 Lern-Session oeffnen")
        self._btn_learning.clicked.connect(self._on_learning_clicked)
        actions.addWidget(self._btn_learning)
        self._btn_reset = QPushButton("Reset Hirn-Store")
        self._btn_reset.setStyleSheet(
            "QPushButton { background: #6e1f1f; color: white; padding: 4px 10px; }"
            "QPushButton:hover { background: #8a2828; }"
        )
        self._btn_reset.clicked.connect(self._on_reset_clicked)
        actions.addWidget(self._btn_reset)
        actions.addStretch(1)
        root.addLayout(actions)
        root.addStretch(1)

    def _make_bucket_tree(self) -> QTreeWidget:
        t = QTreeWidget()
        t.setHeaderLabels(["Achse", "Level", "Context", "α", "β"])
        t.setRootIsDecorated(False)
        t.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        t.setMaximumHeight(140)
        return t

    # --- Logic ----------------------------------------------------------
    def _refresh_if_visible(self) -> None:
        if not self.isVisible():
            return
        self.refresh()

    def refresh(self) -> None:
        try:
            stats = self._service.stats()
        except Exception as exc:
            logger.warning("BrainV3StatsPanel.refresh failed: %s", exc)
            return
        self._lbl_total_clicks.setText(f"Total Klicks: {stats.total_clicks}")
        self._lbl_learned.setText(
            f"Gelernte Achsen: {stats.learned_axes}/17 "
            f"(Cold-Start: {stats.cold_start_axes})"
        )
        self._bar_learned.setValue(stats.learned_axes)
        self._lbl_last.setText(
            f"Letztes Feedback: {stats.last_feedback_at or 'nie'}"
        )
        self._fill_tree(self._tree_pos, stats.top_positive_buckets)
        self._fill_tree(self._tree_neg, stats.top_negative_buckets)
        self.stats_refreshed.emit()

    @staticmethod
    def _fill_tree(tree: QTreeWidget, buckets: list[dict]) -> None:
        tree.clear()
        for b in buckets:
            item = QTreeWidgetItem([
                str(b.get("axis", "")),
                str(b.get("level", "")),
                str(b.get("context_key", ""))[:40],
                f"{float(b.get('alpha', 0.0)):.1f}",
                f"{float(b.get('beta', 0.0)):.1f}",
            ])
            tree.addTopLevelItem(item)

    # --- Reset (two-step) ----------------------------------------------
    def _on_reset_clicked(self) -> None:
        # Step 1: Token holen (BrainV3Service Two-Step-Flow)
        try:
            r1 = self._service.reset(ResetRequest())
        except Exception as exc:
            QMessageBox.critical(self, "Reset fehlgeschlagen", str(exc))
            return
        if r1.status != "token_required" or not r1.confirmation_token:
            QMessageBox.warning(self, "Reset", "Unerwartete Reset-Antwort.")
            return
        token = r1.confirmation_token

        reply = QMessageBox.warning(
            self,
            "Hirn-Store loeschen?",
            "Das loescht alle gelernten Gewichte (axis_weights + pattern_correlations). "
            "Embedding-Cache bleibt erhalten.\n\n"
            f"Confirmation-Token: {token}\n\nFortfahren?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            r2 = self._service.reset(ResetRequest(confirmation_token=token))
        except Exception as exc:
            QMessageBox.critical(self, "Reset fehlgeschlagen", str(exc))
            return
        if r2.status == "reset_done":
            QMessageBox.information(
                self, "Reset abgeschlossen",
                f"Geloescht: {', '.join(r2.cleared_tables)}",
            )
            self.refresh()
            self.reset_done.emit()
        else:
            QMessageBox.warning(self, "Reset", f"Status: {r2.status}")

    def _on_learning_clicked(self) -> None:
        if self._learning_dialog is not None and self._learning_dialog.isVisible():
            self._learning_dialog.raise_()
            self._learning_dialog.activateWindow()
            return
        dlg = BrainV3LearningSessionDialog(
            service=self._service,
            n_samples=15,
            parent=self,
        )
        self._learning_dialog = dlg
        dlg.finished.connect(self._on_learning_finished)
        dlg.open()

    def _on_learning_finished(self) -> None:
        self._learning_dialog = None
        self.refresh()
