from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import AnalysisArtifact, AnalysisJob, Base, Project, ProjectSource
from services.storage_provenance.disk_budget import DiskBudgetService, InsufficientDiskSpace


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_job(session: Session, sha: str, step: str, *, bytes_: int, finished_at: datetime) -> None:
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
            artifact_type="bin",
            artifact_role=f"{step}-artifact",
            path=f"{step}/artifact.bin",
            bytes=bytes_,
        )
    )
    session.add(job)


def test_disk_budget_summary_reports_total_and_project_usage(tmp_path) -> None:
    now = datetime(2026, 6, 15, 12, 0)
    sha_a = "a" * 64
    sha_b = "b" * 64
    with _session() as session:
        session.add(Project(id=1, name="Projekt A", path=str(tmp_path / "a"), resolution="1920x1080", fps=30.0))
        session.add(Project(id=2, name="Projekt B", path=str(tmp_path / "b"), resolution="1920x1080", fps=30.0))
        session.add(ProjectSource(project_id=1, source_sha256=sha_a, current_source_path=str(tmp_path / "a.wav"), last_seen_at=now))
        session.add(ProjectSource(project_id=2, source_sha256=sha_b, current_source_path=str(tmp_path / "b.wav"), last_seen_at=now))
        _seed_job(session, sha_a, "audio.v2.stems", bytes_=100, finished_at=now)
        _seed_job(session, sha_b, "video.plan_a.outputs", bytes_=250, finished_at=now)
        session.commit()

        summary = DiskBudgetService(session, storage_root=tmp_path / "storage").summarize()

    assert summary.total_bytes == 350
    assert summary.source_count == 2
    assert [(item.project_name, item.total_bytes) for item in summary.project_usage] == [
        ("Projekt A", 100),
        ("Projekt B", 250),
    ]


def test_disk_budget_cleanup_estimate_finds_unused_old_artifacts(tmp_path) -> None:
    now = datetime(2026, 6, 15, 12, 0)
    used_sha = "c" * 64
    unused_old_sha = "d" * 64
    with _session() as session:
        session.add(Project(id=1, name="Projekt A", path=str(tmp_path / "a"), resolution="1920x1080", fps=30.0))
        session.add(ProjectSource(project_id=1, source_sha256=used_sha, current_source_path=str(tmp_path / "used.wav"), last_seen_at=now))
        _seed_job(session, used_sha, "audio.v2.stems", bytes_=100, finished_at=now)
        _seed_job(session, unused_old_sha, "video.plan_a.outputs", bytes_=300, finished_at=now - timedelta(days=40))
        session.commit()

        estimate = DiskBudgetService(session, storage_root=tmp_path / "storage").estimate_unused_cleanup(
            older_than_days=30,
            now=now,
        )

    assert estimate.source_sha256_values == (unused_old_sha,)
    assert estimate.reclaimable_bytes == 300


def test_disk_budget_probe_blocks_when_free_space_too_low(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "services.storage_provenance.disk_budget.shutil.disk_usage",
        lambda _path: SimpleNamespace(free=10),
    )
    with _session() as session:
        service = DiskBudgetService(session, storage_root=tmp_path / "storage")

        with pytest.raises(InsufficientDiskSpace, match="required=11, free=10"):
            service.assert_free_space_for_migration(required_bytes=11)
