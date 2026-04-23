"""BackupService — SQLite snapshots before destructive actions + daily checks.

Strategy per Design §8.5:
  - Trigger 1: destructive-action hook (pattern reset, enricher-version bump, …).
  - Trigger 2: daily on app-start if last backup > 24h.
  - Rolling prune: keep the 14 most recent, delete older.
  - Filename: `pb_studio_YYYY-MM-DD-HHMMSS[_<reason>].db`.
  - Scope: full DB copy (cheaper than selective; 14×100 MB = 1.4 GB max).

Uses shutil.copy2 — preserves metadata, single-file atomic copy. No SQLAlchemy
connection needed; SQLite WAL allows hot-copy safely (readers don't block copy).

Public API:
  - backup(reason: str) -> Path             # always creates a new snapshot
  - backup_if_stale(reason: str = "daily") -> Path | None
                                             # creates only if last backup > 24h
  - prune() -> int                           # returns how many were deleted
  - list_backups() -> list[BackupInfo]       # sorted newest-first
  - pattern_reset_context(reason=...)        # context manager that triggers backup before destructive op
"""

from __future__ import annotations

import logging
import re
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

_FILENAME_RE = re.compile(r"pb_studio_(\d{4}-\d{2}-\d{2}-\d{6})(?:_(\w+))?\.db$")
_TS_FORMAT = "%Y-%m-%d-%H%M%S"


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    created_at: datetime
    size_bytes: int
    reason: str | None = None


class BackupService:
    ROLLING_WINDOW: int = 14
    STALE_THRESHOLD: timedelta = timedelta(hours=24)

    def __init__(
        self,
        db_path: Path | str,
        backup_dir: Path | str,
    ) -> None:
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def backup(self, reason: str = "manual") -> Path:
        """Create a fresh dated snapshot. Returns the path to the new backup.
        Prunes the rolling window afterwards.

        Raises:
            FileNotFoundError: if db_path doesn't exist.
        """
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

        ts = datetime.now(timezone.utc).strftime(_TS_FORMAT)
        if reason and reason != "manual":
            filename = f"pb_studio_{ts}_{reason}.db"
        else:
            filename = f"pb_studio_{ts}.db"

        dest = self.backup_dir / filename
        shutil.copy2(str(self.db_path), str(dest))
        logger.info("Backup created: %s", dest)

        self.prune()
        return dest

    def backup_if_stale(self, reason: str = "daily") -> Path | None:
        """Create a backup only if the most recent existing backup is older than
        STALE_THRESHOLD (24h). Returns the new backup path, or None if no backup
        was needed.
        """
        existing = self.list_backups()
        if existing:
            newest = existing[0]
            cutoff = datetime.now(timezone.utc) - self.STALE_THRESHOLD
            if newest.created_at > cutoff:
                logger.debug(
                    "Backup skipped — last backup within threshold: %s", newest.path
                )
                return None

        return self.backup(reason=reason)

    def prune(self) -> int:
        """Delete the oldest backups until at most ROLLING_WINDOW remain.
        Returns count deleted."""
        backups = self.list_backups()
        to_delete = backups[self.ROLLING_WINDOW :]
        for info in to_delete:
            try:
                info.path.unlink()
                logger.info("Pruned old backup: %s", info.path)
            except OSError as exc:
                logger.warning("Failed to delete backup %s: %s", info.path, exc)
        return len(to_delete)

    def list_backups(self) -> list[BackupInfo]:
        """Return existing backups sorted newest-first."""
        results: list[BackupInfo] = []
        for p in self.backup_dir.iterdir():
            if not p.is_file():
                continue
            match = _FILENAME_RE.search(p.name)
            if not match:
                continue
            ts_str, reason_str = match.group(1), match.group(2)
            try:
                created_at = datetime.strptime(ts_str, _TS_FORMAT).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                logger.debug("Skipping file with unparseable timestamp: %s", p.name)
                continue
            results.append(
                BackupInfo(
                    path=p,
                    created_at=created_at,
                    size_bytes=p.stat().st_size,
                    reason=reason_str,
                )
            )
        results.sort(key=lambda b: b.created_at, reverse=True)
        return results

    @contextmanager
    def pattern_reset_context(self, reason: str = "pattern_reset") -> Iterator[None]:
        """Context manager: creates a backup BEFORE yielding, so destructive ops
        are guarded. Intended usage:

            with backup_service.pattern_reset_context():
                session.execute("DELETE FROM mem_learned_pattern")
                session.commit()

        The backup is created unconditionally (not skip-if-stale) since the
        caller is about to do something potentially harmful.
        """
        self.backup(reason=reason)
        yield
