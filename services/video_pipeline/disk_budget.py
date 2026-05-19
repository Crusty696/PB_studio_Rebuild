"""Disk-Budget-Helper (Phase 73).

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 73 Cross-Cutting
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


__all__ = ["DiskInfo", "probe_disk", "has_disk_budget", "DiskFull"]


class DiskFull(RuntimeError):
    pass


@dataclass(frozen=True)
class DiskInfo:
    total_gb: float
    used_gb: float
    free_gb: float
    path: str


def probe_disk(path: Path) -> DiskInfo:
    """Liefert Disk-Stats fuer das Volume das ``path`` enthaelt."""
    path = Path(path)
    target = path if path.exists() else path.parent
    while not target.exists():
        target = target.parent
    usage = shutil.disk_usage(str(target))
    return DiskInfo(
        total_gb=usage.total / 1e9,
        used_gb=usage.used / 1e9,
        free_gb=usage.free / 1e9,
        path=str(target),
    )


def has_disk_budget(path: Path, required_gb: float, *, reserve_gb: float = 2.0) -> bool:
    info = probe_disk(path)
    return info.free_gb >= required_gb + reserve_gb


def assert_disk_budget(path: Path, required_gb: float, *, reserve_gb: float = 2.0) -> DiskInfo:
    info = probe_disk(path)
    if info.free_gb < required_gb + reserve_gb:
        raise DiskFull(
            f"Insufficient disk on {info.path}: need {required_gb + reserve_gb:.2f} GB, "
            f"have {info.free_gb:.2f} GB free"
        )
    return info
