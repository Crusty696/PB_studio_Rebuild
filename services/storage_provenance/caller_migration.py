from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from database.models import AnalysisArtifact, AnalysisJob, ProjectSource
from services.storage_provenance.dedup_lookup import check_dedup, stable_params_hash
from services.storage_provenance.source_identity import compute_source_sha256


@dataclass(frozen=True)
class ProvenanceRecordResult:
    source_sha256: str
    job_id: int
    dedup_state: str
    artifact_count: int


class ProvenanceRecorder:
    """Caller migration writer for pipeline provenance tables."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record_done(
        self,
        *,
        project_id: int,
        source_path: str | Path,
        media_type: str,
        step_id: str,
        params: dict,
        artifacts: dict[str, str | Path],
        step_version: str = "1",
        produced_by_model: str | None = None,
        produced_by_model_version: str | None = None,
    ) -> ProvenanceRecordResult:
        source = Path(source_path)
        source_sha = compute_source_sha256(source, media_type=media_type, mode="strict")
        params_hash = stable_params_hash(params)
        dedup = check_dedup(self.session, source_sha, step_id, step_version, params)

        self._upsert_project_source(project_id, source_sha, source)
        job = self._upsert_job(
            source_sha,
            step_id,
            step_version,
            params_hash,
            produced_by_model=produced_by_model,
            produced_by_model_version=produced_by_model_version,
        )
        artifact_count = 0
        for role, path in artifacts.items():
            if path is None:
                continue
            artifact_path = Path(path)
            if not artifact_path.exists() or not artifact_path.is_file():
                continue
            self._upsert_artifact(job, role, artifact_path)
            artifact_count += 1

        self.session.commit()
        return ProvenanceRecordResult(
            source_sha256=source_sha,
            job_id=job.id,
            dedup_state="hit" if dedup.state == "hit" else "miss",
            artifact_count=artifact_count,
        )

    def _upsert_project_source(self, project_id: int, source_sha: str, source: Path) -> ProjectSource:
        row = (
            self.session.query(ProjectSource)
            .filter_by(project_id=project_id, source_sha256=source_sha)
            .one_or_none()
        )
        if row is None:
            row = ProjectSource(
                project_id=project_id,
                source_sha256=source_sha,
                current_source_path=str(source),
                last_seen_at=datetime.utcnow(),
            )
            self.session.add(row)
        else:
            row.current_source_path = str(source)
            row.last_seen_at = datetime.utcnow()
        return row

    def _upsert_job(
        self,
        source_sha: str,
        step_id: str,
        step_version: str,
        params_hash: str,
        *,
        produced_by_model: str | None,
        produced_by_model_version: str | None,
    ) -> AnalysisJob:
        row = (
            self.session.query(AnalysisJob)
            .filter_by(
                source_sha256=source_sha,
                step_id=step_id,
                step_version=step_version,
                params_hash=params_hash,
            )
            .one_or_none()
        )
        if row is None:
            row = AnalysisJob(
                source_sha256=source_sha,
                step_id=step_id,
                step_version=step_version,
                params_hash=params_hash,
                status="done",
                produced_by_model=produced_by_model,
                produced_by_model_version=produced_by_model_version,
                finished_at=datetime.utcnow(),
            )
            self.session.add(row)
            self.session.flush()
        else:
            row.status = "done"
            row.produced_by_model = produced_by_model or row.produced_by_model
            row.produced_by_model_version = produced_by_model_version or row.produced_by_model_version
            row.finished_at = datetime.utcnow()
            row.error = None
        return row

    def _upsert_artifact(self, job: AnalysisJob, role: str, artifact_path: Path) -> AnalysisArtifact:
        row = (
            self.session.query(AnalysisArtifact)
            .filter_by(job_id=job.id, artifact_role=role, path=str(artifact_path))
            .one_or_none()
        )
        if row is None:
            row = AnalysisArtifact(
                job_id=job.id,
                artifact_type=_artifact_type(artifact_path),
                artifact_role=role,
                path=str(artifact_path),
            )
            self.session.add(row)
        row.bytes = artifact_path.stat().st_size
        row.sha256 = _file_sha256(artifact_path)
        return row


def _artifact_type(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return suffix or "file"


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
