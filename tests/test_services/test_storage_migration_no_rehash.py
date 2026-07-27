"""Projekt-Open darf unveraenderte Artefakte nicht bei jedem Lauf neu hashen.

Befund (Audit 2026-07-27, Bereich db-persistenz, bestaetigt + gemessen):
``migrate_existing_outputs`` laeuft bei JEDEM ``open_project``. ``_upsert_artifact``
setzte ``row.bytes``/``row.sha256`` bedingungslos — auch fuer Rows, die es gerade
per ``one_or_none()`` gefunden hatte. Folge: Voll-Hash jedes Proxys/Stems pro
Open (im groessten real vorhandenen Projekt 0,65 GB Artefakte) plus eine
UPDATE-Flut, weil jede Row dirty markiert wurde.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database.models import AnalysisArtifact, AnalysisJob, Base
from services.storage_provenance import storage_migration


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _job(session: Session) -> AnalysisJob:
    job = AnalysisJob(
        source_sha256="a" * 64,
        step_id="video.plan_a.outputs",
        step_version="1",
        params_hash="p",
        status="done",
    )
    session.add(job)
    session.flush()
    return job


def _migrator(session: Session, tmp_path: Path):
    return storage_migration.StorageMigrationService(
        session, storage_root=tmp_path / "storage"
    )


def test_unchanged_artifact_is_not_rehashed(tmp_path: Path, session: Session, monkeypatch) -> None:
    artifact = tmp_path / "proxy.mp4"
    artifact.write_bytes(b"proxy-bytes")
    job = _job(session)
    mig = _migrator(session, tmp_path)

    calls: list[Path] = []
    real_sha = storage_migration._file_sha256

    def _counting_sha(path: Path) -> str:
        calls.append(path)
        return real_sha(path)

    monkeypatch.setattr(storage_migration, "_file_sha256", _counting_sha)

    kwargs = dict(
        artifact_type="video",
        artifact_role="proxy",
        rel_path="video/proxy.mp4",
        file_path=artifact,
    )
    first = mig._upsert_artifact(job, **kwargs)
    session.flush()
    assert len(calls) == 1
    first_sha = first.sha256
    assert first_sha is not None

    second = mig._upsert_artifact(job, **kwargs)
    assert second is first
    assert second.sha256 == first_sha
    assert len(calls) == 1, (
        f"Artefakt wurde erneut gehasht ({len(calls)} Laeufe) — der "
        "Short-Circuit fuer unveraenderte Artefakte greift nicht."
    )
    assert second not in session.dirty


def test_changed_artifact_is_rehashed(tmp_path: Path, session: Session) -> None:
    """Gegenprobe: geaenderte Groesse muss den Hash neu berechnen."""
    artifact = tmp_path / "proxy.mp4"
    artifact.write_bytes(b"proxy-bytes")
    job = _job(session)
    mig = _migrator(session, tmp_path)

    kwargs = dict(
        artifact_type="video",
        artifact_role="proxy",
        rel_path="video/proxy.mp4",
        file_path=artifact,
    )
    row = mig._upsert_artifact(job, **kwargs)
    session.flush()
    old_sha = row.sha256
    old_bytes = row.bytes

    artifact.write_bytes(b"proxy-bytes-but-longer")
    row = mig._upsert_artifact(job, **kwargs)

    assert row.bytes != old_bytes
    assert row.sha256 != old_sha


def test_row_without_stored_hash_is_hashed(tmp_path: Path, session: Session) -> None:
    """Bestandsrow ohne sha256 (Altbestand) muss nachgezogen werden."""
    artifact = tmp_path / "proxy.mp4"
    artifact.write_bytes(b"proxy-bytes")
    job = _job(session)
    session.add(
        AnalysisArtifact(
            job_id=job.id,
            artifact_type="video",
            artifact_role="proxy",
            path="video/proxy.mp4",
            bytes=artifact.stat().st_size,
            sha256=None,
        )
    )
    session.flush()

    row = _migrator(session, tmp_path)._upsert_artifact(
        job,
        artifact_type="video",
        artifact_role="proxy",
        rel_path="video/proxy.mp4",
        file_path=artifact,
    )
    assert row.sha256 is not None
