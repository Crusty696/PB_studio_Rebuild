"""DG-001 G.* live GUI verifier for SCHNITT surface.

Creates an isolated project database with one audio clip, one video clip,
waveform, beatgrid, anchors, and notes. Then opens the real SCHNITT widgets in
Qt, loads the timeline asynchronously, and records visible widget state.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("QT_API", "pyside6")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "test-report" / "dg001-g-schnitt-gui-20260630"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _log(stage: str) -> None:
    print(f"[dg001-g] {stage}", flush=True)


def _build_project(project_dir: Path) -> int:
    _log("import database modules")
    from database import Base, engine, set_project
    from database.models import (
        AudioTrack,
        Beatgrid,
        ClipAnchor,
        Project,
        TimelineEntry,
        VideoClip,
        WaveformData,
    )

    project_dir.mkdir(parents=True, exist_ok=True)
    _log("set_project")
    set_project(project_dir)
    _log("create tables")
    Base.metadata.create_all(engine)

    _log("insert rows")
    beat_positions = [round(i * 60.0 / 128.0, 4) for i in range(68)]
    n = 96
    low = [round(0.25 + (i % 16) / 40.0, 4) for i in range(n)]
    mid = [round(0.20 + (i % 12) / 50.0, 4) for i in range(n)]
    high = [round(0.12 + (i % 10) / 70.0, 4) for i in range(n)]

    with engine.begin() as conn:
        _log("add project")
        project_result = conn.execute(
            Project.__table__.insert().values(
                name="DG001 G Schnitt GUI",
                path=str(project_dir),
                resolution="1920x1080",
                fps=30.0,
            )
        )
        project_id = int(project_result.inserted_primary_key[0])
        _log(f"project id {project_id}")

        _log("add media")
        audio_result = conn.execute(
            AudioTrack.__table__.insert().values(
                project_id=project_id,
                file_path=str(project_dir / "dg001_audio.wav"),
                title="DG001 Synthetic Audio",
                duration=32.0,
                sample_rate=44100,
                bpm=128.0,
                key="8A",
                lufs=-9.5,
                mood="energetic",
                genre="Psytrance",
            )
        )
        video_result = conn.execute(
            VideoClip.__table__.insert().values(
                project_id=project_id,
                file_path=str(project_dir / "dg001_video.mp4"),
                duration=32.0,
                width=1920,
                height=1080,
                fps=30.0,
                codec="h264",
            )
        )
        audio_id = int(audio_result.inserted_primary_key[0])
        video_id = int(video_result.inserted_primary_key[0])
        _log(f"media ids audio={audio_id} video={video_id}")

        _log("add beatgrid waveform")
        conn.execute(
            Beatgrid.__table__.insert().values(
                audio_track_id=audio_id,
                bpm=128.0,
                offset=0.0,
                beat_positions=beat_positions,
                downbeat_positions=beat_positions[::4],
                energy_per_beat=[0.4 + (i % 8) * 0.05 for i in range(len(beat_positions))],
            )
        )
        conn.execute(
            WaveformData.__table__.insert().values(
                audio_track_id=audio_id,
                num_samples=n,
                duration=32.0,
                band_low=low,
                band_mid=mid,
                band_high=high,
            )
        )

        _log("add timeline")
        audio_entry_result = conn.execute(
            TimelineEntry.__table__.insert().values(
                project_id=project_id,
                track="audio",
                media_id=audio_id,
                start_time=0.0,
                end_time=32.0,
                lane=0,
                locked=False,
            )
        )
        video_entry_result = conn.execute(
            TimelineEntry.__table__.insert().values(
                project_id=project_id,
                track="video",
                media_id=video_id,
                start_time=0.0,
                end_time=8.0,
                source_start=2.0,
                source_end=10.0,
                lane=0,
                locked=True,
            )
        )
        video_entry_id = int(video_entry_result.inserted_primary_key[0])
        _log(
            "timeline ids "
            f"audio={int(audio_entry_result.inserted_primary_key[0])} "
            f"video={video_entry_id}"
        )
        conn.execute(
            ClipAnchor.__table__.insert().values(
                timeline_entry_id=video_entry_id,
                time_offset=1.5,
                label="Drop",
                color="#ff3333",
            )
        )
        _log("rows committed")

    _log("insert notes")
    from services.project_notes_service import update_notes

    update_notes(project_id, "# DG001 G Notes\ninitial")
    _log("project db ready")
    return int(project_id)


def _wait_until(app: QApplication, predicate, timeout_s: float, label: str) -> None:
    deadline = time.monotonic() + timeout_s
    last_error = None
    while time.monotonic() < deadline:
        app.processEvents()
        try:
            if predicate():
                return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
        time.sleep(0.05)
    raise TimeoutError(f"timeout waiting for {label}: {last_error}")


def _exercise_modal_warning(app: QApplication, button) -> dict:
    observed: dict[str, object] = {"seen": False}

    def inspect_and_close() -> None:
        modal = app.activeModalWidget()
        if isinstance(modal, QMessageBox):
            observed.update(
                {
                    "seen": True,
                    "window_title": modal.windowTitle(),
                    "text": modal.text(),
                    "buttons": [b.text() for b in modal.buttons()],
                }
            )
            no_button = modal.button(QMessageBox.StandardButton.No)
            if no_button is not None:
                no_button.click()
            else:
                modal.reject()

    QTimer.singleShot(150, inspect_and_close)
    button.click()
    app.processEvents()
    if not observed["seen"]:
        inspect_and_close()
    return observed


def run(out_dir: Path, timeout_s: float) -> dict:
    from sqlalchemy.orm import Session

    from database import engine
    from database.models import ProjectNote
    from services.project_notes_service import get_notes
    from ui.controllers.schnitt_controller import SchnittController
    from ui.workspaces.schnitt_workspace import STATE_EDITOR, SchnittWorkspace

    out_dir.mkdir(parents=True, exist_ok=True)
    project_dir = out_dir / f"project_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    _log("build project db")
    project_id = _build_project(project_dir)

    _log("create QApplication")
    app = QApplication.instance() or QApplication([])
    QTimer.singleShot(int((timeout_s + 15.0) * 1000), app.quit)
    _log("create SchnittWorkspace")
    workspace = SchnittWorkspace()
    controller = SchnittController(workspace)
    regenerate_signals: list[str] = []
    controller.request_regenerate.connect(lambda _profile: regenerate_signals.append("emitted"))
    workspace.resize(1280, 820)
    workspace.show()
    app.processEvents()

    _log("set active project")
    workspace.set_active_project(project_id)
    timeline = workspace.editor_view.tab_schnitt.timeline_view
    _log("load timeline")
    timeline.load_from_db(project_id)
    _wait_until(app, lambda: len(timeline.clip_items) >= 2, timeout_s, "timeline clip build")
    _log("timeline loaded")

    locked_items = [item for item in timeline.clip_items if item.track_type == "video" and item.is_locked()]
    audio_items = [item for item in timeline.clip_items if item.track_type == "audio"]
    waveform_items = list(getattr(timeline, "waveform_items", []))

    notes_tab = workspace.editor_view.tab_rl_notes
    notes_text = f"# DG001 G Notes\nupdated {datetime.now(timezone.utc).isoformat()}"
    notes_tab.set_active_project(project_id)
    notes_tab.notes_edit.setPlainText(notes_text)
    _log("save notes")
    notes_tab._save_notes()
    with Session(engine) as session:
        note_row = session.query(ProjectNote).filter_by(project_id=project_id).one_or_none()
        note_db = note_row.content_md if note_row else ""

    tabs = workspace.editor_view.sub_tabs
    tab_labels = [tabs.tabText(i) for i in range(tabs.count())]
    tabs.setCurrentWidget(workspace.editor_view.tab_pacing_anker)
    app.processEvents()
    _log("exercise regenerate modal")
    modal = _exercise_modal_warning(app, workspace.editor_view.tab_pacing_anker.btn_regenerate)

    _log("grab screenshot")
    screenshot_path = out_dir / "schnitt_workspace.png"
    pixmap = workspace.grab()
    screenshot_saved = pixmap.save(str(screenshot_path))

    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "project_dir": str(project_dir),
        "project_id": project_id,
        "workspace_visible": workspace.isVisible(),
        "workspace_state": int(workspace.current_state()),
        "workspace_state_expected_editor": STATE_EDITOR,
        "tab_labels": tab_labels,
        "clip_count": len(timeline.clip_items),
        "audio_clip_count": len(audio_items),
        "locked_video_clip_count": len(locked_items),
        "waveform_item_count": len(waveform_items),
        "notes_saved": note_db == notes_text and get_notes(project_id) == notes_text,
        "notes_db_length": len(note_db),
        "regenerate_modal": modal,
        "regenerate_signal_after_no": len(regenerate_signals),
        "screenshot": str(screenshot_path),
        "screenshot_saved": bool(screenshot_saved),
    }
    result["passed"] = all(
        [
            result["workspace_visible"],
            result["workspace_state"] == STATE_EDITOR,
            "Schnitt" in tab_labels,
            "Pacing & Anker" in tab_labels,
            "Audio" in tab_labels,
            "RL & Notes" in tab_labels,
            result["clip_count"] >= 2,
            result["audio_clip_count"] >= 1,
            result["locked_video_clip_count"] >= 1,
            result["waveform_item_count"] >= 1,
            result["notes_saved"],
            modal.get("seen") is True,
            "überschreibt aktuelle ungelockte Schnitte" in str(modal.get("text", "")),
            result["regenerate_signal_after_no"] == 0,
            result["screenshot_saved"],
        ]
    )

    result_path = out_dir / "result.json"
    result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    _log(f"result written passed={result['passed']}")
    workspace.close()
    app.processEvents()
    return result


def main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--timeout-s", type=float, default=20.0)
    args = parser.parse_args()
    result = run(args.out_dir, args.timeout_s)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
