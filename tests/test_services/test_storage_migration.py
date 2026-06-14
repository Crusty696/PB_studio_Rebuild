from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import (
    AnalysisArtifact,
    AnalysisJob,
    AudioTrack,
    Base,
    Project,
    ProjectSource,
    VideoClip,
)
from services.storage_provenance.source_identity import compute_source_sha256
from services.storage_provenance.storage_migration import StorageMigrationService


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_storage_migration_registers_audio_stems_and_junction(tmp_path: Path) -> None:
    source = tmp_path / "track.wav"
    source.write_bytes(b"audio-source")
    stem_dir = tmp_path / "project" / "storage" / "stems" / "1"
    stem_dir.mkdir(parents=True)
    vocals = stem_dir / "vocals.flac"
    vocals.write_bytes(b"vocals")

    with _session() as session:
        session.add(Project(id=1, name="p", path=str(tmp_path / "project"), resolution="1920x1080", fps=30.0))
        session.add(
            AudioTrack(
                id=1,
                project_id=1,
                file_path=str(source),
                stem_vocals_path=str(vocals),
            )
        )
        session.commit()

        result = StorageMigrationService(session, storage_root=tmp_path / "global").migrate_existing_outputs()

        source_sha = compute_source_sha256(source, media_type="audio", mode="strict")
        link_path = tmp_path / "global" / "by_sha" / source_sha[:2] / source_sha / "audio" / "stems"

        assert result.audio_tracks == 1
        assert (link_path / "vocals.flac").read_bytes() == b"vocals"
        assert session.query(ProjectSource).filter_by(source_sha256=source_sha).count() == 1
        assert session.query(AnalysisJob).filter_by(source_sha256=source_sha, step_id="audio.v2.stems").count() == 1
        assert session.query(AnalysisArtifact).filter_by(artifact_role="vocals_stem").one().path == (
            "audio/stems/vocals.flac"
        )


def test_storage_migration_registers_plan_a_video_outputs(tmp_path: Path) -> None:
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video-source")
    proxy = tmp_path / "project" / "storage" / "proxies" / "clip_proxy.mp4"
    proxy.parent.mkdir(parents=True)
    proxy.write_bytes(b"proxy")

    with _session() as session:
        session.add(Project(id=1, name="p", path=str(tmp_path / "project"), resolution="1920x1080", fps=30.0))
        session.add(
            VideoClip(
                id=1,
                project_id=1,
                file_path=str(source),
                proxy_path=str(proxy),
                proxy_status="done",
            )
        )
        session.commit()

        result = StorageMigrationService(session, storage_root=tmp_path / "global").migrate_existing_outputs()

        source_sha = compute_source_sha256(source, media_type="video", mode="strict")
        assert result.video_clips == 1
        assert session.query(AnalysisJob).filter_by(source_sha256=source_sha, step_id="video.plan_a.outputs").count() == 1
        assert session.query(AnalysisArtifact).filter_by(artifact_role="proxy").one().path == "video/proxy.mp4"


def test_storage_migration_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "track.wav"
    source.write_bytes(b"audio-source")
    stem_dir = tmp_path / "project" / "storage" / "stems" / "1"
    stem_dir.mkdir(parents=True)
    (stem_dir / "vocals.flac").write_bytes(b"vocals")

    with _session() as session:
        session.add(Project(id=1, name="p", path=str(tmp_path / "project"), resolution="1920x1080", fps=30.0))
        session.add(
            AudioTrack(
                id=1,
                project_id=1,
                file_path=str(source),
                stem_vocals_path=str(stem_dir / "vocals.flac"),
            )
        )
        session.commit()

        service = StorageMigrationService(session, storage_root=tmp_path / "global")
        service.migrate_existing_outputs()
        service.migrate_existing_outputs()

        source_sha = compute_source_sha256(source, media_type="audio", mode="strict")
        assert session.query(ProjectSource).filter_by(source_sha256=source_sha).count() == 1
        assert session.query(AnalysisJob).filter_by(source_sha256=source_sha, step_id="audio.v2.stems").count() == 1
