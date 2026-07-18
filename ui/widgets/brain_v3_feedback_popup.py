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
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.brain.brain_v3_service import BrainV3Service
from services.brain.context_resolver import CutContext
from services.brain.schemas.brain_v3_schemas import FeedbackRequest
from services.brain.weight_store import WeightStore
from workers.base import BaseWorker, run_worker

logger = logging.getLogger(__name__)


def build_thread_local_brain_service(src):
    """Frische, thread-lokale BrainV3Service-Instanz fuer Worker-Threads.

    WeightStore haelt eine gecachte sqlite3-Connection, die thread-local ist.
    Eine im GUI-Thread konstruierte Service-Instanz darf deshalb NICHT aus
    einem Worker-Thread benutzt werden — sonst sqlite3.ProgrammingError. Pro
    Worker daher eine eigene Instanz auf denselben DB-Pfaden bauen.
    """
    if src is None:
        return BrainV3Service()
    brain = getattr(src, "_brain_store", None)
    if brain is None:
        return BrainV3Service()
    # BrainStore wiederverwenden: oeffnet Connections per-Call (thread-safe) und
    # haelt keine gecachte Connection -> kein Re-Migrate pro Feedback-Klick. Nur
    # WeightStore muss frisch sein (cached sqlite3-Connection ist thread-local).
    return BrainV3Service(
        brain_store=brain,
        weight_store=WeightStore(brain.weights_path),
        project_root=getattr(src, "_project_root", None),
        session_factory=getattr(src, "_session_factory", None),
    )


class _FeedbackSubmitWorker(BaseWorker):
    """Schreibt einen Feedback-Klick (102 Bucket-UPSERTs) off-thread."""

    def __init__(self, service, cut_id: int, rating: str, context):
        super().__init__()
        self._src = service
        self._cut_id = int(cut_id)
        self._rating = rating
        self._context = context

    def _do_work(self):
        svc = build_thread_local_brain_service(self._src)
        try:
            resp = svc.feedback(
                FeedbackRequest(cut_id=self._cut_id, rating=self._rating),
                context=self._context,
            )
            return {
                "cut_id": self._cut_id,
                "rating": self._rating,
                "n_buckets": resp.n_buckets_updated,
            }
        finally:
            try:
                svc._weight_store.close()
            except Exception:
                pass


# Plan-Doc 06 Z.414-417: 4-Klick-Mapping
FEEDBACK_BUTTONS: list[tuple[str, str, str]] = [
    # (rating-key, label, button-style)
    ("perfect",   "1 — Passt perfekt",   "background: #1d6e2a; color: white;"),
    ("fits",      "2 — Passt",           "background: #2a6e5d; color: white;"),
    ("not_quite", "3 — Passt nicht ganz","background: #6e561d; color: white;"),
    ("no_match",  "4 — Passt gar nicht", "background: #6e1f1f; color: white;"),
]

# Separates Dict statt 4. Tupel-Element: FEEDBACK_BUTTONS wird als 3er-Tupel
# entpackt (auch in _wire_hotkeys) — Struktur nicht anfassen.
FEEDBACK_TOOLTIPS: dict[str, str] = {
    "perfect":   "Bewertung 1 (Hotkey 1): Cut passt perfekt zur Musik. "
                 "Erhoeht das Vertrauen des Brains in diese Kombination stark.",
    "fits":      "Bewertung 2 (Hotkey 2): Cut passt gut. "
                 "Erhoeht das Vertrauen des Brains leicht.",
    "not_quite": "Bewertung 3 (Hotkey 3): Cut passt nicht ganz. "
                 "Senkt das Vertrauen des Brains leicht.",
    "no_match":  "Bewertung 4 (Hotkey 4): Cut passt gar nicht. "
                 "Senkt das Vertrauen des Brains stark.",
}


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
        self._service = service
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

        self._rating_buttons: list[QPushButton] = []
        for rating, label, style in FEEDBACK_BUTTONS:
            btn = QPushButton(label)
            btn.setStyleSheet(
                style
                + " padding: 6px 10px; border-radius: 4px; font-weight: 600;"
            )
            btn.setToolTip(FEEDBACK_TOOLTIPS[rating])
            btn.clicked.connect(lambda _checked=False, r=rating: self._submit(r))
            root.addWidget(btn)
            self._rating_buttons.append(btn)

        cancel_row = QHBoxLayout()
        cancel_row.addStretch(1)
        cancel = QPushButton("Abbrechen (Esc)")
        cancel.setToolTip(
            "Dialog ohne Bewertung schliessen (Esc). Es wird kein Feedback gespeichert."
        )
        cancel.clicked.connect(self.reject)
        cancel_row.addWidget(cancel)
        root.addLayout(cancel_row)

    def _wire_hotkeys(self) -> None:
        # Hotkey 1-4 -> sofort senden
        for idx, (rating, _label, _style) in enumerate(FEEDBACK_BUTTONS, start=1):
            sc = QShortcut(QKeySequence(str(idx)), self)
            sc.activated.connect(lambda r=rating: self._submit(r))

    def _submit(self, rating: str) -> None:
        # B-336-Freeze: DB-Write (102 Bucket-UPSERTs, ~3s unter Lock) lief
        # synchron auf dem GUI-Thread -> weisser Bildschirm. Jetzt off-thread.
        self._set_buttons_enabled(False)
        worker = _FeedbackSubmitWorker(self._service, self._cut_id, rating, self._context)
        run_worker(self, worker, on_finish=self._on_submit_done, on_error=self._on_submit_error)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for btn in getattr(self, "_rating_buttons", []):
            btn.setEnabled(enabled)

    def _on_submit_done(self, payload: dict) -> None:
        self.feedback_submitted.emit(
            int(payload["cut_id"]), str(payload["rating"]), int(payload["n_buckets"])
        )
        self.accept()

    def _on_submit_error(self, msg: str) -> None:
        logger.warning("Brain-V3-Feedback fehlgeschlagen: %s", msg)
        self._set_buttons_enabled(True)
        self.reject()


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
