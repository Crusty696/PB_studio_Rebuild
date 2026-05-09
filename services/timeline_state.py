"""TimelineState — zentraler Snapshot der Timeline für Versionierung (SCHNITT Redesign 2026-05-09).

Task 2.2 des SCHNITT-Workspace-Redesign-Plans (siehe
``docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/02_DATA_SERVICES.md``).

UI-freie Datenrepräsentation der Timeline. Lädt aus ``timeline_entries`` und
persistiert serialisierte Snapshots in ``timeline_snapshots`` (Phase 01 Task 1.2).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from database import engine
from database.models import TimelineEntry, TimelineSnapshot


@dataclass(slots=True)
class ClipEntry:
    entry_id: int
    media_id: int
    track: str
    start: float
    end: Optional[float]
    lane: int
    locked: bool = False
    source_start: float = 0.0
    source_end: Optional[float] = None


@dataclass(slots=True)
class TimelineState:
    project_id: int
    version: int
    clips: list[ClipEntry] = field(default_factory=list)
    snapshot_label: Optional[str] = None

    def lock_count(self) -> int:
        return sum(1 for c in self.clips if c.locked)

    @classmethod
    def load(cls, project_id: int) -> "TimelineState":
        with Session(engine) as s:
            rows = (
                s.query(TimelineEntry)
                .filter_by(project_id=project_id)
                .order_by(TimelineEntry.start_time)
                .all()
            )
            clips = [
                ClipEntry(
                    entry_id=r.id,
                    media_id=r.media_id,
                    track=r.track,
                    start=r.start_time,
                    end=r.end_time,
                    lane=r.lane,
                    locked=bool(r.locked),
                    source_start=r.source_start or 0.0,
                    source_end=r.source_end,
                )
                for r in rows
            ]
            latest = (
                s.query(func.max(TimelineSnapshot.version))
                .filter_by(project_id=project_id)
                .scalar()
            ) or 0
        return cls(project_id=project_id, version=latest, clips=clips)

    def save_snapshot(self, label: str) -> int:
        # ``slots=True`` Dataclasses haben kein ``__dict__`` — ``asdict`` ist Pflicht.
        payload = json.dumps([asdict(c) for c in self.clips])
        with Session(engine) as s:
            current = (
                s.query(func.max(TimelineSnapshot.version))
                .filter_by(project_id=self.project_id)
                .scalar()
            ) or 0
            snap = TimelineSnapshot(
                project_id=self.project_id,
                version=current + 1,
                label=label,
                payload_json=payload,
            )
            s.add(snap)
            s.commit()
            return snap.id
