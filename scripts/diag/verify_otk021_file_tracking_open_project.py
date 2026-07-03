"""Verify OTK-021 file-tracking repair through ProjectManager.open_project.

This is a product-path verifier, not a GUI click test. It creates a real
project folder and SQLite DB, inserts a stale ProjectSource path, reopens the
project through ProjectManager.open_project(), and checks that the source path
is rediscovered inside the project folder by content SHA.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
from typing import Any

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ARTIFACT_DIR = REPO_ROOT / "tests" / "qa_artifacts"
WORK_ROOT = ARTIFACT_DIR / "otk021_file_tracking_open_project"
RESULT_PATH = ARTIFACT_DIR / "otk021_file_tracking_open_project_result.json"


def _safe_reset_dir(path: Path) -> None:
    root = ARTIFACT_DIR.resolve()
    target = path.resolve()
    if root not in target.parents and target != root:
        raise RuntimeError(f"Refuse cleanup outside qa_artifacts: {target}")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)


def main() -> int:
    from database.models import Project, ProjectSource
    from services.project_manager import ProjectManager
    from services.storage_provenance.source_identity import compute_source_sha256
    import database
    import database.session as db_session

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    previous_root = Path(db_session.APP_ROOT) if db_session.APP_ROOT is not None else None
    _safe_reset_dir(WORK_ROOT)

    project_dir = WORK_ROOT / "project"
    media_dir = project_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    moved_source = media_dir / "track.wav"
    missing_source = project_dir / "old" / "track.wav"
    moved_source.write_bytes(b"otk021-open-project-audio-data")
    source_sha = compute_source_sha256(moved_source, media_type="audio", mode="strict")

    manager = ProjectManager()
    result: dict[str, Any] = {
        "verifier": "verify_otk021_file_tracking_open_project",
        "project_dir": str(project_dir),
        "moved_source": str(moved_source),
        "missing_source_before": str(missing_source),
        "source_sha256": source_sha,
        "checks": {},
    }

    try:
        manager.create_project(project_dir, "OTK021 File Tracking Open")
        with database.nullpool_session() as session:
            project = session.query(Project).one()
            project.path = str(project_dir)
            session.add(
                ProjectSource(
                    project_id=project.id,
                    source_sha256=source_sha,
                    current_source_path=str(missing_source),
                )
            )
            session.commit()

        meta = manager.open_project(project_dir)
        with database.nullpool_session() as session:
            source = session.query(ProjectSource).one()
            repaired_path = Path(source.current_source_path)

        result["meta"] = meta
        result["checks"] = {
            "open_project_returned_name": meta.get("name"),
            "repaired_path": str(repaired_path),
            "repaired_path_exists": repaired_path.exists(),
            "repaired_to_moved_source": repaired_path == moved_source,
            "manager_current_project": str(manager.current_project_path),
        }
        ok = (
            result["checks"]["repaired_path_exists"]
            and result["checks"]["repaired_to_moved_source"]
            and Path(result["checks"]["manager_current_project"]) == project_dir
        )
        result["status"] = "pass" if ok else "fail"
        return_code = 0 if ok else 1
    except Exception as exc:
        result["status"] = "error"
        result["error"] = repr(exc)
        return_code = 1
    finally:
        RESULT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        if previous_root is not None and previous_root.exists():
            try:
                database.set_project(previous_root, force=True)
            except Exception as exc:  # pragma: no cover - diagnostic cleanup only
                result["restore_error"] = repr(exc)
                RESULT_PATH.write_text(
                    json.dumps(result, indent=2, sort_keys=True),
                    encoding="utf-8",
                )

    print(json.dumps(result, indent=2, sort_keys=True))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
