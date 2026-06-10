"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17.

T7.1: Stems-Cleanup-Policy + Disk-Quota (Q-H 50 GB default).
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

# Defaults (Q-H + Plan):
STEMS_RETENTION_DAYS = 30  # 30 Tage
STEMS_MAX_TOTAL_GB = int(os.environ.get("PB_STEMS_MAX_GB", "50"))  # Q-H 50 GB


def _stems_root() -> Path:
    return Path("storage") / "stems"


def _track_dir(track_id: int) -> Path:
    return _stems_root() / str(track_id)


def _dir_size_bytes(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def cleanup_stems_older_than(days: int = STEMS_RETENTION_DAYS, root: Path | None = None) -> list[Path]:
    """Loescht Stem-Track-Verzeichnisse aelter als N Tage.

    Returns: Liste der geloeschten Verzeichnisse.
    """
    root = root or _stems_root()
    if not root.exists():
        return []
    cutoff = time.time() - days * 86400
    deleted = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        try:
            mtime = child.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            shutil.rmtree(child, ignore_errors=True)
            deleted.append(child)
    return deleted


def cleanup_on_project_close(project_id: int, root: Path | None = None) -> Path | None:
    """Beim Projekt-Schliessen optional Cleanup.

    Konservativ: Nicht alle Stems loeschen (mehrere Projekte koennen sharen).
    Stub-Hook fuer Future. Liefert root.
    """
    return root or _stems_root()


def cleanup_to_quota(max_gb: int = STEMS_MAX_TOTAL_GB, root: Path | None = None) -> list[Path]:
    """LRU-Cleanup wenn Total-Disk-Usage > max_gb.

    Sortiert Track-Verzeichnisse nach mtime (oldest first), loescht bis
    Disk-Usage unter Quota.

    Returns: Liste der geloeschten Verzeichnisse.
    """
    root = root or _stems_root()
    if not root.exists():
        return []
    max_bytes = max_gb * 1024**3

    dirs = [d for d in root.iterdir() if d.is_dir()]
    total = sum(_dir_size_bytes(d) for d in dirs)
    if total <= max_bytes:
        return []

    dirs_sorted = sorted(dirs, key=lambda d: d.stat().st_mtime)
    deleted = []
    for d in dirs_sorted:
        if total <= max_bytes:
            break
        sz = _dir_size_bytes(d)
        shutil.rmtree(d, ignore_errors=True)
        total -= sz
        deleted.append(d)
    return deleted
