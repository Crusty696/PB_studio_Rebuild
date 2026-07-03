"""Verify OTK-021 migration and SCHNITT audio through product paths.

This verifier creates a real PB Studio project folder and SQLite DB with
legacy Audio-V2 stems plus Plan-A video outputs. It then reopens the project
through ``ProjectManager.open_project()``, which is the product hook that runs
the SCHNITT audio adapter. Finally it instantiates the real SCHNITT audio tab
and binder offscreen to prove the migrated stem paths still feed the UI.

This is not a manual GUI click test.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import ctypes
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
from types import SimpleNamespace
from typing import Any
import wave

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ARTIFACT_DIR = REPO_ROOT / "tests" / "qa_artifacts"
WORK_ROOT = ARTIFACT_DIR / "otk021_migration_schnitt_audio_product_path"
RESULT_PATH = ARTIFACT_DIR / "otk021_migration_schnitt_audio_product_path_result.json"
SCREENSHOT_PATH = ARTIFACT_DIR / "otk021_migration_schnitt_audio_product_path_schnitt_audio.png"


@dataclass(frozen=True)
class SeedPaths:
    project_dir: Path
    audio_source: Path
    video_source: Path
    stem_dir: Path
    stems: dict[str, Path]
    proxy: Path
    embeddings: Path
    motion: Path


def _safe_reset_dir(path: Path) -> None:
    root = ARTIFACT_DIR.resolve()
    target = path.resolve()
    if root not in target.parents and target != root:
        raise RuntimeError(f"Refuse cleanup outside qa_artifacts: {target}")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)


def _write_wav(path: Path, *, frames: int = 2048) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(44_100)
        fh.writeframes(b"\x00\x00" * frames)


def _seed_legacy_project(manager) -> SeedPaths:
    from database.models import (
        AudioTrack,
        Beatgrid,
        Project,
        StructureSegment,
        VideoClip,
        WaveformData,
    )
    import database

    project_dir = WORK_ROOT / "project"
    manager.create_project(project_dir, "OTK021 Migration SCHNITT Audio")

    media_dir = project_dir / "media"
    audio_source = media_dir / "legacy-v2-track.wav"
    video_source = media_dir / "legacy-plan-a-clip.mp4"
    _write_wav(audio_source)
    video_source.parent.mkdir(parents=True, exist_ok=True)
    video_source.write_bytes(b"otk021-plan-a-video-source")

    stem_dir = project_dir / "storage" / "stems" / "legacy-v2"
    stems = {
        "vocals": stem_dir / "vocals.wav",
        "drums": stem_dir / "drums.wav",
        "bass": stem_dir / "bass.wav",
        "other": stem_dir / "other.wav",
    }
    for stem in stems.values():
        _write_wav(stem, frames=1024)

    proxy = project_dir / "storage" / "proxies" / "legacy-proxy.mp4"
    embeddings = project_dir / "storage" / "proxies" / "legacy-embeddings.npy"
    motion = project_dir / "storage" / "proxies" / "legacy-motion.json"
    proxy.write_bytes(b"proxy")
    embeddings.write_bytes(b"embeddings")
    motion.write_text('{"motion": [0.1, 0.2, 0.3]}', encoding="utf-8")

    with database.nullpool_session() as session:
        project = session.query(Project).one()
        project.path = str(project_dir)
        audio = AudioTrack(
            project_id=project.id,
            file_path=str(audio_source),
            title="Legacy V2 Track",
            duration=12.0,
            bpm=128.0,
            key="Fm",
            lufs=-13.2,
            stem_vocals_path=str(stems["vocals"]),
            stem_drums_path=str(stems["drums"]),
            stem_bass_path=str(stems["bass"]),
            stem_other_path=str(stems["other"]),
        )
        session.add(audio)
        session.flush()
        session.add(
            Beatgrid(
                audio_track_id=audio.id,
                bpm=128.0,
                offset=0.0,
                beat_positions=[0.0, 0.47, 0.94, 1.41],
            )
        )
        session.add(
            WaveformData(
                audio_track_id=audio.id,
                num_samples=6,
                duration=12.0,
                band_low=[0.1, 0.4, 0.7, 0.4, 0.2, 0.1],
                band_mid=[0.2, 0.3, 0.4, 0.5, 0.3, 0.2],
                band_high=[0.05, 0.2, 0.25, 0.3, 0.2, 0.05],
            )
        )
        session.add(
            StructureSegment(
                audio_track_id=audio.id,
                start_time=0.0,
                end_time=4.0,
                label="INTRO",
            )
        )
        session.add(
            VideoClip(
                project_id=project.id,
                file_path=str(video_source),
                proxy_path=str(proxy),
                proxy_status="done",
                embeddings_path=str(embeddings),
                motion_path=str(motion),
                duration=4.0,
                width=1920,
                height=1080,
                fps=30.0,
            )
        )
        session.commit()

    return SeedPaths(
        project_dir=project_dir,
        audio_source=audio_source,
        video_source=video_source,
        stem_dir=stem_dir,
        stems=stems,
        proxy=proxy,
        embeddings=embeddings,
        motion=motion,
    )


def _is_reparse_or_symlink(path: Path) -> bool:
    if path.is_symlink():
        return True
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is not None:
        try:
            return bool(isjunction(path))
        except OSError:
            pass
    if os.name != "nt":
        return False
    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    if attrs == 0xFFFFFFFF:
        return False
    return bool(attrs & 0x400)


def _collect_db_checks(paths: SeedPaths, storage_root: Path) -> dict[str, Any]:
    import database
    from database.models import (
        AnalysisArtifact,
        AnalysisJob,
        AudioTrack,
        ProjectSource,
        VideoClip,
    )
    from services.storage_provenance.layout import StorageLayout
    from services.storage_provenance.source_identity import compute_source_sha256
    from services.storage_provenance.source_manifest import read_manifest_jobs

    audio_sha = compute_source_sha256(paths.audio_source, media_type="audio", mode="strict")
    video_sha = compute_source_sha256(paths.video_source, media_type="video", mode="strict")
    layout = StorageLayout(storage_root)
    audio_root = layout.source_root(audio_sha)
    video_root = layout.source_root(video_sha)
    linked_stem_dir = audio_root / "audio" / "stems"
    linked_stems = {name: linked_stem_dir / stem.name for name, stem in paths.stems.items()}

    with database.nullpool_session() as session:
        audio = session.query(AudioTrack).one()
        video = session.query(VideoClip).one()
        audio_track_id = int(audio.id)
        video_clip_id = int(video.id)
        jobs = {
            row.step_id: row.status
            for row in session.query(AnalysisJob).order_by(AnalysisJob.step_id).all()
        }
        artifact_roles = sorted(row.artifact_role for row in session.query(AnalysisArtifact).all())
        project_sources = {
            row.source_sha256: row.current_source_path
            for row in session.query(ProjectSource).all()
        }

    audio_manifest_jobs = read_manifest_jobs(storage_root, audio_sha)
    video_manifest_jobs = read_manifest_jobs(storage_root, video_sha)
    checks = {
        "audio_sha256": audio_sha,
        "video_sha256": video_sha,
        "storage_root": str(storage_root),
        "audio_by_sha_root_exists": audio_root.is_dir(),
        "video_by_sha_root_exists": video_root.is_dir(),
        "linked_stem_dir": str(linked_stem_dir),
        "linked_stem_dir_exists": linked_stem_dir.is_dir(),
        "linked_stem_dir_reparse_or_symlink": _is_reparse_or_symlink(linked_stem_dir),
        "linked_stems_exist": {name: path.is_file() for name, path in linked_stems.items()},
        "linked_stem_bytes_match": {
            name: path.read_bytes() == paths.stems[name].read_bytes()
            for name, path in linked_stems.items()
            if path.is_file()
        },
        "project_sources_count": len(project_sources),
        "project_sources_match": {
            audio_sha: project_sources.get(audio_sha) == str(paths.audio_source),
            video_sha: project_sources.get(video_sha) == str(paths.video_source),
        },
        "jobs": jobs,
        "artifact_roles": artifact_roles,
        "audio_manifest_job_count": len(audio_manifest_jobs),
        "video_manifest_job_count": len(video_manifest_jobs),
        "audio_manifest_has_stems": any(
            job.get("step_id") == "audio.v2.stems" and "artifacts" in job
            for job in audio_manifest_jobs
        ),
        "video_manifest_has_outputs": any(
            job.get("step_id") == "video.plan_a.outputs" and "artifacts" in job
            for job in video_manifest_jobs
        ),
        "audio_track_id": audio_track_id,
        "video_clip_id": video_clip_id,
        "linked_stems": {name: str(path) for name, path in linked_stems.items()},
    }
    return checks


def _verify_schnitt_audio_ui(db_checks: dict[str, Any]) -> dict[str, Any]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PySide6.QtWidgets import QApplication
    from ui.controllers.schnitt_audio_binder import SchnittAudioBinder
    from ui.workspaces.schnitt.tab_audio import SchnittTabAudio

    app = QApplication.instance() or QApplication([])
    tab = SchnittTabAudio()
    tab.resize(900, 520)
    tab.show()
    app.processEvents()

    binder = SchnittAudioBinder(tab)
    linked_stems = db_checks["linked_stems"]
    waveform = SimpleNamespace(
        band_low=[0.1, 0.4, 0.7, 0.4, 0.2, 0.1],
        band_mid=[0.2, 0.3, 0.4, 0.5, 0.3, 0.2],
        band_high=[0.05, 0.2, 0.25, 0.3, 0.2, 0.05],
        duration=12.0,
    )
    binder.set_audio_id(db_checks["audio_track_id"])
    binder.update_waveform(waveform, [0.0, 0.47, 0.94, 1.41], [{"start": 0.0, "end": 4.0, "label": "INTRO"}])
    binder.update_audio_meta(-13.2, "Fm", "4A")
    binder.set_duration(12.0)
    binder.update_stems(db_checks["audio_track_id"], linked_stems)
    app.processEvents()

    screenshot_saved = tab.grab().save(str(SCREENSHOT_PATH))
    info_label = tab.stem_workspace._info_label.text()
    scene_items = len(tab.waveform_view.scene().items())
    checks = {
        "schnitt_audio_widget_visible": tab.isVisible(),
        "lufs_label": tab.lufs_label.text(),
        "key_label": tab.key_label.text(),
        "stem_workspace_track_id": tab.stem_workspace.current_track_id,
        "stem_workspace_info": info_label,
        "stem_workspace_reports_4_stems": "4/4 Stems" in info_label,
        "waveform_scene_item_count": scene_items,
        "waveform_scene_has_items": scene_items > 0,
        "screenshot_path": str(SCREENSHOT_PATH),
        "screenshot_saved": bool(screenshot_saved and SCREENSHOT_PATH.is_file()),
    }

    tab.stem_workspace._cleanup_peak_threads()
    for thread in list(tab.stem_workspace._peak_threads):
        if thread.isRunning():
            thread.quit()
            thread.wait(1000)
    tab.close()
    app.processEvents()
    return checks


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ["APPDATA"] = str(WORK_ROOT / "appdata")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _safe_reset_dir(WORK_ROOT)

    import database
    import database.session as db_session
    from services.project_manager import ProjectManager
    from services.storage_provenance.schnitt_audio_adapter import default_global_storage_root

    previous_root = Path(db_session.APP_ROOT) if db_session.APP_ROOT is not None else None
    result: dict[str, Any] = {
        "verifier": "verify_otk021_migration_schnitt_audio_product_path",
        "work_root": str(WORK_ROOT),
        "checks": {},
        "honest_limit": "Product path verifier with real ProjectManager.open_project and real SCHNITT audio widgets; no manual installed-app GUI click.",
    }

    try:
        manager = ProjectManager()
        paths = _seed_legacy_project(manager)
        meta = manager.open_project(paths.project_dir)
        storage_root = default_global_storage_root()
        db_checks = _collect_db_checks(paths, storage_root)
        ui_checks = _verify_schnitt_audio_ui(db_checks)

        result["project_meta"] = meta
        result["seed_paths"] = {
            key: str(value) if isinstance(value, Path) else {k: str(v) for k, v in value.items()}
            for key, value in asdict(paths).items()
        }
        result["checks"] = {**db_checks, **ui_checks}
        migration_ok = (
            db_checks["audio_by_sha_root_exists"]
            and db_checks["video_by_sha_root_exists"]
            and db_checks["linked_stem_dir_exists"]
            and db_checks["linked_stem_dir_reparse_or_symlink"]
            and all(db_checks["linked_stems_exist"].values())
            and all(db_checks["linked_stem_bytes_match"].values())
            and db_checks["project_sources_count"] == 2
            and all(db_checks["project_sources_match"].values())
            and db_checks["jobs"].get("audio.v2.stems") == "done"
            and db_checks["jobs"].get("video.plan_a.outputs") == "done"
            and {"vocals_stem", "drums_stem", "bass_stem", "other_stem", "proxy", "embeddings", "motion"}.issubset(
                set(db_checks["artifact_roles"])
            )
            and db_checks["audio_manifest_has_stems"]
            and db_checks["video_manifest_has_outputs"]
        )
        schnitt_ok = (
            ui_checks["schnitt_audio_widget_visible"]
            and ui_checks["lufs_label"] == "LUFS: -13.2"
            and "Tonart: Fm" in ui_checks["key_label"]
            and "4A" in ui_checks["key_label"]
            and ui_checks["stem_workspace_track_id"] == db_checks["audio_track_id"]
            and ui_checks["stem_workspace_reports_4_stems"]
            and ui_checks["waveform_scene_has_items"]
            and ui_checks["screenshot_saved"]
        )
        result["steps"] = {
            "step_1_migration_existing_v2_plan_a_by_sha_junctions": "pass" if migration_ok else "fail",
            "step_2_schnitt_audio_subtab_product_widget": "pass" if schnitt_ok else "fail",
        }
        result["status"] = "pass" if migration_ok and schnitt_ok else "fail"
        return_code = 0 if result["status"] == "pass" else 1
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
                RESULT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(result, indent=2, sort_keys=True))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
