"""B-706/M1: Restore aus dem Papierkorb stellt die Timeline-Platzierung wieder her.

Vorher: delete_selected_media loescht TimelineEntry+ClipAnchor physisch,
restore_media setzte nur deleted_at=NULL -> Clip kehrte ohne Timeline-Position
zurueck (stiller Verlust). Jetzt: Soft-Delete sichert die Platzierung, Restore
legt sie neu an.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import (
    AudioTrack, ClipAnchor, Project, TimelineEntry, VideoClip,
)


class _FakeVectorDB:
    def delete_all(self):
        return None

    def delete_by_clip_ids(self, clip_ids):
        return None


def _active_timeline_entries(session, track, media_id):
    return session.query(TimelineEntry).filter(
        TimelineEntry.track == track,
        TimelineEntry.media_id == media_id,
    ).all()


def test_b706_m1_restore_reconstructs_timeline_entry_and_anchor(test_engine, monkeypatch):
    import services.ingest_service as ingest_service
    monkeypatch.setattr(ingest_service, "VectorDBService", _FakeVectorDB)

    with Session(test_engine) as session:
        project = Project(name="P", path=".")
        session.add(project)
        session.flush()
        pid = project.id

        video = VideoClip(project_id=pid, file_path="/tmp/v.mp4", width=1920, height=1080)
        audio = AudioTrack(project_id=pid, file_path="/tmp/a.wav", title="t")
        session.add_all([video, audio])
        session.flush()
        vid, aid = video.id, audio.id

        # Distinktive Timeline-Platzierung fuer das Video + ein Anchor.
        ventry = TimelineEntry(
            project_id=pid, track="video", media_id=vid,
            start_time=5.0, end_time=8.0, lane=2,
            crossfade_duration=0.5, source_start=1.0, source_end=4.0,
            brightness=0.1, contrast=1.3, locked=True,
        )
        session.add(ventry)
        session.flush()
        session.add(ClipAnchor(
            timeline_entry_id=ventry.id, time_offset=1.5, label="MARK", color="#00FF00",
        ))
        # Audio ebenfalls platziert.
        session.add(TimelineEntry(
            project_id=pid, track="audio", media_id=aid,
            start_time=0.0, end_time=6.0, lane=0,
        ))
        session.commit()

    # ── Soft-Delete: Timeline-Rows verschwinden physisch ──
    ingest_service.delete_selected_media([vid], [aid])
    with Session(test_engine) as session:
        assert _active_timeline_entries(session, "video", vid) == []
        assert _active_timeline_entries(session, "audio", aid) == []

    # ── Restore: Platzierung + Anchor kommen zurueck ──
    ingest_service.restore_media([vid], [aid])
    with Session(test_engine) as session:
        ventries = _active_timeline_entries(session, "video", vid)
        assert len(ventries) == 1, "Timeline-Platzierung nach Restore nicht wiederhergestellt (B-706/M1)"
        e = ventries[0]
        assert e.start_time == 5.0 and e.end_time == 8.0 and e.lane == 2
        assert e.crossfade_duration == 0.5
        assert e.source_start == 1.0 and e.source_end == 4.0
        assert bool(e.locked) is True
        anchors = session.query(ClipAnchor).filter(
            ClipAnchor.timeline_entry_id == e.id
        ).all()
        assert len(anchors) == 1, "ClipAnchor nach Restore fehlt"
        assert anchors[0].time_offset == 1.5 and anchors[0].label == "MARK"

        aentries = _active_timeline_entries(session, "audio", aid)
        assert len(aentries) == 1 and aentries[0].end_time == 6.0


def test_b706_m1_purge_removes_backup_no_resurrection(test_engine, monkeypatch):
    """Nach Purge darf ein Restore die Platzierung NICHT wieder auferstehen lassen."""
    import services.ingest_service as ingest_service
    monkeypatch.setattr(ingest_service, "VectorDBService", _FakeVectorDB)

    with Session(test_engine) as session:
        project = Project(name="P", path=".")
        session.add(project)
        session.flush()
        pid = project.id
        video = VideoClip(project_id=pid, file_path="/tmp/v.mp4", width=1920, height=1080)
        session.add(video)
        session.flush()
        vid = video.id
        session.add(TimelineEntry(
            project_id=pid, track="video", media_id=vid,
            start_time=3.0, end_time=4.0, lane=1,
        ))
        session.commit()

    ingest_service.delete_selected_media([vid], [])
    ingest_service.purge_soft_deleted_media(pid)

    # Backup ist mit-gepurged -> ein (hypothetischer) Restore findet nichts.
    ingest_service.restore_media([vid], [])
    with Session(test_engine) as session:
        assert _active_timeline_entries(session, "video", vid) == [], (
            "Purge hat das Timeline-Backup nicht mitgeraeumt -> Resurrection"
        )
