from __future__ import annotations

import hashlib
import json
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from database.models import AnalysisArtifact, AnalysisJob, Base, Project, ProjectSource
from services.storage_provenance.disk_budget import DiskBudgetService, InsufficientDiskSpace
from services.storage_provenance.layout import StorageLayout


ARTIFACTS = ROOT / "tests" / "qa_artifacts"
OUT = ARTIFACTS / "otk021_disk_budget_real_result.json"


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _write_bytes(path: Path, size: int, fill: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(fill * size)


def _seed_job(
    session: Session,
    *,
    source_sha: str,
    step_id: str,
    artifact_path: str,
    bytes_: int,
    finished_at: datetime,
) -> None:
    job = AnalysisJob(
        source_sha256=source_sha,
        step_id=step_id,
        step_version="1",
        params_hash=f"params-{step_id}",
        status="done",
        finished_at=finished_at,
    )
    job.artifacts.append(
        AnalysisArtifact(
            artifact_type="bin",
            artifact_role=f"{step_id}-artifact",
            path=artifact_path,
            bytes=bytes_,
        )
    )
    session.add(job)


@contextmanager
def _session(db_path: Path):
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def main() -> int:
    now = datetime(2026, 6, 30, 12, 0, 0)
    work = ARTIFACTS / "otk021_disk_budget_real"
    storage_root = work / "storage"
    db_path = work / "disk_budget.sqlite"
    layout = StorageLayout(storage_root)
    work.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    used_a = _sha("disk-budget-used-a")
    used_b = _sha("disk-budget-used-b")
    unused_old = _sha("disk-budget-unused-old")
    unused_recent = _sha("disk-budget-unused-recent")

    file_sizes = {
        used_a: 4096,
        used_b: 2048,
        unused_old: 3072,
        unused_recent: 1024,
    }
    db_bytes = {
        used_a: 4000,
        used_b: 2000,
        unused_old: 3000,
        unused_recent: 1000,
    }

    for source_sha, size in file_sizes.items():
        source_root = layout.ensure_source_root(source_sha)
        _write_bytes(source_root / "artifact.bin", size, source_sha[:1].encode("ascii"))

    with _session(db_path) as session:
        session.add_all(
            [
                Project(id=1, name="Disk Budget A", path=str(work / "project-a"), resolution="1920x1080", fps=30.0),
                Project(id=2, name="Disk Budget B", path=str(work / "project-b"), resolution="1920x1080", fps=30.0),
            ]
        )
        session.add_all(
            [
                ProjectSource(
                    project_id=1,
                    source_sha256=used_a,
                    current_source_path=str(work / "a.wav"),
                    last_seen_at=now,
                ),
                ProjectSource(
                    project_id=2,
                    source_sha256=used_b,
                    current_source_path=str(work / "b.mp4"),
                    last_seen_at=now,
                ),
            ]
        )
        _seed_job(
            session,
            source_sha=used_a,
            step_id="audio.v2.stems",
            artifact_path="artifact.bin",
            bytes_=db_bytes[used_a],
            finished_at=now,
        )
        _seed_job(
            session,
            source_sha=used_b,
            step_id="video.plan_a.outputs",
            artifact_path="artifact.bin",
            bytes_=db_bytes[used_b],
            finished_at=now,
        )
        _seed_job(
            session,
            source_sha=unused_old,
            step_id="video.scene_detect",
            artifact_path="artifact.bin",
            bytes_=db_bytes[unused_old],
            finished_at=now - timedelta(days=45),
        )
        _seed_job(
            session,
            source_sha=unused_recent,
            step_id="audio.preview",
            artifact_path="artifact.bin",
            bytes_=db_bytes[unused_recent],
            finished_at=now - timedelta(days=5),
        )
        session.commit()

        service = DiskBudgetService(session, storage_root=storage_root)
        summary = service.summarize()
        estimate = service.estimate_unused_cleanup(older_than_days=30, now=now)
        service.assert_free_space_for_migration(required_bytes=1)
        real_disk_free = SimpleNamespace(**{"free": None})
        real_disk_free.free = __import__("shutil").disk_usage(storage_root).free

        low_space_error = ""
        low_space_guard_passed = False
        with patch(
            "services.storage_provenance.disk_budget.shutil.disk_usage",
            lambda _path: SimpleNamespace(free=10),
        ):
            try:
                service.assert_free_space_for_migration(required_bytes=11)
            except InsufficientDiskSpace as exc:
                low_space_error = str(exc)
                low_space_guard_passed = "required=11, free=10" in low_space_error

        project_usage = {item.project_name: item.total_bytes for item in summary.project_usage}
        result = {
            "status": "pass",
            "db_path": str(db_path),
            "storage_root": str(storage_root),
            "summary": {
                "total_bytes": summary.total_bytes,
                "source_count": summary.source_count,
                "project_usage": project_usage,
            },
            "cleanup_estimate": {
                "source_sha256_values": list(estimate.source_sha256_values),
                "reclaimable_bytes": estimate.reclaimable_bytes,
            },
            "expected": {
                "total_bytes": sum(db_bytes.values()),
                "project_usage": {
                    "Disk Budget A": db_bytes[used_a],
                    "Disk Budget B": db_bytes[used_b],
                },
                "cleanup_source_sha256_values": [unused_old],
                "cleanup_reclaimable_bytes": db_bytes[unused_old],
            },
            "file_sizes": file_sizes,
            "db_artifact_bytes": db_bytes,
            "real_disk_probe": {
                "required_bytes": 1,
                "free_bytes": real_disk_free.free,
                "passed": True,
            },
            "low_space_guard": {
                "method": "patched disk_usage free=10; disk filling intentionally not used",
                "required_bytes": 11,
                "error": low_space_error,
                "passed": low_space_guard_passed,
            },
        }

    checks = [
        result["summary"]["total_bytes"] == result["expected"]["total_bytes"],
        result["summary"]["source_count"] == 4,
        result["summary"]["project_usage"] == result["expected"]["project_usage"],
        result["cleanup_estimate"]["source_sha256_values"] == result["expected"]["cleanup_source_sha256_values"],
        result["cleanup_estimate"]["reclaimable_bytes"] == result["expected"]["cleanup_reclaimable_bytes"],
        result["real_disk_probe"]["passed"] is True,
        result["low_space_guard"]["passed"] is True,
    ]
    if not all(checks):
        result["status"] = "fail"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
