"""B-539: by_sha provenance manifest.

The cross-project-reuse lookup historically queried the active project DB for a
*previous* project that analysed the same source. With per-project SQLite DBs
that query never sees other projects, so reuse silently failed.

This module persists a small ``provenance_manifest.json`` next to the
content-addressed ``by_sha/<sha>/`` artifacts. Because ``by_sha`` is global
(``%APPDATA%/PBStudio/storage``), the manifest is visible across projects and
lets the reuse lookup recover the originating project, model and timestamp even
though that data lives in a different project's DB.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from services.storage_provenance.layout import StorageLayout

MANIFEST_NAME = "provenance_manifest.json"


def _iso(value) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def manifest_path(storage_root: str | Path, source_sha256: str) -> Path:
    return StorageLayout(storage_root).source_root(source_sha256) / MANIFEST_NAME


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

    Dedup key is ``(project_path, step_id)``. ``project_path`` is used because
    ``project_id`` is only unique *within* a single project DB — with
    per-project DBs two different projects can both have id=1, so an id-based
    key would let one project's migration clobber another's entry.
    Best-effort: never raises into the caller's analysis path.
    """
    layout = StorageLayout(storage_root)
    root = layout.ensure_source_root(source_sha256)
    path = root / MANIFEST_NAME

    data: dict = {"source_sha256": source_sha256, "jobs": []}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("jobs"), list):
                data = loaded
        except (ValueError, OSError):
            data = {"source_sha256": source_sha256, "jobs": []}

    entry = {
        "project_id": int(project_id),
        "project_name": project_name,
        "project_path": str(project_path),
        "step_id": step_id,
        "model": model,
        "model_version": model_version,
        "finished_at": _iso(finished_at),
    }
    jobs = [
        j
        for j in data.get("jobs", [])
        if not (j.get("project_path") == entry["project_path"] and j.get("step_id") == entry["step_id"])
    ]
    jobs.append(entry)
    data["jobs"] = jobs
    data["source_sha256"] = source_sha256

    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return path


def read_manifest_jobs(storage_root: str | Path, source_sha256: str) -> list[dict]:
    """Return the recorded job entries for a source, or ``[]`` if none/unreadable."""
    try:
        path = manifest_path(storage_root, source_sha256)
    except Exception:  # invalid sha — treat as no manifest
        return []
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    jobs = data.get("jobs")
    return jobs if isinstance(jobs, list) else []
