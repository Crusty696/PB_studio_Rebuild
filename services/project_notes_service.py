"""Service für Projekt-Notes (Sub-Tab "RL & Notes"). SCHNITT Redesign 2026-05-09 Task 2.4.

Hinweis: Plan-Spec (02_DATA_SERVICES.md) referenziert `database.session.DBSession`,
das im Repo nicht existiert. Wir nutzen `sqlalchemy.orm.Session` analog zu
`services/timeline_snapshot_service.py` und `services/timeline_state.py`.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import engine
from database.models import ProjectNote


def get_notes(project_id: int) -> str:
    """Liefert content_md des ProjectNote-Eintrags oder "" wenn keiner existiert."""
    with Session(engine) as s:
        row = s.query(ProjectNote).filter_by(project_id=project_id).one_or_none()
        return row.content_md if row else ""


def update_notes(project_id: int, content_md: str) -> None:
    """Schreibt content_md. Erstellt Row, falls noch keine existiert (1:1)."""
    with Session(engine) as s:
        row = s.query(ProjectNote).filter_by(project_id=project_id).one_or_none()
        if row is None:
            s.add(ProjectNote(project_id=project_id, content_md=content_md))
        else:
            row.content_md = content_md
        s.commit()
