"""B-539: by_sha provenance manifest.

The cross-project-reuse lookup historically queried the active project DB for a
*previous* project that analysed the same source. With per-project SQLite DBs
that query never sees other projects, so reuse silently failed.

This module persists a small ``provenance_manifest.json`` next to the
content-addressed ``by_sha/<sha>/`` artifacts. Because ``by_sha`` is global
(``%APPDATA%/PBStudio/storage``), the manifest is visible across projects and
lets the reuse lookup recover the originating project, model and timestamp even
though that data lives in a different project's DB.

Robustness (B-543..B-546):
- B-543: writes are atomic (temp + os.replace) and serialised by a cross-process
  file lock; a corrupt manifest is backed up + logged, never silently wiped.
- B-545: read/write failures are logged (warning), not silently swallowed.
- B-546: project identity compares paths via os.path.normcase(normpath) so a
  rename/move or Windows case difference does not split or self-match entries.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from services.storage_provenance.layout import StorageLayout

logger = logging.getLogger(__name__)

MANIFEST_NAME = "provenance_manifest.json"
_LOCK_TIMEOUT_SEC = 10.0
_LOCK_STALE_SEC = 60.0


def _iso(value) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def _norm_path(value) -> str:
    """B-546: normalise a project path for identity comparison (case + separators)."""
    return os.path.normcase(os.path.normpath(str(value)))


def manifest_path(storage_root: str | Path, source_sha256: str) -> Path:
    return StorageLayout(storage_root).source_root(source_sha256) / MANIFEST_NAME


class _ManifestLock:
    """B-543: best-effort cross-process lock via O_CREAT|O_EXCL lockfile.

    Serialises concurrent record_manifest_job() calls on the same source so the
    read-modify-write does not lose updates. A stale lock (older than
    _LOCK_STALE_SEC, e.g. from a crashed process) is broken; if acquisition
    times out we proceed anyway (availability over strictness) but log it.
    """

    def __init__(self, lock_path: Path):
        self._lock_path = lock_path
        self._fd: int | None = None

    def __enter__(self) -> "_ManifestLock":
        start = time.monotonic()
        while True:
            try:
                self._fd = os.open(str(self._lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR)
                return self
            except FileExistsError:
                # break a stale lock left behind by a crashed writer
                try:
                    age = time.time() - self._lock_path.stat().st_mtime
                    if age > _LOCK_STALE_SEC:
                        logger.warning("manifest lock stale (%.0fs), breaking: %s", age, self._lock_path)
                        self._lock_path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.monotonic() - start > _LOCK_TIMEOUT_SEC:
                    logger.warning("manifest lock timeout, proceeding unlocked: %s", self._lock_path)
                    return self
                time.sleep(0.05)

    def __exit__(self, *exc) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        try:
            self._lock_path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("manifest lock release failed %s: %s", self._lock_path, e)


def _load_manifest(path: Path, source_sha256: str) -> dict:
    """Load manifest; on corruption back it up + log instead of silent reset (B-543/B-545)."""
    fresh = {"source_sha256": source_sha256, "jobs": []}
    if not path.is_file():
        return fresh
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("jobs"), list):
            return loaded
        raise ValueError("manifest shape invalid")
    except (ValueError, OSError) as e:
        logger.warning("manifest corrupt at %s (%s) — backing up + resetting", path, e)
        try:
            path.replace(path.with_suffix(path.suffix + ".corrupt"))
        except OSError as be:
            logger.warning("manifest corrupt-backup failed %s: %s", path, be)
        return fresh


def record_manifest_job(
    storage_root: str | Path,
    source_sha256: str,
    *,
    project_id: int,
    project_name: str,
    project_path: str,
    step_id: str,
    model: str | None = None,
    model_version: str | None = None,
    finished_at=None,
) -> Path:
    """Upsert one job entry into the source's provenance manifest.

    Dedup key is the normalised ``(project_path, step_id)`` (B-546): ``project_id``
    is only unique within a single project DB, so an id-based key would let two
    per-project DBs (both id=1) clobber each other; ``project_path`` is global,
    and normalisation keeps a rename/case change from creating a duplicate.
    Atomic + locked write (B-543). Best-effort: never raises into the analysis path.
    """
    layout = StorageLayout(storage_root)
    root = layout.ensure_source_root(source_sha256)
    path = root / MANIFEST_NAME

    entry = {
        "project_id": int(project_id),
        "project_name": project_name,
        "project_path": str(project_path),
        "step_id": step_id,
        "model": model,
        "model_version": model_version,
        "finished_at": _iso(finished_at),
    }
    norm_pp = _norm_path(project_path)

    with _ManifestLock(root / (MANIFEST_NAME + ".lock")):
        data = _load_manifest(path, source_sha256)
        jobs = [
            j
            for j in data.get("jobs", [])
            if not (_norm_path(j.get("project_path", "")) == norm_pp and j.get("step_id") == step_id)
        ]
        jobs.append(entry)
        data["jobs"] = jobs
        data["source_sha256"] = source_sha256

        # B-543: atomic write — temp file + os.replace so a concurrent reader
        # never sees a half-written file.
        tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(str(tmp), str(path))
    return path


def read_manifest_jobs(storage_root: str | Path, source_sha256: str) -> list[dict]:
    """Return the recorded job entries for a source, or ``[]`` if none/unreadable."""
    try:
        path = manifest_path(storage_root, source_sha256)
    except Exception as e:  # invalid sha — treat as no manifest
        logger.warning("manifest_path failed for sha=%r: %s", source_sha256, e)
        return []
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        logger.warning("manifest read/parse failed at %s: %s", path, e)
        return []
    jobs = data.get("jobs")
    return jobs if isinstance(jobs, list) else []
