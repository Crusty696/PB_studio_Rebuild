from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import AnalysisArtifact, AnalysisJob, Base, Project, ProjectSource
from services.storage_provenance.storage_browser import StorageBrowserService


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _job(session: Session, sha: str, step: str, *, finished_at: datetime, bytes_: int) -> None:
    job = AnalysisJob(
        source_sha256=sha,
        step_id=step,
        step_version="1",
        params_hash=f"params-{step}",
        status="done",
        finished_at=finished_at,
    )
    job.artifacts.append(
        AnalysisArtifact(
            artifact_type="json",
            artifact_role=f"{step}-artifact",
            path=f"{step}/out.json",
            bytes=bytes_,
        )
    )
    session.add(job)


def test_storage_browser_lists_sources_sorted_with_project_usage(tmp_path: Path) -> None:
    newer = datetime(2026, 6, 15, 12, 0, 0)
    older = datetime(2026, 6, 1, 12, 0, 0)
    sha_new = "a" * 64
    sha_old = "b" * 64

    with _session() as session:
        session.add(Project(id=1, name="Projekt A", path=str(tmp_path / "a"), resolution="1920x1080", fps=30.0))
        session.add(Project(id=2, name="Projekt B", path=str(tmp_path / "b"), resolution="1920x1080", fps=30.0))
        session.add(ProjectSource(project_id=1, source_sha256=sha_new, current_source_path=str(tmp_path / "new.wav"), last_seen_at=newer))
        session.add(ProjectSource(project_id=2, source_sha256=sha_new, current_source_path=str(tmp_path / "new.wav"), last_seen_at=newer))
        session.add(ProjectSource(project_id=1, source_sha256=sha_old, current_source_path=str(tmp_path / "old.mp4"), last_seen_at=older))
        _job(session, sha_new, "audio.v2.stems", finished_at=newer, bytes_=100)
        _job(session, sha_new, "audio.waveform", finished_at=newer, bytes_=50)
        _job(session, sha_old, "video.plan_a.outputs", finished_at=older, bytes_=25)
        session.commit()

        rows = StorageBrowserService(session).list_sources()

    assert [row.source_sha256 for row in rows] == [sha_new, sha_old]
    assert rows[0].file_name == "new.wav"
    assert rows[0].project_count == 2
    assert rows[0].projects_used_by == "Projekt A, Projekt B"
    assert rows[0].stages_done == 2
    assert rows[0].total_bytes == 150


def test_storage_browser_filters_unused_and_old_sources(tmp_path: Path) -> None:
    now = datetime(2026, 6, 15, 12, 0, 0)
    used_sha = "c" * 64
    unused_old_sha = "d" * 64

    with _session() as session:
        session.add(Project(id=1, name="Projekt A", path=str(tmp_path / "a"), resolution="1920x1080", fps=30.0))
        session.add(ProjectSource(project_id=1, source_sha256=used_sha, current_source_path=str(tmp_path / "used.wav"), last_seen_at=now))
        _job(session, used_sha, "audio.v2.stems", finished_at=now, bytes_=10)
        _job(session, unused_old_sha, "video.plan_a.outputs", finished_at=now - timedelta(days=40), bytes_=20)
        session.commit()

        rows = StorageBrowserService(session).list_sources(
            unused_only=True,
            older_than_days=30,
            now=now,
        )

    assert [row.source_sha256 for row in rows] == [unused_old_sha]


def test_storage_browser_delete_selected_removes_only_selected_analysis_jobs(tmp_path: Path) -> None:
    selected_sha = "e" * 64
    kept_sha = "f" * 64

    with _session() as session:
        _job(session, selected_sha, "audio.v2.stems", finished_at=datetime(2026, 6, 15), bytes_=10)
        _job(session, kept_sha, "video.plan_a.outputs", finished_at=datetime(2026, 6, 15), bytes_=20)
        session.commit()

        result = StorageBrowserService(session).delete_analysis_sources([selected_sha])

        remaining = {job.source_sha256 for job in session.query(AnalysisJob).all()}

    assert result.deleted_sources == 1
    assert result.deleted_jobs == 1
    assert remaining == {kept_sha}


def test_storage_browser_delete_empty_selection_is_noop() -> None:
    with _session() as session:
        result = StorageBrowserService(session).delete_analysis_sources([])

    assert result.deleted_sources == 0
    assert result.deleted_jobs == 0
    assert result.deleted_artifacts == 0
    assert result.deleted_storage_dirs == 0


def test_storage_browser_lists_job_without_project_source() -> None:
    sha = "1" * 64
    with _session() as session:
        _job(session, sha, "audio.v2.stems", finished_at=datetime(2026, 6, 15), bytes_=0)
        session.commit()

        rows = StorageBrowserService(session).list_sources()

    assert len(rows) == 1
    assert rows[0].file_name == "-"
    assert rows[0].projects_used_by == "-"
    assert rows[0].project_count == 0


def test_storage_browser_delete_removes_storage_directory(tmp_path: Path) -> None:
    sha = "2" * 64
    storage_root = tmp_path / "storage"

    with _session() as session:
        _job(session, sha, "audio.v2.stems", finished_at=datetime(2026, 6, 15), bytes_=10)
        session.commit()
        service = StorageBrowserService(session, storage_root=storage_root)
        source_root = service.layout.source_root(sha)
        source_root.mkdir(parents=True)
        (source_root / "artifact.bin").write_bytes(b"x")

        result = service.delete_analysis_sources([sha], delete_storage_dirs=True)

    assert result.deleted_storage_dirs == 1
    assert not source_root.exists()
