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
    # B-579: real artifact paths recorded in the by_sha manifest (role -> path or
    # role -> [paths]); None for the DB path, which falls back to the by_sha layout.
    artifacts: dict | None = None


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
    current_project_path: str | None = None,
    storage_root: str | Path | None = None,
) -> CrossProjectReuseHit | None:
    """Find completed provenance jobs for the same source in another project.

    B-539: the DB query only sees the *active* project's DB. With per-project
    DBs it never finds another project, so when it returns nothing we fall back
    to the global by_sha provenance manifest, which is visible across projects.
    ``current_project_path`` (globally unique, unlike ``current_project_id``)
    excludes the active project's own manifest entries from the fallback.
    """

    source_sha = compute_source_sha256(source_path, media_type=media_type, mode="strict")
    source_project = _find_previous_project(session, source_sha, current_project_id=current_project_id)
    if source_project is None:
        return _manifest_hit(source_sha, storage_root, current_project_path)

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
    current_project_path: str | None = None,
    storage_root: str | Path | None = None,
) -> CrossProjectReuseHit | None:
    """Create local done rows only when the reusable outputs are accessible."""

    hit = lookup_cross_project_reuse(
        session,
        source_path,
        media_type=media_type,
        current_project_id=current_project_id,
        current_project_path=current_project_path,
        storage_root=storage_root,
    )
    if hit is None:
        return None

    applied_steps: list[ReuseStep] = []
    stem_paths: dict[str, Path] | None = None
    for step in hit.steps:
        if step.provenance_step_id == "audio.v2.stems":
            # B-579: prefer the real artifact paths from the manifest, fall back
            # to the by_sha layout. Guard: only reuse if all four stems exist now.
            stem_paths = _resolve_stem_paths(storage_root, hit.source_sha256, step.artifacts)
            if stem_paths is None:
                continue
        elif step.provenance_step_id == "video.plan_a.outputs":
            # B-579 (ST-3): video had no existence guard — it marked done on a
            # dangling reference. Only reuse if the real outputs are reachable now,
            # via the manifest's real paths or the by_sha layout.
            if not _video_outputs_reachable(storage_root, hit.source_sha256, step.artifacts):
                continue
        applied_steps.append(step)
    if not applied_steps:
        return None

    now = datetime.now(timezone.utc)
    if current_project_id is not None:
        _upsert_current_project_source(
            session,
            project_id=int(current_project_id),
            source_sha=hit.source_sha256,
            source_path=source_path,
        )
    if stem_paths is not None:
        _apply_audio_stem_references(session, media_id=media_id, stem_paths=stem_paths)

    for step in applied_steps:
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
    if len(applied_steps) == len(hit.steps):
        return hit
    return CrossProjectReuseHit(
        source_sha256=hit.source_sha256,
        project_id=hit.project_id,
        project_name=hit.project_name,
        steps=tuple(applied_steps),
        toast_message=hit.toast_message,
    )


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


def _manifest_hit(
    source_sha: str,
    storage_root: str | Path | None,
    current_project_path: str | None,
) -> CrossProjectReuseHit | None:
    """B-539 fallback: build a reuse hit from the global by_sha manifest.

    Used when the active project's DB has no record of another project that
    analysed this source (the normal case with per-project DBs). Entries are
    matched/excluded by ``project_path`` because ``project_id`` is not unique
    across separate per-project DBs.
    """
    import os

    from services.storage_provenance.source_manifest import MANIFEST_NAME, _norm_path, read_manifest_jobs

    if storage_root is None:
        from services.storage_provenance.schnitt_audio_adapter import default_global_storage_root

        storage_root = default_global_storage_root()

    cur_norm = _norm_path(current_project_path) if current_project_path is not None else None
    jobs = read_manifest_jobs(storage_root, source_sha)
    candidates = [
        j
        for j in jobs
        if cur_norm is None or _norm_path(j.get("project_path", "")) != cur_norm
    ]
    if not candidates:
        return None

    # B-544 / B-579: only reuse if artifacts are physically reachable. Either the
    # by_sha source dir still holds files (legacy layout) OR at least one candidate
    # job carries real artifact paths in the manifest that exist on disk. Never
    # mark a step done on a dangling reference — re-analysis is safer.
    if not _source_root_has_artifacts(storage_root, source_sha) and not any(
        _manifest_artifacts_exist(j.get("artifacts")) for j in candidates
    ):
        return None

    # B-546: pick the most recently finished job deterministically (like the DB
    # path's finished_at.desc()), not the JSON insertion order.
    candidates.sort(key=lambda j: (_parse_iso(j.get("finished_at")) or datetime.min), reverse=True)

    src_name = candidates[0].get("project_name") or "unbekannt"
    src_id = int(candidates[0].get("project_id") or 0)

    steps: list[ReuseStep] = []
    for j in candidates:
        job_artifacts = j.get("artifacts") if isinstance(j.get("artifacts"), dict) else None
        for analysis_step in _analysis_steps_for_job(str(j.get("step_id", ""))):
            model = _format_model_from_manifest(j)
            finished = _parse_iso(j.get("finished_at"))
            tooltip = _format_tooltip(finished, j.get("project_name") or "unbekannt", model)
            steps.append(
                ReuseStep(
                    provenance_step_id=str(j.get("step_id", "")),
                    analysis_step_key=analysis_step,
                    produced_at=finished,
                    model=model,
                    tooltip=tooltip,
                    artifacts=job_artifacts,
                )
            )
    if not steps:
        return None

    return CrossProjectReuseHit(
        source_sha256=source_sha,
        project_id=src_id,
        project_name=src_name,
        steps=tuple(steps),
        toast_message=(
            f"Datei wurde bereits in Projekt {src_name} analysiert. "
            "Ergebnisse werden mitverwendet."
        ),
    )


