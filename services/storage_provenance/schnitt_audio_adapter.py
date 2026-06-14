from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.orm import Session

from services.storage_provenance.storage_migration import (
    StorageMigrationResult,
    StorageMigrationService,
)


def default_global_storage_root() -> Path:
    """Return the Plan-C global storage root."""

    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "PBStudio" / "storage"
    return Path.home() / ".PBStudio" / "storage"


def ensure_schnitt_audio_adapter(
    session: Session,
    *,
    storage_root: str | Path | None = None,
) -> StorageMigrationResult:
    """Ensure legacy SCHNITT stem paths are mirrored into by_sha storage."""

    root = Path(storage_root) if storage_root is not None else default_global_storage_root()
    return StorageMigrationService(session, storage_root=root).migrate_existing_outputs()
