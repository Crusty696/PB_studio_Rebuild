"""B-706/M3: Content-Hash-Dedup beim Video-Import.

Vorher: Dup-Erkennung rein pfadbasiert (project_id, file_path); stream_sha256
wurde nie gesetzt -> identischer Inhalt ueber einen anderen Pfad (UNC/gemapptes
Laufwerk/Junction/8.3) doppelt importiert. Jetzt: stream_sha256 wird beim Import
berechnet und derselbe Inhalt unter anderem Pfad uebersprungen.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from database import Project, VideoClip


def _meta():
    return {"duration": 1.0, "width": 1920, "height": 1080, "fps": 30.0, "codec": "h264"}


def test_b706_m3_content_hash_dedup(test_engine, tmp_path, monkeypatch):
    import services.ingest_service as ingest_service

    monkeypatch.setattr(ingest_service, "_probe_video_meta", lambda _p: _meta())
    monkeypatch.setattr(
        ingest_service, "_apply_cross_project_reuse_after_ingest", lambda *a, **k: None
    )

    with Session(test_engine) as session:
        project = Project(name="P", path=".")
        session.add(project)
        session.commit()
        pid = project.id

    content = b"MOOV-fake-video-bytes\0" * 50000  # ~1 MiB, identischer Inhalt
    a = tmp_path / "sub1" / "clip.mp4"
    a.parent.mkdir()
    a.write_bytes(content)
    b = tmp_path / "sub2" / "anderer_name.mp4"   # gleicher Inhalt, anderer Pfad
    b.parent.mkdir()
    b.write_bytes(content)
    c = tmp_path / "sub3" / "diff.mp4"           # anderer Inhalt
    c.parent.mkdir()
    c.write_bytes(content + b"X")

    r1 = ingest_service.ingest_video(str(a), project_id=pid, invalidate_caches=False)
    assert r1 is not None
    r1_id = r1.id

    r2 = ingest_service.ingest_video(str(b), project_id=pid, invalidate_caches=False)
    assert r2 is None, "identischer Inhalt unter anderem Pfad muss uebersprungen werden (B-706/M3)"

    r3 = ingest_service.ingest_video(str(c), project_id=pid, invalidate_caches=False)
    assert r3 is not None, "anderer Inhalt muss regulaer importiert werden"

    with Session(test_engine) as session:
        clip = session.get(VideoClip, r1_id)
        assert clip.stream_sha256, "stream_sha256 muss beim Import gesetzt werden (B-706/M3)"
        clips = session.query(VideoClip).filter_by(project_id=pid).all()
        assert len(clips) == 2, "nur 2 unterschiedliche Inhalte importiert, das Duplikat nicht"
