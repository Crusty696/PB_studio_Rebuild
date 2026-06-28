"""InspectorPanel — Studio Brain "Struktur" tab, right-side detail panel (T10.2b).

Shows rich per-clip detail for the currently-selected scene card:

    - Header: scene_id, source video basename, start–end time (mm:ss.xx).
    - Role  label + confidence (as percentage).
    - Mood  label + confidence (as percentage).
    - Style bucket + style_distance (3 decimals).
    - Neighbors: top-5 nearest clips by cosine similarity, ordered by
      rank_in_a ASC. Each row shows scene_id, similarity, and the neighbor's
      role/mood (or "—" if the neighbor has no struct_clip_tags yet).
    - Historical usage: N cuts (never used / N cuts + last run timestamp).

Populates via a single BrainService.get_clip_detail(scene_id) call — no
additional DB traffic per-field.

Deliberately out of scope (later dispatches):
    - Stats panel      → T10.2c.
    - Graph mode       → T10.2d.
    - Boost/Exclude    → T10.2e.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy.exc import OperationalError

from services.brain import BrainService

logger = logging.getLogger(__name__)


# ── Layout constants ──────────────────────────────────────────────────────────

_INSPECTOR_MIN_WIDTH = 240
_NEIGHBOR_LIST_HEIGHT = 110
_PLACEHOLDER_TEXT = "Wähle einen Clip aus, um Details zu sehen."

_INSPECTOR_STYLE = (
    "QFrame#StructureInspector{background:#131922;"
    "border:1px solid rgba(255,255,255,0.07);border-radius:6px;}"
    "QLabel[role='title']{color:#e5e7eb;font-size:11px;font-weight:700;}"
    "QLabel[role='status']{color:#9ca3af;font-size:10px;}"
    "QLabel[role='value']{color:#e5e7eb;font-size:10px;}"
    "QLabel[role='key']{color:#9ca3af;font-size:10px;}"
    "QListWidget{background:#0f141d;color:#e5e7eb;font-size:10px;"
    "border:1px solid rgba(255,255,255,0.06);border-radius:4px;}"
)


def _format_mmssxx(seconds: float) -> str:
    """Format a float second count as mm:ss.xx."""
    try:
        s = float(seconds)
    except (TypeError, ValueError):
        return "--:--.--"
    if s < 0.0:
        s = 0.0
    m = int(s // 60)
    rem = s - (m * 60)
    return f"{m:02d}:{rem:05.2f}"


def _format_confidence_pct(conf: Optional[float]) -> str:
    try:
        c = float(conf or 0.0)
    except (TypeError, ValueError):
        c = 0.0
    return f"{int(round(c * 100))}%"


def _format_with_conf(label: Optional[str], conf: Optional[float]) -> str:
    if not label:
        return "—"
    return f"{label} — {_format_confidence_pct(conf)}"


class InspectorPanel(QFrame):
    """Right-side detail panel for the Structure tab.

    Call `populate(scene_id)` to fetch + render detail for a scene. Call
    `clear()` to return to the empty-state placeholder.
    """

    def __init__(
        self,
        brain_service: BrainService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._svc = brain_service
        self._scene_id: Optional[int] = None

        self.setObjectName("StructureInspector")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumWidth(_INSPECTOR_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(_INSPECTOR_STYLE)

        self._build()
        self.clear()

    # ── UI construction ────────────────────────────────────────────────────
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # Title + status line (doubles as placeholder / error line).
        self._title_label = QLabel("Inspector")
        self._title_label.setProperty("role", "title")
        self._title_label.setToolTip(
            "Details zur aktuell ausgewaehlten Szene: Rolle, Stimmung, "
            "Stil, aehnliche Szenen und wie oft sie bisher verwendet wurde."
        )
        outer.addWidget(self._title_label)

        self._status_label = QLabel(_PLACEHOLDER_TEXT)
        self._status_label.setProperty("role", "status")
        self._status_label.setWordWrap(True)
        outer.addWidget(self._status_label)

        # Structured key/value form (hidden in empty state).
        self._form_widget = QWidget(self)
        form = QFormLayout(self._form_widget)
        form.setContentsMargins(0, 2, 0, 2)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(3)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self._scene_id_label = self._make_value_label()
        self._video_label = self._make_value_label()
        self._time_label = self._make_value_label()
        self._role_label = self._make_value_label()
        self._mood_label = self._make_value_label()
        self._style_label = self._make_value_label()
        self._usage_label = self._make_value_label()

        form.addRow(self._make_key_label("Szene:"), self._scene_id_label)
        form.addRow(self._make_key_label("Video:"), self._video_label)
        form.addRow(self._make_key_label("Zeit:"), self._time_label)
        form.addRow(self._make_key_label("Rolle:"), self._role_label)
        form.addRow(self._make_key_label("Stimmung:"), self._mood_label)
        form.addRow(self._make_key_label("Stil:"), self._style_label)
        _usage_key = self._make_key_label("Nutzung:")
        form.addRow(_usage_key, self._usage_label)
        _usage_tooltip = (
            "Wie oft diese Szene in frueheren Pacing-Runs geschnitten wurde, "
            "und wann sie zuletzt in einem abgeschlossenen Run gelandet ist."
        )
        _usage_key.setToolTip(_usage_tooltip)
        self._usage_label.setToolTip(_usage_tooltip)

        outer.addWidget(self._form_widget)

        # Neighbors list.
        self._neighbors_title = QLabel("Ähnliche Szenen (Top 5)")
        self._neighbors_title.setProperty("role", "key")
        self._neighbors_title.setToolTip(
            "Die 5 aehnlichsten Szenen (cosine similarity der "
            "Bildeinbettung). Jede Zeile: Szenen-ID, Aehnlichkeit, "
            "Rolle/Stimmung."
        )
        outer.addWidget(self._neighbors_title)

        self._neighbors_list = QListWidget(self)
        self._neighbors_list.setFixedHeight(_NEIGHBOR_LIST_HEIGHT)
        self._neighbors_list.setToolTip(
            "Die 5 aehnlichsten Szenen (cosine similarity der "
            "Bildeinbettung). Jede Zeile: Szenen-ID, Aehnlichkeit, "
            "Rolle/Stimmung."
        )
        outer.addWidget(self._neighbors_list)

        outer.addStretch()

    @staticmethod
    def _make_key_label(text_value: str) -> QLabel:
        lbl = QLabel(text_value)
        lbl.setProperty("role", "key")
        return lbl

    @staticmethod
    def _make_value_label() -> QLabel:
        lbl = QLabel("—")
        lbl.setProperty("role", "value")
        lbl.setWordWrap(True)
        return lbl

    # ── Public API ─────────────────────────────────────────────────────────
    def populate(self, scene_id: int) -> None:
        """Fetch `scene_id` detail from BrainService and paint the panel.

        Graceful modes:
          - BrainService returns None (no tags row yet) → placeholder text
            "Scene #N: not enriched yet".
          - Underlying DB layer raises OperationalError (unmigrated schema)
            → keep UI mountable; show a terse warning line.
        """
        try:
            sid = int(scene_id)
        except (TypeError, ValueError):
            logger.warning("InspectorPanel.populate: bad scene_id=%r", scene_id)
            return

        self._scene_id = sid

        try:
            detail = self._svc.get_clip_detail(sid)
        except OperationalError as exc:
            logger.warning(
                "InspectorPanel.populate: get_clip_detail failed: %s", exc
            )
            self._show_placeholder(
                f"Szene #{sid}: Details noch nicht verfügbar "
                "(Datenbank noch nicht bereit)."
            )
            return

        if detail is None:
            self._show_placeholder(
                f"Szene #{sid}: noch nicht analysiert."
            )
            return

        self._render_detail(detail)

    def clear(self) -> None:
        """Reset the panel to its empty-state placeholder."""
        self._scene_id = None
        self._show_placeholder(_PLACEHOLDER_TEXT)

    # ── Internal rendering ─────────────────────────────────────────────────
    def _show_placeholder(self, message: str) -> None:
        self._status_label.setText(message)
        self._status_label.setVisible(True)
        self._form_widget.setVisible(False)
        self._neighbors_title.setVisible(False)
        self._neighbors_list.setVisible(False)
        self._neighbors_list.clear()

    def _render_detail(self, detail: dict[str, Any]) -> None:
        self._status_label.setVisible(False)
        self._form_widget.setVisible(True)
        self._neighbors_title.setVisible(True)
        self._neighbors_list.setVisible(True)

        sid = int(detail["scene_id"])
        self._scene_id_label.setText(f"#{sid}")

        basename = detail.get("video_file_basename") or "—"
        self._video_label.setText(str(basename))

        t_start = float(detail.get("start_time") or 0.0)
        t_end = float(detail.get("end_time") or 0.0)
        self._time_label.setText(
            f"{_format_mmssxx(t_start)} – {_format_mmssxx(t_end)}"
        )

        self._role_label.setText(
            _format_with_conf(detail.get("role"), detail.get("role_confidence"))
        )
        self._mood_label.setText(
            _format_with_conf(
                detail.get("mood_refined"), detail.get("mood_confidence")
            )
        )

        bucket_name = detail.get("style_bucket_name")
        style_distance = float(detail.get("style_distance") or 0.0)
        if bucket_name:
            self._style_label.setText(
                f"{bucket_name}  (d={style_distance:.3f})"
            )
        elif detail.get("style_bucket_id") is not None:
            self._style_label.setText(
                f"Bucket #{detail['style_bucket_id']}  (d={style_distance:.3f})"
            )
        else:
            self._style_label.setText(f"—  (d={style_distance:.3f})")

        self._usage_label.setText(self._format_usage(detail))

        # Repopulate neighbors.
        self._neighbors_list.clear()
        neighbors = detail.get("neighbors") or []
        if not neighbors:
            empty = QListWidgetItem("(keine ähnlichen Szenen)")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self._neighbors_list.addItem(empty)
        else:
            for n in neighbors:
                self._neighbors_list.addItem(self._format_neighbor(n))

    @staticmethod
    def _format_usage(detail: dict[str, Any]) -> str:
        count = int(detail.get("usage_count") or 0)
        if count == 0:
            return "noch nie verwendet"
        last = detail.get("last_run_completed_at")
        if last:
            return f"{count} Schnitte · letzter Lauf: {last}"
        return f"{count} Schnitte, letzter Lauf: —"

    @staticmethod
    def _format_neighbor(n: dict[str, Any]) -> str:
        sid = int(n.get("scene_id") or 0)
        sim = float(n.get("cosine_similarity") or 0.0)
        role = n.get("role") or "—"
        mood = n.get("mood_refined") or "—"
        return f"#{sid}  {sim:.3f}  ·  {role} / {mood}"