def _source_root_has_artifacts(storage_root, source_sha: str) -> bool:
    """B-544: True if the by_sha source dir still holds artifacts (not just the
    manifest/lock). Guards against marking a reuse step done when the underlying
    stems/outputs were already deleted (e.g. via the storage browser)."""
    from services.storage_provenance.layout import StorageLayout
    from services.storage_provenance.source_manifest import MANIFEST_NAME

    try:
        root = StorageLayout(storage_root).source_root(source_sha)
    except Exception:
        return False
    if not root.is_dir():
        return False
    # ensure_source_root() always creates empty audio/ + video/ subdirs, so check
    # for a real artifact FILE (recursively), not just the presence of a subdir.
    for f in root.rglob("*"):
        try:
            if not f.is_file():
                continue
        except OSError:
            continue
        nm = f.name
        if nm == MANIFEST_NAME or nm.startswith(MANIFEST_NAME) or nm.endswith(".corrupt"):
            continue
        return True
    return False


def _first_existing_path(value) -> Path | None:
    """B-579: a manifest artifact value is either a path string or a list of
    them; return the first one that exists on disk, else None."""
    if value is None:
        return None
    candidates = value if isinstance(value, (list, tuple)) else [value]
    for raw in candidates:
        if raw is None:
            continue
        try:
            p = Path(raw)
        except TypeError:
            continue
        if p.is_file():
            return p.resolve()
    return None


def _manifest_artifacts_exist(artifacts) -> bool:
    """B-579: True if the manifest carries at least one real artifact path that
    exists on disk right now."""
    if not isinstance(artifacts, dict):
        return False
    return any(_first_existing_path(v) is not None for v in artifacts.values())


def _resolve_stem_paths(
    storage_root: str | Path | None,
    source_sha: str,
    manifest_artifacts: dict | None,
) -> dict[str, Path] | None:
    """B-579: resolve the four stem files, preferring the real paths recorded in
    the manifest and falling back to the global by_sha layout. Returns the full
    set only when all four exist now, else None (no done on missing files)."""
    paths: dict[str, Path] = {}
    if isinstance(manifest_artifacts, dict):
        for name in ("vocals", "drums", "bass", "other"):
            # V2 records roles as "<name>_stem"; migration as "<name>". Accept both.
            value = manifest_artifacts.get(name)
            if value is None:
                value = manifest_artifacts.get(f"{name}_stem")
            resolved = _first_existing_path(value)
            if resolved is not None:
                paths[name] = resolved
    if len(paths) == 4:
        return paths

    return _global_stem_paths(storage_root, source_sha)


def _global_stem_paths(
    storage_root: str | Path | None,
    source_sha: str,
) -> dict[str, Path] | None:
    """Return all four global stem artifacts or None when reuse is incomplete."""
    from services.storage_provenance.layout import StorageLayout

    if storage_root is None:
        from services.storage_provenance.schnitt_audio_adapter import (
            default_global_storage_root,
        )

        storage_root = default_global_storage_root()
    stem_dir = StorageLayout(storage_root).source_root(source_sha) / "audio" / "stems"
    paths = {name: (stem_dir / f"{name}.wav").resolve() for name in ("vocals", "drums", "bass", "other")}
    if not all(path.is_file() for path in paths.values()):
        return None
    return paths


def _video_outputs_reachable(
    storage_root: str | Path | None,
    source_sha: str,
    manifest_artifacts: dict | None,
) -> bool:
    """B-579 (ST-3): True if the reused video outputs are actually reachable —
    either via the real paths recorded in the manifest or via a real file in the
    by_sha source dir. Never mark a video step done on a dangling reference."""
    if _manifest_artifacts_exist(manifest_artifacts):
        return True
    return _source_root_has_artifacts(_resolved_storage_root(storage_root), source_sha)


def _resolved_storage_root(storage_root: str | Path | None) -> str | Path:
    if storage_root is not None:
        return storage_root
    from services.storage_provenance.schnitt_audio_adapter import (
        default_global_storage_root,
    )

    return default_global_storage_root()


def _apply_audio_stem_references(
    session: Session,
    *,
    media_id: int,
    stem_paths: dict[str, Path],
) -> None:
    from database.models import AudioTrack

    track = session.get(AudioTrack, media_id)
    if track is None:
        raise ValueError(f"AudioTrack {media_id} nicht gefunden fuer Stem-Reuse")
    track.stem_vocals_path = str(stem_paths["vocals"])
    track.stem_drums_path = str(stem_paths["drums"])
    track.stem_bass_path = str(stem_paths["bass"])
    track.stem_other_path = str(stem_paths["other"])


def _format_model_from_manifest(job: dict) -> str:
    model = job.get("model")
    version = job.get("model_version")
    if model and version:
        return f"{model} {version}"
    if model:
        return str(model)
    return str(job.get("step_id", ""))


def _parse_iso(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


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
