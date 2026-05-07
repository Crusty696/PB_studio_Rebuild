"""Brain V3 — Feedback-Popup mit 4 Buttons (Phase 5, 06_PHASES.md Z.414-417).

QDialog/QMenu mit:
    1. „Passt perfekt"   (Hotkey 1, alpha+=2.0)
    2. „Passt"            (Hotkey 2, alpha+=1.0)
    3. „Passt nicht ganz" (Hotkey 3, beta+=1.0)
    4. „Passt gar nicht"  (Hotkey 4, beta+=2.0)

Nutzt `BrainV3Service.feedback()` direkt — keine Abhaengigkeit von
Timeline-Item-Geometrie. Caller uebergibt cut_id + optional CutContext.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.brain_v3.brain_v3_service import BrainV3Service
from services.brain_v3.context_resolver import CutContext
from services.brain_v3.schemas.brain_v3_schemas import FeedbackRequest

logger = logging.getLogger(__name__)


# Plan-Doc 06 Z.414-417: 4-Klick-Mapping
FEEDBACK_BUTTONS: list[tuple[str, str, str]] = [
    # (rating-key, label, button-style)
    ("perfect",   "1 — Passt perfekt",   "background: #1d6e2a; color: white;"),
    ("fits",      "2 — Passt",           "background: #2a6e5d; color: white;"),
    ("not_quite", "3 — Passt nicht ganz","background: #6e561d; color: white;"),
    ("no_match",  "4 — Passt gar nicht", "background: #6e1f1f; color: white;"),
]


class BrainV3FeedbackPopup(QDialog):
    """Modal Popup mit 4 Bewertungs-Buttons + Hotkey 1-4."""

    feedback_submitted = Signal(int, str, int)  # cut_id, rating, n_buckets_updated

    def __init__(
        self,
        cut_id: int,
        service: Optional[BrainV3Service] = None,
        context: Optional[CutContext] = None,
        cut_label: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._cut_id = int(cut_id)
        self._service = service or BrainV3Service()
        self._context = context
        self.setWindowTitle("Brain V3 — Cut bewerten")
        self.setModal(True)
        self.setMinimumWidth(360)
        self._build_ui(cut_label)
        self._wire_hotkeys()

    def _build_ui(self, cut_label: Optional[str]) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        title = QLabel(cut_label or f"Cut #{self._cut_id}")
        title.setStyleSheet("font-weight: 600; font-size: 13px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        sub = QLabel("Wie passt dieser Cut zur Musik?")
        sub.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 11px;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(sub)

        for rating, label, style in FEEDBACK_BUTTONS:
            btn = QPushButton(label)
            btn.setStyleSheet(
                style
                + " padding: 6px 10px; border-radius: 4px; font-weight: 600;"
            )
            btn.clicked.connect(lambda _checked=False, r=rating: self._submit(r))
            root.addWidget(btn)

        cancel_row = QHBoxLayout()
        cancel_row.addStretch(1)
        cancel = QPushButton("Abbrechen (Esc)")
        cancel.clicked.connect(self.reject)
        cancel_row.addWidget(cancel)
        root.addLayout(cancel_row)

    def _wire_hotkeys(self) -> None:
        # Hotkey 1-4 -> sofort senden
        for idx, (rating, _label, _style) in enumerate(FEEDBACK_BUTTONS, start=1):
            sc = QShortcut(QKeySequence(str(idx)), self)
            sc.activated.connect(lambda r=rating: self._submit(r))

    def _submit(self, rating: str) -> None:
        try:
            resp = self._service.feedback(
                FeedbackRequest(cut_id=self._cut_id, rating=rating),
                context=self._context,
            )
        except Exception as exc:
            logger.warning("Brain-V3-Feedback fehlgeschlagen: %s", exc)
            self.reject()
            return
        self.feedback_submitted.emit(self._cut_id, rating, resp.n_buckets_updated)
        self.accept()


def confidence_color_hex(confidence: float) -> str:
    """Confidence 0..1 -> Farb-Hex (rot=unsicher, gruen=sicher).

    Plan-Doc 06 Phase 5 Z.429-432: dünner Balken über jedem Cut.
    """
    c = max(0.0, min(1.0, float(confidence)))
    # Linear interpolate red -> yellow -> green
    if c < 0.5:
        # red->yellow
        r = 255
        g = int(255 * (c * 2))
    else:
        r = int(255 * (1 - (c - 0.5) * 2))
        g = 255
    return f"#{r:02x}{g:02x}30"
