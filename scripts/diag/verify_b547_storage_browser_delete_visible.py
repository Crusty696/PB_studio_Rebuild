"""B-547 visible Storage-Browser delete verifier.

Shows the real StorageBrowserDialog against a temporary SQLite DB and
temporary by_sha storage, selects one source, enables physical-file delete,
clicks through the real QMessageBox dialogs, and verifies DB rows plus the
by_sha directory are gone.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import time

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


def _seed_database(db_path: Path, storage_root: Path, sha: str) -> dict[str, str | int]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from database.models import AnalysisArtifact, AnalysisJob, Base, Project, ProjectSource
    from services.storage_provenance.layout import StorageLayout

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)

    source_root = StorageLayout(storage_root).ensure_source_root(sha)
    artifact_path = source_root / "audio" / "artifact.bin"
    artifact_path.write_bytes(b"x" * 4096)

    with Session(engine) as session:
        project = Project(
            id=1,
            name="B547 Visible Delete Project",
            path=str(db_path.parent / "project"),
            resolution="1920x1080",
            fps=30.0,
        )
        session.add(project)
        session.add(
            ProjectSource(
                project_id=1,
                source_sha256=sha,
                current_source_path=str(db_path.parent / "source.wav"),
                last_seen_at=datetime(2026, 6, 30, 12, 0, 0),
            )
        )
        job = AnalysisJob(
            source_sha256=sha,
            step_id="audio.v2.stems",
            step_version="1",
            params_hash="b547-visible",
            status="done",
            finished_at=datetime(2026, 6, 30, 12, 0, 0),
        )
        job.artifacts.append(
            AnalysisArtifact(
                artifact_type="bin",
                artifact_role="visible-delete-artifact",
                path=str(artifact_path),
                bytes=artifact_path.stat().st_size,
            )
        )
        session.add(job)
        session.commit()
        job_id = int(job.id)

    return {
        "job_id": job_id,
        "source_root": str(source_root),
        "artifact_path": str(artifact_path),
        "artifact_bytes": artifact_path.stat().st_size,
    }


def _count_remaining(db_path: Path) -> dict[str, int]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from database.models import AnalysisArtifact, AnalysisJob, ProjectSource

    engine = create_engine(f"sqlite:///{db_path}")
    with Session(engine) as session:
        return {
            "analysis_jobs": session.query(AnalysisJob).count(),
            "analysis_artifacts": session.query(AnalysisArtifact).count(),
            "project_sources": session.query(ProjectSource).count(),
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-s", type=float, default=20.0)
    args = parser.parse_args()

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox

    from services.storage_provenance.storage_browser import StorageBrowserService
    from ui.dialogs import storage_browser_dialog as dialog_module

    app = QApplication.instance() or QApplication([])
    sha = "547" + ("a" * 61)
    work_dir = Path(tempfile.mkdtemp(prefix="pb-b547-storage-browser-", dir=str(ARTIFACT_DIR)))
    db_path = work_dir / "pb_studio.db"
    storage_root = work_dir / "storage"
    seed = _seed_database(db_path, storage_root, sha)
    engine = create_engine(f"sqlite:///{db_path}")

    @contextmanager
    def temp_session():
        session = Session(engine)
        try:
            yield session
        finally:
            session.close()

    class TempStorageBrowserService(StorageBrowserService):
        def __init__(self, session):
            super().__init__(session, storage_root=storage_root)

    old_session = dialog_module.nullpool_session
    old_service = dialog_module.StorageBrowserService
    dialog_module.nullpool_session = temp_session
    dialog_module.StorageBrowserService = TempStorageBrowserService

    clicked_messages: list[dict[str, str]] = []

    def click_message_boxes() -> None:
        for widget in QApplication.topLevelWidgets():
            if not isinstance(widget, QMessageBox) or not widget.isVisible():
                continue
            title = widget.windowTitle()
            text = widget.text()
            if title == "Analysen loeschen":
                button = widget.button(QMessageBox.StandardButton.Yes)
                button_name = "Yes"
            else:
                button = widget.button(QMessageBox.StandardButton.Ok)
                button_name = "Ok"
            if button is not None and button.isEnabled():
                clicked_messages.append({"title": title, "text": text, "button": button_name})
                button.click()

    timer = QTimer()
    timer.setInterval(100)
    timer.timeout.connect(click_message_boxes)
    timer.start()

    result: dict[str, object] = {
        "ok": False,
        "sha": sha,
        "work_dir": str(work_dir),
        "db_path": str(db_path),
        "storage_root": str(storage_root),
        "seed": seed,
        "clicked_messages": clicked_messages,
    }

    dialog = None
    try:
        dialog = dialog_module.StorageBrowserDialog()
        dialog.show()
        app.processEvents()
        started = time.monotonic()
        while dialog.table.rowCount() < 1 and time.monotonic() - started < args.timeout_s:
            app.processEvents()
            time.sleep(0.05)

        row_count_before = dialog.table.rowCount()
        summary_before = dialog._summary.text()
        source_root = Path(seed["source_root"])
        source_root_exists_before = source_root.exists()
        dialog.table.selectRow(0)
        dialog._delete_files.setChecked(True)
        dialog._delete_selected_btn.click()

        deadline = time.monotonic() + args.timeout_s
        while time.monotonic() < deadline:
            app.processEvents()
            if clicked_messages and clicked_messages[-1]["button"] == "Ok":
                break
            time.sleep(0.05)
        app.processEvents()

        remaining = _count_remaining(db_path)
        source_root_exists_after = source_root.exists()
        row_count_after = dialog.table.rowCount()
        summary_after = dialog._summary.text()
        result.update(
            {
                "row_count_before": row_count_before,
                "summary_before": summary_before,
                "source_root_exists_before": source_root_exists_before,
                "row_count_after": row_count_after,
                "summary_after": summary_after,
                "source_root_exists_after": source_root_exists_after,
                "remaining": remaining,
            }
        )
        result["ok"] = (
            row_count_before == 1
            and source_root_exists_before
            and len(clicked_messages) >= 2
            and any("Speicherordner geloescht" in msg["text"] for msg in clicked_messages)
            and not source_root_exists_after
            and remaining["analysis_jobs"] == 0
            and remaining["analysis_artifacts"] == 0
            and remaining["project_sources"] == 1
        )
    except Exception as exc:  # noqa: BLE001 - verifier reports diagnostic failures.
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        timer.stop()
        if dialog is not None:
            dialog.close()
        dialog_module.nullpool_session = old_session
        dialog_module.StorageBrowserService = old_service

    result_path = ARTIFACT_DIR / "b547_storage_browser_delete_visible_result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
