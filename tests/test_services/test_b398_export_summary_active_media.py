from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_b398_summary_counts_only_exportable_video_entries(monkeypatch):
    """B-398: Nur Eintraege zaehlen, deren Medium existiert und nicht
    soft-deleted ist.

    virt-M4-Nachzug 2026-07-10: get_timeline_summary nutzt jetzt reine
    Spalten-Queries (der deleted_at-Filter laeuft in SQL) — der alte
    Fake-Session-Mock konnte query(Col, Col, Col) nicht abbilden. Test
    laeuft jetzt gegen eine echte In-Memory-SQLite mit den realen Models.
    """
    from services import export_service as exp
    from database.models import Base, Project, TimelineEntry, VideoClip

    eng = create_engine("sqlite://")
    Base.metadata.create_all(eng)
    with Session(eng) as s:
        s.add(Project(id=1, name="b398", path="/tmp/b398"))
        s.flush()
        s.add_all([
            VideoClip(id=1, project_id=1, file_path="a.mp4"),
            VideoClip(id=2, project_id=1, file_path="b.mp4",
                      deleted_at=datetime(2026, 5, 26, tzinfo=timezone.utc)),
        ])
        s.add_all([
            # exportierbar: Medium 1 existiert, nicht geloescht
            TimelineEntry(project_id=1, track="video", media_id=1,
                          start_time=0.0, end_time=1.0),
            # NICHT exportierbar: Medium 2 ist soft-deleted
            TimelineEntry(project_id=1, track="video", media_id=2,
                          start_time=1.0, end_time=2.0),
            # NICHT exportierbar: Medium 3 existiert nicht
            TimelineEntry(project_id=1, track="video", media_id=3,
                          start_time=2.0, end_time=3.0),
        ])
        s.commit()

    monkeypatch.setattr(exp, "engine", eng)

    summary = exp.get_timeline_summary(project_id=1)

    assert summary["video_clips"] == 1
    assert summary["audio_tracks"] == 0
    assert summary["total_entries"] == 1
    assert summary["estimated_duration"] == 1.0
