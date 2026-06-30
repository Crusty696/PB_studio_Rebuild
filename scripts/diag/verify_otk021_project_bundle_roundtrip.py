"""OTK-021 project bundle export/import verifier.

Uses real file-backed SQLite databases and real storage/by_sha files. Exports a
project into a .pbbundle with ProjectBundleService, imports it into a separate
database/storage root, then verifies project rows, provenance rows, manifest
contents, zip payload, and restored file hashes.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import zipfile

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ARTIFACT_DIR = REPO_ROOT / "tests" / "qa_artifacts"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _session(db_path: Path) -> Session:
    from database.models import Base

    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return Session(engine)


def _seed_export_project(session: Session, storage_root: Path) -> dict[str, object]:
    from database.models import AnalysisArtifact, AnalysisJob, Project, ProjectSource
    from services.storage_provenance.layout import StorageLayout

    project = Project(
        name="OTK021 Bundle Source Project",
        path=str(storage_root.parent / "source-project"),
        resolution="3840x2160",
        fps=50.0,
    )
    session.add(project)
    session.flush()

    layout = StorageLayout(storage_root)
    sources = [
        {
            "sha": "1" * 64,
            "path": storage_root.parent / "track.wav",
            "step": "audio.v2.stems",
            "artifact_role": "vocals_stem",
            "artifact_type": "stem",
            "relative": Path("audio/stems/vocals.flac"),
            "payload": b"vocals-real-roundtrip",
        },
        {
            "sha": "2" * 64,
            "path": storage_root.parent / "clip.mp4",
            "step": "video.plan_a.outputs",
            "artifact_role": "edit_proxy",
            "artifact_type": "video",
            "relative": Path("video/proxies/proxy.mp4"),
            "payload": b"proxy-real-roundtrip",
        },
    ]

    expected_hashes: dict[str, str] = {}
    for item in sources:
        source_sha = str(item["sha"])
        session.add(
            ProjectSource(
                project_id=project.id,
                source_sha256=source_sha,
                current_source_path=str(item["path"]),
                last_seen_at=datetime(2026, 6, 30, 12, 0, 0),
            )
        )
        job = AnalysisJob(
            source_sha256=source_sha,
            step_id=str(item["step"]),
            step_version="1",
            params_hash=f"params-{item['step']}",
            status="done",
            produced_by_model="OTK021Verifier",
            produced_by_model_version="1",
            coverage_percent=100,
            started_at=datetime(2026, 6, 30, 12, 1, 0),
            finished_at=datetime(2026, 6, 30, 12, 2, 0),
            duration_seconds=60.0,
        )
        file_path = layout.ensure_source_root(source_sha) / item["relative"]
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(item["payload"])
        rel_path = str(item["relative"]).replace("\\", "/")
        job.artifacts.append(
            AnalysisArtifact(
                artifact_type=str(item["artifact_type"]),
                artifact_role=str(item["artifact_role"]),
                path=rel_path,
                bytes=file_path.stat().st_size,
                sha256=_sha256(file_path),
            )
        )
        session.add(job)
        expected_hashes[
            f"storage/by_sha/{source_sha[:2]}/{source_sha}/{rel_path}"
        ] = _sha256(file_path)

    session.commit()
    return {
        "project_id": int(project.id),
        "project_name": project.name,
        "expected_hashes": expected_hashes,
        "source_count": len(sources),
    }


def _inspect_import(db_path: Path, storage_root: Path) -> dict[str, object]:
    from database.models import AnalysisArtifact, AnalysisJob, Project, ProjectSource

    with _session(db_path) as session:
        projects = session.query(Project).all()
        sources = session.query(ProjectSource).all()
        jobs = session.query(AnalysisJob).all()
        artifacts = session.query(AnalysisArtifact).all()
        return {
            "project_count": len(projects),
            "project_names": [project.name for project in projects],
            "project_paths": [project.path for project in projects],
            "source_count": len(sources),
            "job_count": len(jobs),
            "artifact_count": len(artifacts),
            "job_steps": sorted(job.step_id for job in jobs),
            "artifact_roles": sorted(artifact.artifact_role for artifact in artifacts),
            "restored_hashes": {
                f"storage/{path.relative_to(storage_root).as_posix()}": _sha256(path)
                for path in sorted(storage_root.rglob("*"))
                if path.is_file()
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-workdir", action="store_true")
    args = parser.parse_args()

    from services.storage_provenance.project_bundle import ProjectBundleService

    work_dir = Path(tempfile.mkdtemp(prefix="pb-otk021-project-bundle-", dir=str(ARTIFACT_DIR)))
    export_db = work_dir / "export" / "pb_studio.db"
    import_db = work_dir / "import" / "pb_studio.db"
    source_storage = work_dir / "source-storage"
    target_storage = work_dir / "target-storage"
    bundle_path = work_dir / "bundle" / "OTK021 Bundle.pbbundle"
    imported_project_path = work_dir / "imported-project"

    result: dict[str, object] = {
        "ok": False,
        "work_dir": str(work_dir),
        "export_db": str(export_db),
        "import_db": str(import_db),
        "source_storage": str(source_storage),
        "target_storage": str(target_storage),
        "bundle_path": str(bundle_path),
    }

    try:
        with _session(export_db) as export_session:
            seed = _seed_export_project(export_session, source_storage)
            export_result = ProjectBundleService(
                export_session,
                storage_root=source_storage,
            ).export_project(int(seed["project_id"]), bundle_path)

        with _session(import_db) as import_session:
            import_result = ProjectBundleService(
                import_session,
                storage_root=target_storage,
            ).import_project(bundle_path, project_path=imported_project_path)

        with zipfile.ZipFile(bundle_path) as zf:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            zip_names = sorted(zf.namelist())

        imported = _inspect_import(import_db, target_storage)
        expected_hashes = seed["expected_hashes"]
        result.update(
            {
                "seed": seed,
                "export_result": {
                    "source_count": export_result.source_count,
                    "job_count": export_result.job_count,
                    "artifact_count": export_result.artifact_count,
                    "file_count": export_result.file_count,
                },
                "import_result": {
                    "project_id": import_result.project_id,
                    "source_count": import_result.source_count,
                    "job_count": import_result.job_count,
                    "artifact_count": import_result.artifact_count,
                    "file_count": import_result.file_count,
                },
                "manifest": manifest,
                "zip_names": zip_names,
                "imported": imported,
            }
        )
        result["ok"] = (
            export_result.source_count == 2
            and export_result.job_count == 2
            and export_result.artifact_count == 2
            and export_result.file_count == 2
            and import_result.source_count == 2
            and import_result.job_count == 2
            and import_result.artifact_count == 2
            and import_result.file_count == 2
            and imported["project_count"] == 1
            and imported["project_names"] == ["OTK021 Bundle Source Project"]
            and imported["project_paths"] == [str(imported_project_path)]
            and imported["job_steps"] == ["audio.v2.stems", "video.plan_a.outputs"]
            and imported["artifact_roles"] == ["edit_proxy", "vocals_stem"]
            and imported["restored_hashes"] == expected_hashes
            and manifest["project"]["resolution"] == "3840x2160"
            and float(manifest["project"]["fps"]) == 50.0
            and len(manifest["project_sources"]) == 2
            and len(manifest["analysis_jobs"]) == 2
            and len(manifest["analysis_artifacts"]) == 2
            and len(manifest["storage_files"]) == 2
            and "manifest.json" in zip_names
        )
    except Exception as exc:  # noqa: BLE001 - verifier must report diagnostic failures.
        result["error"] = f"{type(exc).__name__}: {exc}"

    result_path = ARTIFACT_DIR / "otk021_project_bundle_roundtrip_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not args.keep_workdir and result.get("ok"):
        import shutil

        shutil.rmtree(work_dir, ignore_errors=True)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
