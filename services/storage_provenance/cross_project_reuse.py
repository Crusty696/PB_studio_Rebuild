from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from database.models import AnalysisJob, AnalysisStatus, Project, ProjectSource
from services.storage_provenance.source_identity import compute_source_sha256


PROVENANCE_TO_ANALYSIS_STEPS: dict[str, tuple[str, ...]] = {
    "audio.v2.stems": ("stem_separation",),
    "video.plan_a.outputs": ("motion_scores", "siglip_embeddings"),
}


@dataclass(frozen=True)
class ReuseStep:
    provenance_step_id: str
    analysis_step_key: str
    produced_at: datetime | None
    model: str
    tooltip: str


@dataclass(frozen=True)
class CrossProjectReuseHit:
    source_sha256: str
    project_id: int
    project_name: str
    steps: tuple[ReuseStep, ...]
    toast_message: str


def lookup_cross_project_reuse(
    session: Session,
    source_path: str | Path,
    *,
    media_type: str,
    current_project_id: int | None,
) -> CrossProjectReuseHit | None:
    """Find completed provenance jobs for the same source in another project."""

    source_sha = compute_source_sha256(source_path, media_type=media_type, mode="strict")
    source_project = _find_previous_project(session, source_sha, current_project_id=current_project_id)
    if source_project is None:
        return None

    jobs = (
        session.query(AnalysisJob)
        .filter(
            AnalysisJob.source_sha256 == source_sha,
            AnalysisJob.status == "done",
        )
        .order_by(AnalysisJob.finished_at.desc().nullslast(), AnalysisJob.id.asc())
        .all()
    )

    steps: list[ReuseStep] = []
    for job in jobs:
        for analysis_step in _analysis_steps_for_job(job.step_id):
            model = _format_model(job)
            tooltip = _format_tooltip(job.finished_at, source_project.name, model)
            steps.append(
                ReuseStep(
                    provenance_step_id=job.step_id,
                    analysis_step_key=analysis_step,
                    produced_at=job.finished_at,
                    model=model,
                    tooltip=tooltip,
                )
            )

    if not steps:
        return None

    return CrossProjectReuseHit(
        source_sha256=source_sha,
        project_id=source_project.id,
        project_name=source_project.name,
        steps=tuple(steps),
        toast_message=(
            f"Datei wurde bereits in Projekt {source_project.name} analysiert. "
            "Ergebnisse werden mitverwendet."
        ),
    )


def apply_cross_project_reuse_status(
    session: Session,
    source_path: str | Path,
    *,
    media_type: str,
    media_id: int,
    current_project_id: int | None,
) -> CrossProjectReuseHit | None:
    """Create local done AnalysisStatus rows for reusable provenance hits."""

    hit = lookup_cross_project_reuse(
        session,
        source_path,
        media_type=media_type,
        current_project_id=current_project_id,
    )
    if hit is None:
        return None

    now = datetime.now(timezone.utc)
    if current_project_id is not None:
        _upsert_current_project_source(
            session,
            project_id=int(current_project_id),
            source_sha=hit.source_sha256,
            source_path=source_path,
        )
    for step in hit.steps:
        row = (
            session.query(AnalysisStatus)
            .filter_by(media_type=media_type, media_id=media_id, step_key=step.analysis_step_key)
            .one_or_none()
        )
        summary = {
            "reuse_source_project": hit.project_name,
            "reuse_source_sha256": hit.source_sha256,
            "provenance_step_id": step.provenance_step_id,
            "provenance_tooltip": step.tooltip,
        }
        if row is None:
            row = AnalysisStatus(
                media_type=media_type,
                media_id=media_id,
                step_key=step.analysis_step_key,
                status="done",
                started_at=now,
                completed_at=step.produced_at or now,
                value_summary=summary,
            )
            session.add(row)
        elif row.status != "done":
            row.status = "done"
            row.completed_at = step.produced_at or now
            row.error_message = None
            row.value_summary = summary

    session.commit()
    return hit


def _find_previous_project(
    session: Session,
    source_sha: str,
    *,
    current_project_id: int | None,
) -> Project | None:
    query = (
        session.query(Project)
        .join(ProjectSource, ProjectSource.project_id == Project.id)
        .filter(ProjectSource.source_sha256 == source_sha)
        .filter(Project.deleted_at.is_(None))
        .order_by(ProjectSource.last_seen_at.desc().nullslast(), Project.id.asc())
    )
    if current_project_id is not None:
        query = query.filter(Project.id != int(current_project_id))
    return query.first()


def _upsert_current_project_source(
    session: Session,
    *,
    project_id: int,
    source_sha: str,
    source_path: str | Path,
) -> ProjectSource:
    row = (
        session.query(ProjectSource)
        .filter_by(project_id=project_id, source_sha256=source_sha)
        .one_or_none()
    )
    if row is None:
        row = ProjectSource(
            project_id=project_id,
            source_sha256=source_sha,
            current_source_path=str(Path(source_path)),
            last_seen_at=datetime.utcnow(),
        )
        session.add(row)
    else:
        row.current_source_path = str(Path(source_path))
        row.last_seen_at = datetime.utcnow()
    return row


def _analysis_steps_for_job(step_id: str) -> tuple[str, ...]:
    if step_id in PROVENANCE_TO_ANALYSIS_STEPS:
        return PROVENANCE_TO_ANALYSIS_STEPS[step_id]
    if "." not in step_id:
        return (step_id,)
    return ()


def _format_model(job: AnalysisJob) -> str:
    if job.produced_by_model and job.produced_by_model_version:
        return f"{job.produced_by_model} {job.produced_by_model_version}"
    if job.produced_by_model:
        return job.produced_by_model
    return job.step_id


def _format_tooltip(produced_at: datetime | None, project_name: str, model: str) -> str:
    if produced_at is None:
        produced = "unbekannt"
    else:
        produced = produced_at.strftime("%Y-%m-%d %H:%M")
    return f"Erzeugt am {produced} in Projekt {project_name}, Modell {model}"
