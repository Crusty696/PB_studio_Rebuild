from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import shutil

from sqlalchemy.orm import Session

from database.models import AnalysisArtifact, AnalysisJob, Project, ProjectSource
from services.storage_provenance.layout import StorageLayout


@dataclass(frozen=True)
class StorageBrowserRow:
    source_sha256: str
    file_name: str
    projects_used_by: str
    project_count: int
    stages_done: int
    total_bytes: int
    last_used: datetime | None

    @property
    def short_sha(self) -> str:
        return self.source_sha256[:12]


@dataclass(frozen=True)
class StorageDeleteResult:
    deleted_sources: int
    deleted_jobs: int
    deleted_artifacts: int
    deleted_storage_dirs: int = 0
    freed_bytes: int = 0


class StorageBrowserService:
    """Read and cleanup provenance-backed analysis storage."""

    def __init__(self, session: Session, *, storage_root: str | Path | None = None) -> None:
        self.session = session
        self.layout = StorageLayout(storage_root) if storage_root is not None else None

    def list_sources(
        self,
        *,
        unused_only: bool = False,
        older_than_days: int | None = None,
        now: datetime | None = None,
    ) -> list[StorageBrowserRow]:
        rows: list[StorageBrowserRow] = []
        source_hashes = [
            value[0]
            for value in (
                self.session.query(AnalysisJob.source_sha256)
                .distinct()
                .order_by(AnalysisJob.source_sha256.asc())
                .all()
            )
        ]

        cutoff = None
        if older_than_days is not None and older_than_days > 0:
            cutoff = (now or datetime.utcnow()) - timedelta(days=older_than_days)

        for source_sha in source_hashes:
            jobs = self.session.query(AnalysisJob).filter_by(source_sha256=source_sha).all()
            sources = (
                self.session.query(ProjectSource, Project)
                .join(Project, Project.id == ProjectSource.project_id)
                .filter(ProjectSource.source_sha256 == source_sha)
                .order_by(ProjectSource.last_seen_at.desc().nullslast(), Project.name.asc())
                .all()
            )
            if unused_only and sources:
                continue

            last_used = _latest_datetime(
                [source.last_seen_at for source, _project in sources]
                + [job.finished_at for job in jobs]
            )
            if cutoff is not None and (last_used is None or last_used >= cutoff):
                continue

            rows.append(
                StorageBrowserRow(
                    source_sha256=source_sha,
                    file_name=_file_name(sources),
                    projects_used_by=", ".join(project.name for _source, project in sources) or "-",
                    project_count=len(sources),
                    stages_done=len({job.step_id for job in jobs if job.status == "done"}),
                    total_bytes=self._total_bytes(jobs),
                    last_used=last_used,
                )
            )

        rows.sort(key=lambda row: (row.last_used or datetime.min, row.source_sha256), reverse=True)
        return rows

    def delete_analysis_sources(
        self,
        source_sha256_values: list[str],
        *,
        delete_storage_dirs: bool = False,
    ) -> StorageDeleteResult:
        unique_sources = sorted(set(source_sha256_values))
        if not unique_sources:
            return StorageDeleteResult(0, 0, 0, 0)

        jobs = self.session.query(AnalysisJob).filter(AnalysisJob.source_sha256.in_(unique_sources)).all()
        job_ids = [job.id for job in jobs]
        artifact_count = 0
        if job_ids:
            artifact_count = (
                self.session.query(AnalysisArtifact)
                .filter(AnalysisArtifact.job_id.in_(job_ids))
                .count()
            )
        for job in jobs:
            self.session.delete(job)

        deleted_dirs = 0
        freed_bytes = 0
        if delete_storage_dirs and self.layout is not None:
            deleted_dirs, freed_bytes = self._delete_storage_dirs(unique_sources)

        self.session.commit()
        return StorageDeleteResult(
            deleted_sources=len(unique_sources),
            deleted_jobs=len(jobs),
            deleted_artifacts=artifact_count,
            deleted_storage_dirs=deleted_dirs,
            freed_bytes=freed_bytes,
        )

    def _total_bytes(self, jobs: list[AnalysisJob]) -> int:
        job_ids = [job.id for job in jobs if job.id is not None]
        if not job_ids:
            return 0
        values = (
            self.session.query(AnalysisArtifact.bytes)
            .filter(AnalysisArtifact.job_id.in_(job_ids))
            .all()
        )
        return sum(int(value[0] or 0) for value in values)

    def _delete_storage_dirs(self, source_hashes: list[str]) -> tuple[int, int]:
        assert self.layout is not None
        storage_root = self.layout.storage_root.absolute()
        deleted = 0
        freed = 0
        for source_sha in source_hashes:
            root = self.layout.source_root(source_sha).absolute()
            try:
                root.relative_to(storage_root)
            except ValueError as exc:
                raise ValueError(f"Refusing to delete outside storage root: {root}") from exc
            if root.exists():
                freed += _dir_size(root)
                shutil.rmtree(root)
                deleted += 1
        return deleted, freed


def _dir_size(path: Path) -> int:
    """Summe der Dateigroessen unter path (fuer 'X freigegeben'-Anzeige, B-547)."""
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            pass
    return total


def _file_name(sources: list[tuple[ProjectSource, Project]]) -> str:
    if not sources:
        return "-"
    return Path(sources[0][0].current_source_path).name


def _latest_datetime(values: list[datetime | None]) -> datetime | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return max(present)
