"""Service für persistente Timeline-Snapshots (Hybrid-Undo). SCHNITT Redesign 2026-05-09."""
from __future__ import annotations
import json
from sqlalchemy.orm import Session

from database import engine
from database.models import TimelineEntry, TimelineSnapshot
from services.timeline_state import TimelineState


def create_snapshot(project_id: int, label: str) -> int:
    """Lädt aktuellen TimelineState und persistiert als Snapshot. Gibt snap.id zurück."""
    state = TimelineState.load(project_id)
    return state.save_snapshot(label)


def list_snapshots(project_id: int) -> list[TimelineSnapshot]:
    """Listet alle Snapshots eines Projekts, sortiert nach version ASC."""
    with Session(engine) as s:
        return (
            s.query(TimelineSnapshot)
            .filter_by(project_id=project_id)
            .order_by(TimelineSnapshot.version.asc())
            .all()
        )


def restore_snapshot(snapshot_id: int) -> None:
    """Stellt Timeline-State aus Snapshot wieder her — löscht alle aktuellen
    TimelineEntries des Projekts und schreibt die im Payload referenzierten."""
    with Session(engine) as s:
        snap = s.get(TimelineSnapshot, snapshot_id)
        if snap is None:
            raise ValueError(f"Snapshot {snapshot_id} not found")
        clips = json.loads(snap.payload_json)
        s.query(TimelineEntry).filter_by(project_id=snap.project_id).delete()
        for c in clips:
            s.add(TimelineEntry(
                project_id=snap.project_id,
                track=c["track"],
                media_id=c["media_id"],
                start_time=c["start"],
                end_time=c["end"],
                lane=c["lane"],
                source_start=c.get("source_start", 0.0),
                source_end=c.get("source_end"),
                locked=c.get("locked", False),
            ))
        s.commit()
