"""StatsPanel — Studio Brain "Struktur" tab, library-level stats (T10.2c).

Compact read-out of library structure health:

    - Coverage: total scenes, enriched scenes, coverage percent.
    - Roles:    count per role label (sorted DESC).
    - Moods:    count per mood_refined (sorted DESC).
    - Active style buckets: integer count.
    - Coverage gaps: expected mood labels (from mood_anchors_v1.yaml) that
      currently have ZERO scenes — if none, show "no gaps".

Pure read-view. No interactive elements. No filters. Refresh is driven by
StructureTab.refresh() (which invalidates the BrainService cache first).

Graceful mode: if the underlying DB has no struct_* tables yet (fresh
checkout / unmigrated), `refresh()` catches OperationalError and shows a
terse "Stats unavailable — enrichment has not run." line instead of
crashing the UI.

Deliberately out of scope (later dispatches):
    - Graph mode       → T10.2d.
    - Boost/Exclude    → T10.2e.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QListWidget,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import OperationalError

from services.brain import BrainService

logger = logging.getLogger(__name__)


# ── Layout constants ──────────────────────────────────────────────────────────

_STATS_MIN_WIDTH = 240
_SECTION_LIST_HEIGHT = 96
_UNAVAILABLE_TEXT = "Statistiken nicht verfügbar — Analyse wurde noch nicht ausgeführt."

_STATS_STYLE = (
    "QFrame#StructureStats{background:#131922;"
    "border:1px solid rgba(255,255,255,0.07);border-radius:6px;}"
    "QLabel[role='title']{color:#e5e7eb;font-size:11px;font-weight:700;}"
    "QLabel[role='section']{color:#9ca3af;font-size:10px;font-weight:600;}"
    "QLabel[role='value']{color:#e5e7eb;font-size:10px;}"
    "QLabel[role='muted']{color:#6b7280;font-size:10px;}"
    "QListWidget{background:#0f141d;color:#e5e7eb;font-size:10px;"
    "border:1px solid rgba(255,255,255,0.06);border-radius:4px;}"
)


def _format_pct(fraction: float) -> str:
    try:
        f = float(fraction)
    except (TypeError, ValueError):
        return "— %"
    return f"{int(round(f * 100))}%"


def _format_row(label: str, count: int, total: int) -> str:
    """Return ``"label: N (xx%)"`` — percent is share of ``total``."""
    if total <= 0:
        return f"{label}: {int(count)} (— %)"
    share = int(round((count / total) * 100))
    return f"{label}: {int(count)} ({share}%)"


class StatsPanel(QFrame):
    """Right-side library-level stats readout for the Structure tab.

    Call :meth:`refresh` to re-fetch from BrainService and repaint. The
    widget takes no signals and exposes no interactive controls.
    """

    def __init__(
        self,
        brain_service: BrainService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._svc = brain_service

        self.setObjectName("StructureStats")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(_STATS_MIN_WIDTH)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self.setStyleSheet(_STATS_STYLE)

        self._build()
        self._show_unavailable(False)
        self.refresh()

    # ── UI construction ────────────────────────────────────────────────────
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(4)

        self._title_label = QLabel("Statistik")
        self._title_label.setProperty("role", "title")
        self._title_label.setToolTip(
            "Bibliotheks-Statistik: Wie viele Szenen sind analysiert, "
            "welche Rollen/Stimmungen dominieren, und welche erwarteten "
            "Stimmungs-Anker fehlen noch im Material."
        )
        outer.addWidget(self._title_label)

        # Unavailable / error line (hidden in healthy state).
        self._status_label = QLabel(_UNAVAILABLE_TEXT)
        self._status_label.setProperty("role", "muted")
        self._status_label.setWordWrap(True)
        self._status_label.setVisible(False)
        outer.addWidget(self._status_label)

        # Coverage summary (totals + %).
        self._coverage_label = QLabel("—")
        self._coverage_label.setProperty("role", "value")
        self._coverage_label.setWordWrap(True)
        self._coverage_label.setToolTip(
            "Wie viel Prozent deiner Clips wurden bereits komplett "
            "analysiert (Rolle + Stimmung + Stil-Cluster erkannt)."
        )
        outer.addWidget(self._coverage_label)

        self._buckets_label = QLabel("—")
        self._buckets_label.setProperty("role", "value")
        self._buckets_label.setToolTip(
            "Aktive Stil-Cluster — Gruppen von Clips mit aehnlicher "
            "visueller Sprache. Je mehr Cluster, desto abwechslungsreicher "
            "die Bildsprache."
        )
        outer.addWidget(self._buckets_label)

        # Roles section.
        self._roles_header = QLabel("<b>Rollen</b>")
        self._roles_header.setProperty("role", "section")
        self._roles_header.setTextFormat(Qt.TextFormat.RichText)
        self._roles_header.setToolTip(
            "Verteilung der erkannten Schnitt-Rollen in deiner Bibliothek. "
            "Hero = Hauptakteur, Filler = Ueberbrueckung, Transition = "
            "Bewegung."
        )
        outer.addWidget(self._roles_header)

        self._roles_list = QListWidget(self)
        self._roles_list.setFixedHeight(_SECTION_LIST_HEIGHT)
        self._roles_list.setToolTip(
            "Verteilung der erkannten Schnitt-Rollen: wie viele Szenen "
            "pro Rolle und ihr Anteil."
        )
        outer.addWidget(self._roles_list)

        # Moods section.
        self._moods_header = QLabel("<b>Stimmungen</b>")
        self._moods_header.setProperty("role", "section")
        self._moods_header.setTextFormat(Qt.TextFormat.RichText)
        self._moods_header.setToolTip(
            "Verteilung der Video-Stimmungen. Wenn eine Stimmung dominiert, "
            "wird dein Schnitt eintoenig."
        )
        outer.addWidget(self._moods_header)

        self._moods_list = QListWidget(self)
        self._moods_list.setFixedHeight(_SECTION_LIST_HEIGHT)
        self._moods_list.setToolTip(
            "Verteilung der erkannten Stimmungen: wie viele Szenen pro "
            "Stimmung und ihr Anteil."
        )
        outer.addWidget(self._moods_list)

        # Coverage-gaps section.
        self._gaps_header = QLabel("<b>Fehlende Stimmungen</b>")
        self._gaps_header.setProperty("role", "section")
        self._gaps_header.setTextFormat(Qt.TextFormat.RichText)
        self._gaps_header.setToolTip(
            "Erwartete Stimmungen aus der Konfiguration die KEINE Szenen "
            "haben. Solche Luecken zwingen den Agenten Kompromisse "
            "einzugehen."
        )
        outer.addWidget(self._gaps_header)

        self._gaps_label = QLabel("keine Lücken")
        self._gaps_label.setProperty("role", "value")
        self._gaps_label.setWordWrap(True)
        self._gaps_label.setToolTip(
            "Fehlende Stimmungs-Anker aus der Konfiguration, fuer die du "
            "noch kein Material hast."
        )
        outer.addWidget(self._gaps_label)

        outer.addStretch()

    # ── Public API ─────────────────────────────────────────────────────────
    def refresh(self) -> None:
        """Re-fetch BrainService.structure_stats() and repaint.

        Narrow catch: only ``OperationalError`` (missing tables on a fresh
        DB) is swallowed — any other exception propagates so real failures
        surface loudly. Mirrors the rule in T10.2a's _FilterBar._safe_call.
        """
        try:
            stats = self._svc.structure_stats()
        except OperationalError as exc:
            logger.warning("StatsPanel.refresh: structure_stats failed: %s", exc)
            self._show_unavailable(True)
            return

        self._show_unavailable(False)
        self._render(stats)

    # ── Internal rendering ─────────────────────────────────────────────────
    def _show_unavailable(self, is_unavailable: bool) -> None:
        self._status_label.setVisible(is_unavailable)
        body_widgets = (
            self._coverage_label,
            self._buckets_label,
            self._roles_header,
            self._roles_list,
            self._moods_header,
            self._moods_list,
            self._gaps_header,
            self._gaps_label,
        )
        for w in body_widgets:
            w.setVisible(not is_unavailable)

    def _render(self, stats: dict[str, Any]) -> None:
        total = int(stats.get("total_scenes") or 0)
        enriched = int(stats.get("enriched_scenes") or 0)
        fraction = float(stats.get("coverage_fraction") or 0.0)
        pct_text = "— %" if total == 0 else _format_pct(fraction)
        self._coverage_label.setText(
            f"Szenen: {enriched} analysiert / {total} gesamt  ·  {pct_text}"
        )

        bucket_count = int(stats.get("active_style_buckets") or 0)
        self._buckets_label.setText(f"Aktive Stil-Cluster: {bucket_count}")

        # Roles list.
        self._roles_list.clear()
        role_counts = list(stats.get("role_counts") or [])
        role_total = sum(n for _, n in role_counts)
        if not role_counts:
            self._roles_list.addItem("(keine Rollen)")
        else:
            for label, n in role_counts:
                self._roles_list.addItem(_format_row(str(label), int(n), role_total))

        # Moods list.
        self._moods_list.clear()
        mood_counts = list(stats.get("mood_counts") or [])
        mood_total = sum(n for _, n in mood_counts)
        if not mood_counts:
            self._moods_list.addItem("(keine Stimmungen)")
        else:
            for label, n in mood_counts:
                self._moods_list.addItem(_format_row(str(label), int(n), mood_total))

        # Missing moods.
        missing = list(stats.get("missing_moods") or [])
        if not missing:
            self._gaps_label.setText("keine Lücken")
        else:
            self._gaps_label.setText(", ".join(str(m) for m in missing))
