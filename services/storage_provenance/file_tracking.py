from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from database.models import ProjectSource
from services.storage_provenance.source_identity import compute_source_sha256


@dataclass(frozen=True)
class FileRepairResult:
    checked: int
    repaired: int
    missing: tuple[int, ...]


def repair_missing_sources(
    session: Session,
    *,
    search_roots: Iterable[str | Path],
    media_type: str,
    source_ids: Iterable[int] | None = None,
) -> FileRepairResult:
    """Repair missing ``project_sources.current_source_path`` values by SHA."""

    roots = [Path(root) for root in search_roots]
    query = session.query(ProjectSource)
    if source_ids is not None:
        query = query.filter(ProjectSource.id.in_(tuple(source_ids)))
    sources = query.all()
    repaired = 0
    missing: list[int] = []

    for source in sources:
        current = Path(source.current_source_path)
        if current.exists():
            continue

        match = _find_by_sha(source.source_sha256, roots, media_type=media_type)
        if match is None:
            missing.append(source.id)
            continue

        source.current_source_path = str(match)
        source.last_seen_at = datetime.utcnow()
        repaired += 1

    session.commit()
    return FileRepairResult(checked=len(sources), repaired=repaired, missing=tuple(missing))


def _find_by_sha(source_sha256: str, roots: list[Path], *, media_type: str) -> Path | None:
    for root in roots:
        if not root.exists():
            continue
        for candidate in root.rglob("*"):
            if not candidate.is_file():
                continue
            try:
                candidate_sha = compute_source_sha256(candidate, media_type=media_type, mode="strict")
            except (OSError, ValueError):
                continue
            if candidate_sha == source_sha256:
                return candidate
    return None
