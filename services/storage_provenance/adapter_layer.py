from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy.orm import Session

from database.models import AnalysisArtifact, AnalysisJob
from services.storage_provenance.layout import StorageLayout


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_LEGACY_STEM_FILENAMES = {
    "vocals_stem": "vocals.flac",
    "drums_stem": "drums.flac",
    "bass_stem": "bass.flac",
    "other_stem": "other.flac",
}


def resolve_artifact_path(
    session: Session,
    track_id_or_sha: int | str,
    role: str,
    *,
    storage_root: str | Path,
    legacy_stems_root: str | Path | None = None,
) -> Path:
    """Resolve a provenance artifact or legacy V2 stem path."""

    identifier = str(track_id_or_sha)
    if _SHA256_RE.match(identifier):
        artifact_path = _resolve_by_source_sha(session, identifier.lower(), role, storage_root=Path(storage_root))
        if artifact_path is not None:
            return artifact_path

    if legacy_stems_root is not None:
        legacy_path = _legacy_stem_path(Path(legacy_stems_root), identifier, role)
        if legacy_path.exists():
            return legacy_path

    raise FileNotFoundError(f"Artifact not found for {track_id_or_sha!r} role={role!r}")


def _resolve_by_source_sha(session: Session, source_sha256: str, role: str, *, storage_root: Path) -> Path | None:
    row = (
        session.query(AnalysisArtifact)
        .join(AnalysisJob, AnalysisArtifact.job_id == AnalysisJob.id)
        .filter(
            AnalysisJob.source_sha256 == source_sha256,
            AnalysisJob.status == "done",
            AnalysisArtifact.artifact_role == role,
        )
        .order_by(AnalysisArtifact.id.desc())
        .first()
    )
    if row is None:
        return None
    return StorageLayout(storage_root).source_root(source_sha256) / row.path


def _legacy_stem_path(legacy_stems_root: Path, track_id: str, role: str) -> Path:
    filename = _LEGACY_STEM_FILENAMES.get(role, role)
    return legacy_stems_root / track_id / filename
