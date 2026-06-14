from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from sqlalchemy.orm import Session

from database.models import AnalysisJob


@dataclass(frozen=True)
class DedupResult:
    state: str
    job_id: int | None = None
    artifacts: dict[str, str] | None = None


def stable_params_hash(params: dict) -> str:
    payload = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def check_dedup(
    session: Session,
    source_sha256: str,
    step_id: str,
    step_version: str,
    params: dict,
) -> DedupResult:
    params_hash = stable_params_hash(params)
    job = (
        session.query(AnalysisJob)
        .filter_by(
            source_sha256=source_sha256,
            step_id=step_id,
            step_version=step_version,
            params_hash=params_hash,
        )
        .one_or_none()
    )
    if job is None:
        stale_job = (
            session.query(AnalysisJob)
            .filter_by(source_sha256=source_sha256, step_id=step_id, params_hash=params_hash)
            .order_by(AnalysisJob.id.desc())
            .first()
        )
        if stale_job is not None:
            return DedupResult(state="stale", job_id=stale_job.id, artifacts=_artifact_map(stale_job))
        return DedupResult(state="miss", artifacts={})

    if job.status == "done":
        return DedupResult(state="hit", job_id=job.id, artifacts=_artifact_map(job))
    if job.status == "partial":
        return DedupResult(state="partial", job_id=job.id, artifacts=_artifact_map(job))
    return DedupResult(state=job.status, job_id=job.id, artifacts=_artifact_map(job))


def _artifact_map(job: AnalysisJob) -> dict[str, str]:
    return {artifact.artifact_role: artifact.path for artifact in job.artifacts}
