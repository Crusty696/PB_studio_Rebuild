"""Audio-Re-Import muss das verbrauchte Timeline-Backup entfernen.

Befund (Audit 2026-07-27, Bereich db-persistenz, bestaetigt):
``ingest_video`` loescht beim Re-Import nach Soft-Delete die zugehoerige
``SoftDeleteTimelineBackup``-Zeile (Commit 7e156fe), ``ingest_audio`` nicht.
Folge-Kette: Delete -> Re-Import (Backup bleibt liegen) -> erneuter Delete ohne
TimelineEntries (``if entries:`` greift nicht, Alt-Backup bleibt) -> Restore aus
dem Papierkorb legt die ALTEN TimelineEntries neu an. Der Audio-Track landet an
einer Position, die der User im aktuellen Stand nie gesetzt hat.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import database
from database import AudioTrack, Project, SoftDeleteTimelineBackup, VideoClip


@pytest.fixture
def seeded(db_session, monkeypatch):
    """Projekt + soft-geloeschtes Medium je Typ, plus passende Backup-Zeilen."""
    import services.ingest_service as ingest_service

    # Der Reuse-Check laeuft best-effort gegen den GLOBALEN Storage-Root.
    # Fuer diesen Test irrelevant und soll nicht nach draussen greifen.
    monkeypatch.setattr(
        ingest_service, "_apply_cross_project_reuse_after_ingest",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(ingest_service, "_invalidate_pacing_caches", lambda: None)

    project = Project(name="P", path="/tmp/p", resolution="1920x1080", fps=30.0)
    db_session.add(project)
    db_session.commit()
    return {"session": db_session, "project": project, "module": ingest_service}


def _backup_count(session, media_type: str, media_id: int) -> int:
    return (
        session.query(SoftDeleteTimelineBackup)
        .filter(
            SoftDeleteTimelineBackup.media_type == media_type,
            SoftDeleteTimelineBackup.media_id == media_id,
        )
        .count()
    )


def test_audio_reimport_clears_soft_delete_backup(seeded, tmp_path: Path) -> None:
    session = seeded["session"]
    project = seeded["project"]
    ingest_service = seeded["module"]

    source = tmp_path / "track.mp3"
    source.write_bytes(b"audio")
    resolved = str(source.resolve())

    track = AudioTrack(project_id=project.id, file_path=resolved, title="track")
    from datetime import datetime

    track.deleted_at = datetime.utcnow()
    session.add(track)
    session.commit()

    session.add(
        SoftDeleteTimelineBackup(
            project_id=project.id,
            media_type="audio",
            media_id=track.id,
            payload_json="[{}]",
        )
    )
    session.commit()
    assert _backup_count(session, "audio", track.id) == 1

    result = ingest_service.ingest_audio(resolved, project_id=project.id)

    assert result is not None
    assert result.deleted_at is None
    assert _backup_count(session, "audio", track.id) == 0, (
        "Re-Import hat das verbrauchte Timeline-Backup liegen lassen — ein "
        "spaeteres Restore legt die alten TimelineEntries erneut an."
    )


def test_audio_reimport_keeps_backup_of_other_media(seeded, tmp_path: Path) -> None:
    """Gegenprobe: nur die Zeile DIESES Mediums darf verschwinden."""
    session = seeded["session"]
    project = seeded["project"]
    ingest_service = seeded["module"]

    from datetime import datetime

    source = tmp_path / "track.mp3"
    source.write_bytes(b"audio")
    resolved = str(source.resolve())
    track = AudioTrack(project_id=project.id, file_path=resolved, title="t")
    track.deleted_at = datetime.utcnow()
    other = AudioTrack(project_id=project.id, file_path=str(tmp_path / "b.mp3"), title="b")
    clip = VideoClip(project_id=project.id, file_path=str(tmp_path / "c.mp4"))
    session.add_all([track, other, clip])
    session.commit()

    for media_type, media_id in (("audio", track.id), ("audio", other.id), ("video", clip.id)):
        session.add(
            SoftDeleteTimelineBackup(
                project_id=project.id,
                media_type=media_type,
                media_id=media_id,
                payload_json="[{}]",
            )
        )
    session.commit()

    ingest_service.ingest_audio(resolved, project_id=project.id)

    assert _backup_count(session, "audio", track.id) == 0
    assert _backup_count(session, "audio", other.id) == 1
    assert _backup_count(session, "video", clip.id) == 1
