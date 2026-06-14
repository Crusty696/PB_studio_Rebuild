from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import shutil

from sqlalchemy.orm import Session

from database.models import AnalysisArtifact, AnalysisJob, Project, ProjectSource
from services.storage_provenance.storage_browser import StorageBrowserService


@dataclass(frozen=True)
class ProjectDiskUsage:
    project_id: int
    project_name: str
    total_bytes: int


@dataclass(frozen=True)
class DiskBudgetSummary:
    total_bytes: int
    source_count: int
    project_usage: tuple[ProjectDiskUsage, ...]


@dataclass(frozen=True)
class CleanupEstimate:
    source_sha256_values: tuple[str, ...]
    reclaimable_bytes: int


class InsufficientDiskSpace(RuntimeError):
    pass


class DiskBudgetService:
    """Storage budget summaries, cleanup estimates, and migration disk probe."""

    def __init__(self, session: Session, *, storage_root: str | Path) -> None:
        self.session = session
        self.storage_root = Path(storage_root)

    def summarize(self) -> DiskBudgetSummary:
        browser = StorageBrowserService(self.session)
        rows = browser.list_sources()
        project_usage = []
        for project in self.session.query(Project).filter(Project.deleted_at.is_(None)).order_by(Project.id.asc()).all():
            source_hashes = [
                value[0]
                for value in (
                    self.session.query(ProjectSource.source_sha256)
                    .filter_by(project_id=project.id)
                    .all()
                )
            ]
            project_usage.append(
                ProjectDiskUsage(
                    project_id=project.id,
                    project_name=project.name,
                    total_bytes=self._bytes_for_sources(source_hashes),
                )
            )
        return DiskBudgetSummary(
            total_bytes=sum(row.total_bytes for row in rows),
            source_count=len(rows),
            project_usage=tuple(project_usage),
        )

    def estimate_unused_cleanup(self, *, older_than_days: int, now: datetime | None = None) -> CleanupEstimate:
        rows = StorageBrowserService(self.session).list_sources(
            unused_only=True,
            older_than_days=older_than_days,
            now=now,
        )
        return CleanupEstimate(
            source_sha256_values=tuple(row.source_sha256 for row in rows),
            reclaimable_bytes=sum(row.total_bytes for row in rows),
        )

    def assert_free_space_for_migration(self, *, required_bytes: int) -> None:
        free_bytes = shutil.disk_usage(self.storage_root).free
        if free_bytes < required_bytes:
            raise InsufficientDiskSpace(
                f"Not enough free disk space for migration: required={required_bytes}, free={free_bytes}"
            )

    def _bytes_for_sources(self, source_hashes: list[str]) -> int:
        if not source_hashes:
            return 0
        job_ids = [
            value[0]
            for value in (
                self.session.query(AnalysisJob.id)
                .filter(AnalysisJob.source_sha256.in_(source_hashes))
                .all()
            )
        ]
        if not job_ids:
            return 0
        values = (
            self.session.query(AnalysisArtifact.bytes)
            .filter(AnalysisArtifact.job_id.in_(job_ids))
            .all()
        )
        return sum(int(value[0] or 0) for value in values)
