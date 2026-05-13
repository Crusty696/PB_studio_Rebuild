"""Action gating for SCHNITT commands."""

from __future__ import annotations

import logging

from database import get_active_project_id
from services.schnitt_context import SchnittDataContext, build_schnitt_context

logger = logging.getLogger(__name__)


class SchnittActionBinder:
    """Keeps SCHNITT command buttons aligned with current project context."""

    def __init__(self, btn_generate, btn_auto_edit, db_engine=None, status_label=None):
        self.btn_generate = btn_generate
        self.btn_auto_edit = btn_auto_edit
        self.db_engine = db_engine
        self.status_label = status_label
        self.context: SchnittDataContext | None = None

    def apply_context(self, context: SchnittDataContext) -> bool:
        self.context = context
        can_run = context.can_auto_edit
        reason = self.block_reason()
        if can_run:
            tooltip = "SCHNITT bereit: Timeline und Auto-Edit koennen gestartet werden."
        else:
            tooltip = f"Nicht bereit: {reason}"
        for button in (self.btn_generate, self.btn_auto_edit):
            button.setEnabled(can_run)
            button.setToolTip(tooltip)
        if self.status_label is not None:
            self.status_label.setText("Timeline bereit" if can_run else f"Blockiert: {reason}")
        return can_run

    def refresh(self, project_id: int | None) -> bool:
        if self.db_engine is None:
            return self.apply_context(_blocked_context("Projekt fehlt"))
        return self.apply_context(build_schnitt_context(self.db_engine, project_id))

    def refresh_current_project(self) -> bool:
        try:
            project_id = get_active_project_id()
        except Exception as exc:
            logger.debug("[SchnittActionBinder] active project unavailable: %s", exc)
            project_id = None
        return self.refresh(project_id)

    def block_reason(self) -> str:
        if self.context is None:
            return "Kontext fehlt"
        if self.context.missing_reasons:
            return "; ".join(self.context.missing_reasons)
        if not self.context.can_auto_edit:
            return "Audio, Video oder Beatgrid fehlt"
        return ""


def _blocked_context(reason: str) -> SchnittDataContext:
    return SchnittDataContext(
        project_id=None,
        project_path=None,
        audio_id=None,
        video_ids=(),
        timeline_entry_count=0,
        has_stems=False,
        has_waveform=False,
        has_beatgrid=False,
        has_video_analysis=False,
        missing_reasons=(reason,),
    )
