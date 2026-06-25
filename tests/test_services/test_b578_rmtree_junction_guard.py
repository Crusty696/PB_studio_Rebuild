from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import AnalysisArtifact, AnalysisJob, Base
from services.storage_provenance.storage_browser import StorageBrowserService


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _job(session: Session, sha: str) -> None:
    job = AnalysisJob(
        source_sha256=sha,
        step_id="audio.v2.stems",
        step_version="1",
        params_hash="params-stems",
        status="done",
        finished_at=datetime(2026, 6, 15),
    )
    job.artifacts.append(
        AnalysisArtifact(
            artifact_type="json",
            artifact_role="stems-artifact",
            path="audio/stems/out.json",
            bytes=10,
        )
    )
    session.add(job)


def _make_junction(link: Path, target: Path) -> bool:
    """Create a Windows junction (no admin needed). Returns True on success."""
    if os.name != "nt":
        return False
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and link.exists()


def test_b578_delete_does_not_follow_junction_inside_tree(tmp_path: Path) -> None:
    """B-578 containment: a junction nested inside the storage source dir must not
    cause deletion of the real project stems it points to."""
    sha = "2" * 64
    storage_root = tmp_path / "storage"

    external = tmp_path / "project_local" / "stems"
    (external / "nested").mkdir(parents=True)
    keep = external / "keep.wav"
    keep.write_bytes(b"real-project-stems")
    (external / "nested" / "deep.wav").write_bytes(b"deep")

    with _session() as session:
        _job(session, sha)
        session.commit()
        service = StorageBrowserService(session, storage_root=storage_root)
        source_root = service.layout.source_root(sha)
        (source_root / "audio").mkdir(parents=True)
        (source_root / "audio" / "real_artifact.bin").write_bytes(b"cache")

        # layout.create_directory_link puts a junction at .../audio/stems
        link = source_root / "audio" / "stems"
        if not _make_junction(link, external):
            pytest.skip("mklink /J not available in this runner")

        result = service.delete_analysis_sources([sha], delete_storage_dirs=True)

    assert not source_root.exists()
    assert result.deleted_storage_dirs == 1
    assert external.exists(), "external stems dir was deleted via junction"
    assert keep.exists() and keep.read_bytes() == b"real-project-stems"
    assert (external / "nested" / "deep.wav").exists()


def test_b578_delete_when_source_root_itself_is_a_junction(tmp_path: Path) -> None:
    """B-578 hardening: when the storage source dir itself is a junction pointing at
    real project data, deletion must remove only the link and never the target
    contents. The pre-fix code raised ``OSError: Cannot call rmtree on a symbolic
    link`` here (rmtree refuses), so the storage dir was not even cleaned up while
    the project data was at risk on other platforms/versions."""
    sha = "3" * 64
    storage_root = tmp_path / "storage"

    external = tmp_path / "project_local"
    external.mkdir(parents=True)
    keep = external / "keep.wav"
    keep.write_bytes(b"real-project-stems")

    with _session() as session:
        _job(session, sha)
        session.commit()
        service = StorageBrowserService(session, storage_root=storage_root)
        source_root = service.layout.source_root(sha)
        # The whole source_root is a junction onto external project data.
        source_root.parent.mkdir(parents=True, exist_ok=True)
        if not _make_junction(source_root, external):
            pytest.skip("mklink /J not available in this runner")

        result = service.delete_analysis_sources([sha], delete_storage_dirs=True)

    assert not source_root.exists(), "junction link was not removed"
    assert result.deleted_storage_dirs == 1
    assert external.exists(), "junction target dir was deleted"
    assert keep.exists() and keep.read_bytes() == b"real-project-stems"
