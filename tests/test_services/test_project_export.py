from __future__ import annotations

import zipfile
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import AnalysisArtifact, AnalysisJob, Base, Project, ProjectSource
from services.storage_provenance.project_bundle import (
    ProjectBundleService,
    ProjectBundleValidationError,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_project_with_artifact(session: Session, storage_root: Path, tmp_path: Path) -> tuple[int, str, Path]:
    source_sha = "a" * 64
    project = Project(
        id=1,
        name="Projekt A",
        path=str(tmp_path / "Projekt A"),
        resolution="1920x1080",
        fps=30.0,
    )
    session.add(project)
    session.add(
        ProjectSource(
            project_id=1,
            source_sha256=source_sha,
            current_source_path=str(tmp_path / "track.wav"),
            last_seen_at=datetime(2026, 6, 15, 12, 0, 0),
        )
    )
    job = AnalysisJob(
        source_sha256=source_sha,
        step_id="audio.v2.stems",
        step_version="1",
        params_hash="legacy-v2-stems",
        status="done",
        produced_by_model="Demucs",
        finished_at=datetime(2026, 6, 15, 12, 30, 0),
    )
    job.artifacts.append(
        AnalysisArtifact(
            artifact_type="stem",
            artifact_role="vocals_stem",
            path="audio/stems/vocals.flac",
            bytes=6,
        )
    )
    session.add(job)
    session.commit()

    artifact = storage_root / "by_sha" / source_sha[:2] / source_sha / "audio" / "stems" / "vocals.flac"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"vocals")
    return project.id, source_sha, artifact


def test_project_bundle_export_writes_manifest_and_by_sha_files(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    bundle = tmp_path / "Projekt A.pbbundle"

    with _session() as session:
        project_id, source_sha, _artifact = _seed_project_with_artifact(session, storage_root, tmp_path)

        result = ProjectBundleService(session, storage_root=storage_root).export_project(project_id, bundle)

    assert result.bundle_path == bundle
    assert result.source_count == 1
    assert result.file_count == 1
    with zipfile.ZipFile(bundle) as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert f"storage/by_sha/{source_sha[:2]}/{source_sha}/audio/stems/vocals.flac" in names
        manifest = zf.read("manifest.json").decode("utf-8")
    assert '"project"' in manifest
    assert '"analysis_jobs"' in manifest


def test_project_bundle_import_creates_project_sources_jobs_and_files(tmp_path: Path) -> None:
    source_storage = tmp_path / "source_storage"
    bundle = tmp_path / "Projekt A.pbbundle"
    target_storage = tmp_path / "target_storage"

    with _session() as export_session:
        project_id, source_sha, _artifact = _seed_project_with_artifact(export_session, source_storage, tmp_path)
        ProjectBundleService(export_session, storage_root=source_storage).export_project(project_id, bundle)

    with _session() as import_session:
        result = ProjectBundleService(import_session, storage_root=target_storage).import_project(
            bundle,
            project_path=tmp_path / "Imported",
        )

        project = import_session.get(Project, result.project_id)
        source = import_session.query(ProjectSource).filter_by(project_id=result.project_id).one()
        job = import_session.query(AnalysisJob).filter_by(source_sha256=source_sha).one()
        artifact = import_session.query(AnalysisArtifact).filter_by(job_id=job.id).one()

    assert project is not None
    assert project.name == "Projekt A"
    assert source.source_sha256 == source_sha
    assert artifact.path == "audio/stems/vocals.flac"
    assert (target_storage / "by_sha" / source_sha[:2] / source_sha / "audio" / "stems" / "vocals.flac").read_bytes() == b"vocals"


def test_project_bundle_import_rejects_corrupt_storage_file(tmp_path: Path) -> None:
    source_storage = tmp_path / "source_storage"
    bundle = tmp_path / "Projekt A.pbbundle"

    with _session() as export_session:
        project_id, source_sha, _artifact = _seed_project_with_artifact(export_session, source_storage, tmp_path)
        ProjectBundleService(export_session, storage_root=source_storage).export_project(project_id, bundle)

    corrupt_bundle = tmp_path / "corrupt.pbbundle"
    with zipfile.ZipFile(bundle) as src, zipfile.ZipFile(corrupt_bundle, "w") as dst:
        for info in src.infolist():
            data = src.read(info.filename)
            if info.filename.endswith("vocals.flac"):
                data = b"broken"
            dst.writestr(info, data)

    with _session() as import_session:
        with pytest.raises(ProjectBundleValidationError):
            ProjectBundleService(import_session, storage_root=tmp_path / "target").import_project(
                corrupt_bundle,
                project_path=tmp_path / "Imported",
            )
