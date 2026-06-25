from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from database.models import AnalysisArtifact, AnalysisJob, Project, ProjectSource
from services.storage_provenance.dedup_lookup import check_dedup, stable_params_hash
from services.storage_provenance.source_identity import compute_source_sha256
from services.storage_provenance.source_manifest import record_manifest_job

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProvenanceRecordResult:
    source_sha256: str
    job_id: int
    dedup_state: str
    artifact_count: int


class ProvenanceRecorder:
    """Caller migration writer for pipeline provenance tables."""

    def __init__(self, session: Session, *, storage_root: str | Path | None = None) -> None:
        self.session = session
        self._storage_root = storage_root

    def _record_manifest(
        self,
        project_id: int,
        source_sha: str,
        job: AnalysisJob,
        artifacts: dict[str, str | Path] | None = None,
    ) -> None:
        """B-539: mirror provenance into the global by_sha manifest. Best-effort.

        B-579: also persist the *real* artifact paths so cross-project reuse can
        resolve V2-pipeline outputs that live at project-local paths (never copied
        into by_sha)."""
        try:
            storage_root = self._storage_root
            if storage_root is None:
                from services.storage_provenance.schnitt_audio_adapter import (
                    default_global_storage_root,
                )

                storage_root = default_global_storage_root()
            project = self.session.get(Project, project_id)
            record_manifest_job(
                storage_root,
                source_sha,
                project_id=project_id,
                project_name=project.name if project is not None else "unbekannt",
                project_path=project.path if project is not None else str(project_id),
                step_id=job.step_id,
                model=job.produced_by_model,
                model_version=job.produced_by_model_version,
                finished_at=job.finished_at,
                artifacts=artifacts,
            )
        except Exception as e:  # never break the pipeline on manifest write
            logger.warning("B-545: provenance manifest write failed (project=%s): %s", project_id, e)

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
        real_artifacts: dict[str, str] = {}
        for role, path in artifacts.items():
            if path is None:
                continue
            artifact_path = Path(path)
            if not artifact_path.exists() or not artifact_path.is_file():
                continue
            self._upsert_artifact(job, role, artifact_path)
            real_artifacts[role] = str(artifact_path)
            artifact_count += 1

        # B-579: record the manifest after collecting the real, on-disk artifact
        # paths so cross-project reuse can resolve them without assuming the
        # by_sha layout.
        self._record_manifest(project_id, source_sha, job, real_artifacts)

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
