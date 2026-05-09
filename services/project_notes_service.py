"""Service für Projekt-Notes (Sub-Tab "RL & Notes"). SCHNITT Redesign 2026-05-09 Task 2.4.

Hinweis: Plan-Spec (02_DATA_SERVICES.md) referenziert `database.session.DBSession`,
das im Repo nicht existiert. Wir nutzen `sqlalchemy.orm.Session` analog zu
`services/timeline_snapshot_service.py` und `services/timeline_state.py`.

T4.1 (2026-05-09): ``update_notes`` als SQLite-Upsert (atomar, kein TOCTOU).
T4.2 (2026-05-09): ``update_notes`` liefert ``updated_at`` zurück.
"""
from __future__ import annotations

import datetime as _datetime

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from database import engine
from database.models import ProjectNote


def get_notes(project_id: int) -> str:
    """Liefert content_md des ProjectNote-Eintrags oder "" wenn keiner existiert."""
    with Session(engine) as s:
        row = s.query(ProjectNote).filter_by(project_id=project_id).one_or_none()
        return row.content_md if row else ""


def update_notes(project_id: int, content_md: str) -> _datetime.datetime:
    """Schreibt content_md. Erstellt Row falls keine existiert (1:1).

    Atomar via SQLite ``ON CONFLICT DO UPDATE`` — kein TOCTOU-Race
    zwischen ``SELECT`` und ``INSERT/UPDATE``.

    Returns:
        ``updated_at`` der geschriebenen Row (UTC, naive datetime).
    """
    now = _datetime.datetime.utcnow()
    with Session(engine) as s:
        stmt = sqlite_insert(ProjectNote).values(
            project_id=project_id,
            content_md=content_md,
            updated_at=now,
        ).on_conflict_do_update(
            index_elements=["project_id"],
            set_=dict(content_md=content_md, updated_at=now),
        )
        s.execute(stmt)
        s.commit()
    return now
