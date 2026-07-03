"""Verify OTK-021 cross-project reuse through import and notify paths.

This verifier uses real project folders, real SQLite DBs, the real
``ingest_audio`` import path, the by_sha manifest fallback, and the real
``ImportMediaController._notify_cross_project_reuse`` toast path. It is not a
manual GUI click test.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
import shutil
import sys
import traceback
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
WORK_ROOT = ARTIFACT_DIR / "otk021_xreuse"
RESULT_PATH = ARTIFACT_DIR / "otk021_cross_project_reuse_import_notify_result.json"


def _safe_reset_dir(path: Path) -> None:
    root = ARTIFACT_DIR.resolve()
    target = path.resolve()
    if root not in target.parents and target != root:
        raise RuntimeError(f"Refuse cleanup outside qa_artifacts: {target}")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)


class _Console:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def append(self, message: str) -> None:
        self.lines.append(str(message))


class _StatusBar:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def showMessage(self, message: str, timeout: int = 0) -> None:
        self.messages.append(str(message))


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["APPDATA"] = str(WORK_ROOT / "appdata")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _safe_reset_dir(WORK_ROOT)

    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtWidgets import QApplication, QWidget

    settings_path = WORK_ROOT / "qt-settings"
    settings_path.mkdir(parents=True, exist_ok=True)
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(settings_path))

    import database
    import database.session as db_session
    from database.models import AnalysisStatus, AudioTrack, Project
    from services.ingest_service import ingest_audio
    from services.project_manager import ProjectManager
    from services.storage_provenance.layout import StorageLayout
    from services.storage_provenance.schnitt_audio_adapter import default_global_storage_root
    from services.storage_provenance.source_identity import compute_source_sha256
    from services.storage_provenance.source_manifest import record_manifest_job
    from ui.controllers.import_media import ImportMediaController

    previous_root = Path(db_session.APP_ROOT) if db_session.APP_ROOT is not None else None

    app = QApplication.instance() or QApplication([])

    shared_audio = WORK_ROOT / "shared-track.wav"
    shared_audio.write_bytes(b"otk021-cross-project-reuse-audio")
    source_sha = compute_source_sha256(shared_audio, media_type="audio", mode="strict")

    project_a = WORK_ROOT / "project-a"
    project_b = WORK_ROOT / "project-b"
    storage_root = default_global_storage_root()
    stem_dir = StorageLayout(storage_root).ensure_source_root(source_sha) / "audio" / "stems"
    stem_dir.mkdir(parents=True, exist_ok=True)
    stems: dict[str, Path] = {}
    for name in ("vocals", "drums", "bass", "other"):
        stem_path = stem_dir / f"{name}.wav"
        stem_path.write_bytes(f"{name}-stem".encode("utf-8"))
        stems[name] = stem_path.resolve()

    result: dict[str, Any] = {
        "verifier": "verify_otk021_cross_project_reuse_import_notify",
        "project_a": str(project_a),
        "project_b": str(project_b),
        "shared_audio": str(shared_audio),
        "storage_root": str(storage_root),
        "source_sha256": source_sha,
        "checks": {},
    }

    try:
        manager = ProjectManager()
        manager.create_project(project_a, "OTK021 Reuse Projekt A")
        imported_a = ingest_audio(str(shared_audio), invalidate_caches=False)
        if imported_a is None:
            raise RuntimeError("Projekt A import returned None")
        with database.nullpool_session() as session:
            project_row = session.query(Project).one()
            project_a_id = int(project_row.id)
            project_a_name = project_row.name
            project_a_path = project_row.path

        record_manifest_job(
            storage_root,
            source_sha,
            project_id=project_a_id,
            project_name=project_a_name,
            project_path=project_a_path,
            step_id="audio.v2.stems",
            model="Demucs",
            finished_at=datetime(2026, 7, 3, 9, 0, 0),
            artifacts={f"{name}_stem": str(path) for name, path in stems.items()},
        )

        manager.create_project(project_b, "OTK021 Reuse Projekt B")
        imported_b = ingest_audio(str(shared_audio), invalidate_caches=False)
        if imported_b is None:
            raise RuntimeError("Projekt B import returned None")

        with database.nullpool_session() as session:
            project_b_row = session.query(Project).one()
            project_b_id = int(project_b_row.id)
            track_b = session.query(AudioTrack).one()
            status_b = (
                session.query(AnalysisStatus)
                .filter_by(media_type="audio", media_id=track_b.id, step_key="stem_separation")
                .one_or_none()
            )
            db_checks = {
                "project_b_id": project_b_id,
                "track_b_id": int(track_b.id),
                "track_b_file_path": track_b.file_path,
                "shared_audio_resolved": str(shared_audio.resolve()),
                "status_exists": status_b is not None,
                "status_done": status_b.status == "done" if status_b is not None else False,
                "reuse_source_project": (
                    status_b.value_summary.get("reuse_source_project")
                    if status_b is not None and isinstance(status_b.value_summary, dict)
                    else None
                ),
                "stem_paths": {
                    "vocals": track_b.stem_vocals_path,
                    "drums": track_b.stem_drums_path,
                    "bass": track_b.stem_bass_path,
                    "other": track_b.stem_other_path,
                },
            }

        window = QWidget()
        window.console_text = _Console()
        window.status_bar = _StatusBar()
        controller = ImportMediaController(window)
        settings = QSettings("PB Studio", "Rebuild")
        mute_key = f"reuse_notifications/muted_project_{project_b_id}"
        mute_value_initial = settings.value(mute_key, False, type=bool)
        settings.setValue(mute_key, False)
        settings.sync()
        with database.nullpool_session() as session:
            resolved_paths = {str(shared_audio.resolve())}
            media_rows = (
                session.query(AudioTrack)
                .filter(AudioTrack.project_id == int(project_b_id), AudioTrack.file_path.in_(resolved_paths))
                .all()
            )
            status_probe = []
            for row in media_rows:
                rows = (
                    session.query(AnalysisStatus)
                    .filter_by(media_type="audio", media_id=row.id, status="done")
                    .all()
                )
                status_probe.append(
                    {
                        "media_id": row.id,
                        "status_count": len(rows),
                        "summaries": [r.value_summary for r in rows],
                    }
                )
        toast_message = None
        notice = None
        mute_value_before_notify = settings.value(mute_key, False, type=bool)
        try:
            toast_message = controller._notify_cross_project_reuse([str(shared_audio)], "audio", project_b_id)
            app.processEvents()
            notice = getattr(controller, "_active_reuse_notice", None)
            mute_value_before_notify = settings.value(mute_key, False, type=bool)
        finally:
            settings.setValue(mute_key, mute_value_initial)
            settings.sync()
        toast_checks = {
            "toast_message": toast_message,
            "notice_created": notice is not None,
            "notice_non_modal": (
                notice.windowModality() == Qt.WindowModality.NonModal if notice is not None else False
            ),
            "notice_checkbox": (
                notice.checkBox().text() if notice is not None and notice.checkBox() is not None else None
            ),
            "console_lines": list(window.console_text.lines),
            "status_messages": list(window.status_bar.messages),
            "mute_key": mute_key,
            "mute_value_initial": mute_value_initial,
            "mute_value_before_notify": mute_value_before_notify,
            "mute_value_after_restore": settings.value(mute_key, False, type=bool),
            "notify_media_rows": len(media_rows),
            "notify_status_probe": status_probe,
        }
        if notice is not None:
            notice.close()
        window.close()

        result["checks"] = {
            "project_a_imported": imported_a.id is not None,
            "project_b_imported": imported_b.id is not None,
            **db_checks,
            **toast_checks,
            "stem_paths_exist": all(Path(path).is_file() for path in db_checks["stem_paths"].values()),
        }
        ok = (
            result["checks"]["project_a_imported"]
            and result["checks"]["project_b_imported"]
            and result["checks"]["status_done"]
            and result["checks"]["reuse_source_project"] == "OTK021 Reuse Projekt A"
            and result["checks"]["stem_paths_exist"]
            and result["checks"]["toast_message"]
            == "Datei wurde bereits in Projekt OTK021 Reuse Projekt A analysiert. Ergebnisse werden mitverwendet."
            and result["checks"]["notice_created"]
            and result["checks"]["notice_non_modal"]
            and result["checks"]["notice_checkbox"] == "Nicht mehr fragen"
        )
        result["status"] = "pass" if ok else "fail"
        return_code = 0 if ok else 1
    except Exception as exc:
        result["status"] = "error"
        result["error"] = repr(exc)
        result["traceback"] = traceback.format_exc()
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
