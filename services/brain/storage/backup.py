"""Brain V3 — Backup-Service (Phase 6, 06_PHASES.md Z.453-457).

Atomarisches Backup aller V3-Hirn-Store-DBs via VACUUM INTO.

VACUUM INTO ist online + transaktional + ergibt vollstaendiges Backup
(SQLite-Doc bestaetigt). Sicherer als File-Copy, da keine Race-Condition
mit aktiven Writern.

Retention-Policy: pro Aufruf konfigurierbar; Default = letzte 4 Backups.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from services.brain import paths

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BackupResult:
    timestamp: str
    backup_dir: Path
    files_written: list[Path]
    skipped: list[Path]


@dataclass(frozen=True)
class ScheduledBackupResult:
    ran: bool
    reason: str
    backup: BackupResult | None
    deleted: list[Path]


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_brain_v3_store(
    backup_dir: Optional[Path] = None,
    *,
    brain_dir: Optional[Path] = None,
) -> BackupResult:
    """Erstellt atomares Backup aller V3-Hirn-Store-DBs.

    Args:
        backup_dir: Wurzel-Verzeichnis, in das ein Sub-Ordner
            `brain_v3_backup_<timestamp>/` angelegt wird. Default:
            `<brain_v3_app_dir>/backups/`.
        brain_dir: V3-App-Dir-Override (Tests). Default: `paths.brain_v3_app_dir()`.

    Returns:
        BackupResult mit timestamp + Pfaden der geschriebenen DBs.
    """
    src_dir = Path(brain_dir) if brain_dir else paths.brain_v3_app_dir()
    root = Path(backup_dir) if backup_dir else (src_dir / "backups")
    root.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    target = root / f"brain_v3_backup_{ts}"
    target.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    skipped: list[Path] = []
    for name in ("weights.db", "patterns.db", "embedding_cache.db"):
        src = src_dir / name
        dst = target / name
        if not src.exists():
            skipped.append(src)
            continue
        try:
            conn = sqlite3.connect(str(src))
            try:
                conn.execute("VACUUM INTO ?", (str(dst),))
            finally:
                conn.close()
            written.append(dst)
            logger.info("backup_brain_v3_store: %s -> %s", name, dst)
        except sqlite3.Error as exc:
            logger.warning("backup failed for %s: %s", name, exc)
            skipped.append(src)
    return BackupResult(
        timestamp=ts, backup_dir=target,
        files_written=written, skipped=skipped,
    )


def prune_old_backups(
    backup_root: Optional[Path] = None,
    keep: int = 4,
) -> list[Path]:
    """Loescht alte Backup-Verzeichnisse, behaelt nur die letzten `keep`.

    Args:
        backup_root: Wurzel mit `brain_v3_backup_<timestamp>/`-Subdirs.
        keep: Anzahl behaltener Backups (default 4 pro Plan z.456).

    Returns:
        Liste der geloeschten Verzeichnisse.
    """
    root = Path(backup_root) if backup_root else (paths.brain_v3_app_dir() / "backups")
    if not root.exists():
        return []
    candidates = sorted(
        [p for p in root.iterdir() if p.is_dir() and p.name.startswith("brain_v3_backup_")],
        key=lambda p: p.name,
        reverse=True,
    )
    to_delete = candidates[keep:]
    deleted: list[Path] = []
    import shutil
    for p in to_delete:
        try:
            shutil.rmtree(p)
            deleted.append(p)
            logger.info("prune_old_backups: removed %s", p)
        except OSError as exc:
            logger.warning("prune_old_backups: failed to remove %s: %s", p, exc)
    return deleted


def run_weekly_backup_if_due(
    *,
    state_file: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
    brain_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
    interval_days: int = 7,
    keep: int = 4,
) -> ScheduledBackupResult:
    """Fuehrt woechentliches Brain-V3-Backup aus, wenn Intervall faellig ist."""
    if interval_days <= 0:
        raise ValueError("interval_days muss > 0 sein")
    current = now or datetime.now()
    src_dir = Path(brain_dir) if brain_dir else paths.brain_v3_app_dir()
    root = Path(backup_dir) if backup_dir else (src_dir / "backups")
    marker = Path(state_file) if state_file else (root / "last_weekly_backup.txt")

    last_run = _read_backup_marker(marker)
    if last_run is not None and current - last_run < timedelta(days=interval_days):
        return ScheduledBackupResult(
            ran=False,
            reason="not_due",
            backup=None,
            deleted=[],
        )

    backup = backup_brain_v3_store(backup_dir=root, brain_dir=src_dir)
    deleted = prune_old_backups(root, keep=keep)
    if not backup.files_written:
        return ScheduledBackupResult(
            ran=False,
            reason="no_dbs",
            backup=backup,
            deleted=deleted,
        )

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(current.isoformat(timespec="seconds"), encoding="utf-8")
    logger.info(
        "run_weekly_backup_if_due: backup=%s files=%d deleted=%d",
        backup.backup_dir,
        len(backup.files_written),
        len(deleted),
    )
    return ScheduledBackupResult(
        ran=True,
        reason="due",
        backup=backup,
        deleted=deleted,
    )


def _read_backup_marker(path: Path) -> datetime | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError as exc:
        logger.warning("weekly backup marker unreadable %s: %s", path, exc)
        return None
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        logger.warning("weekly backup marker invalid %s: %r", path, raw)
        return None
