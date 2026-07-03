"""Prepare OTK-021 long live verification without starting the long run.

This script performs only short checks:
- stale prep artifact cleanup
- import/dry-run checks
- synthetic WAV/MP4 data preflight
- evidence matrix generation
- heartbeat file creation
- crash/log watcher config creation
- mini service-level product path for migration, SCHNITT adapter,
  cross-project reuse, and file tracking
- separate manifest-fallback reuse prep with non-wav SCHNITT stem names
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import wave

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ARTIFACT_DIR = ROOT / "tests" / "qa_artifacts" / "otk021_live_prep"
RESULT_JSON = ROOT / "tests" / "qa_artifacts" / "otk021_live_prep_result.json"
HEARTBEAT_JSON = ROOT / "tests" / "qa_artifacts" / "otk021_live_prep_heartbeat.json"
WATCH_CONFIG_JSON = ROOT / "tests" / "qa_artifacts" / "otk021_live_log_watch_config.json"
SYNTHESIS_MD = ROOT / "docs" / "superpowers" / "synthesis" / "otk021-live-run-prep-2026-07-03.md"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _heartbeat(phase: str, detail: str = "") -> None:
    _write_json(
        HEARTBEAT_JSON,
        {
            "phase": phase,
            "detail": detail,
            "updated_at_utc": _now(),
            "long_run_started": False,
        },
    )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _cleanup_stale() -> list[str]:
    stale = [
        RESULT_JSON,
        HEARTBEAT_JSON,
        WATCH_CONFIG_JSON,
        ROOT / "tests" / "qa_artifacts" / "otk021_live_log_watch_result.json",
    ]
    removed: list[str] = []
    for path in stale:
        if path.exists():
            path.unlink()
            removed.append(str(path))
    if ARTIFACT_DIR.exists():
        shutil.rmtree(ARTIFACT_DIR)
        removed.append(str(ARTIFACT_DIR))
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    return removed


def _dry_run_imports() -> dict[str, object]:
    modules = [
        "database.models",
        "services.storage_provenance.storage_migration",
        "services.storage_provenance.schnitt_audio_adapter",
        "services.storage_provenance.cross_project_reuse",
        "services.storage_provenance.file_tracking",
        "services.storage_provenance.storage_browser",
        "ui.dialogs.storage_browser_dialog",
    ]
    loaded: list[str] = []
    for module in modules:
        __import__(module)
        loaded.append(module)
    return {"ok": True, "modules": loaded}


def _find_ffmpeg() -> str | None:
    candidates = [
        ROOT / "bin" / "ffmpeg.exe",
        ROOT / "dist" / "pb_studio" / "_internal" / "bin" / "ffmpeg.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which("ffmpeg")


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b"\x00\x00" * 16000)


def _data_preflight(min_free_gb: float) -> dict[str, object]:
    _heartbeat("data-preflight", "create synthetic wav/mp4 and check disk")
    wav_path = ARTIFACT_DIR / "media" / "otk021_prep.wav"
    mp4_path = ARTIFACT_DIR / "media" / "otk021_prep.mp4"
    _write_wav(wav_path)

    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")
    cmd = [
        ffmpeg,
        "-y",
        "-hwaccel",
        "cuda",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=128x128:r=1:d=1",
        "-c:v",
        "h264_nvenc",
        "-pix_fmt",
        "yuv420p",
        str(mp4_path),
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg mini mp4 failed rc={proc.returncode}: {proc.stderr[-1000:]}")

    usage = shutil.disk_usage(ROOT)
    min_free_bytes = int(min_free_gb * 1024**3)
    recommended_long_run_free_bytes = 20 * 1024**3
    disk_ok = usage.free >= min_free_bytes
    return {
        "ok": wav_path.is_file() and mp4_path.is_file() and disk_ok,
        "wav": {"path": str(wav_path), "bytes": wav_path.stat().st_size, "sha256": _sha256(wav_path)},
        "mp4": {"path": str(mp4_path), "bytes": mp4_path.stat().st_size, "sha256": _sha256(mp4_path)},
        "ffmpeg": ffmpeg,
        "ffmpeg_cmd": cmd,
        "disk": {
            "free_bytes": usage.free,
            "min_free_bytes": min_free_bytes,
            "recommended_long_run_free_bytes": recommended_long_run_free_bytes,
            "ok": disk_ok,
            "warning": (
                "free disk below 20GB recommendation for long media run"
                if usage.free < recommended_long_run_free_bytes
                else None
            ),
        },
    }


def _session(db_path: Path) -> Session:
    from database.models import Base

    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return Session(engine)


def _mini_product_run(wav_path: Path) -> dict[str, object]:
    _heartbeat("mini-product-run", "service-level migration/reuse/file-tracking")
    from database.models import AnalysisJob, AnalysisStatus, AudioTrack, Project, ProjectSource
    from services.storage_provenance.cross_project_reuse import apply_cross_project_reuse_status
    from services.storage_provenance.file_tracking import repair_missing_sources
    from services.storage_provenance.schnitt_audio_adapter import ensure_schnitt_audio_adapter
    from services.storage_provenance.source_identity import compute_source_sha256

    db_path = ARTIFACT_DIR / "mini_product" / "pb_studio.db"
    storage_root = ARTIFACT_DIR / "mini_product" / "global_storage"
    project_a = ARTIFACT_DIR / "mini_product" / "project_a"
    project_b = ARTIFACT_DIR / "mini_product" / "project_b"
    stems = project_a / "storage" / "stems" / "1"
    stems.mkdir(parents=True, exist_ok=True)
    stem_paths = {}
    for name in ("vocals", "drums", "bass", "other"):
        path = stems / f"{name}.wav"
        path.write_bytes(f"{name}-stem".encode("utf-8"))
        stem_paths[name] = path

    moved_dir = ARTIFACT_DIR / "mini_product" / "moved"
    moved_dir.mkdir(parents=True, exist_ok=True)
    moved_source = moved_dir / "moved_track.wav"
    moved_source.write_bytes(b"otk021-moved-source-distinct-from-reuse-wav\n")
    moved_sha = compute_source_sha256(moved_source, media_type="audio", mode="strict")

    source_sha = compute_source_sha256(wav_path, media_type="audio", mode="strict")
    with _session(db_path) as session:
        session.add(Project(id=1, name="Prep A", path=str(project_a), resolution="1920x1080", fps=30.0))
        session.add(Project(id=2, name="Prep B", path=str(project_b), resolution="1920x1080", fps=30.0))
        session.add(Project(id=3, name="Prep Moved", path=str(moved_dir), resolution="1920x1080", fps=30.0))
        session.add(
            AudioTrack(
                id=1,
                project_id=1,
                file_path=str(wav_path),
                title="Prep Source",
                stem_vocals_path=str(stem_paths["vocals"]),
                stem_drums_path=str(stem_paths["drums"]),
                stem_bass_path=str(stem_paths["bass"]),
                stem_other_path=str(stem_paths["other"]),
            )
        )
        session.add(AudioTrack(id=2, project_id=2, file_path=str(wav_path), title="Prep Reuse"))
        session.add(
            ProjectSource(
                id=99,
                project_id=3,
                source_sha256=moved_sha,
                current_source_path=str(ARTIFACT_DIR / "mini_product" / "missing.wav"),
            )
        )
        session.commit()

        migration = ensure_schnitt_audio_adapter(session, storage_root=storage_root)
        reuse = apply_cross_project_reuse_status(
            session,
            wav_path,
            media_type="audio",
            media_id=2,
            current_project_id=2,
            storage_root=storage_root,
        )
        repair = repair_missing_sources(session, search_roots=[moved_dir], media_type="audio")
        status = (
            session.query(AnalysisStatus)
            .filter_by(media_type="audio", media_id=2, step_key="stem_separation")
            .one_or_none()
        )
        jobs = session.query(AnalysisJob).filter_by(source_sha256=source_sha).all()
        repaired_source = session.query(ProjectSource).filter_by(id=99).one()
        track_b = session.get(AudioTrack, 2)

        link_dir = storage_root / "by_sha" / source_sha[:2] / source_sha / "audio" / "stems"
        result = {
            "ok": (
                migration.audio_tracks == 1
                and reuse is not None
                and status is not None
                and status.status == "done"
                and repair.repaired == 1
                and Path(repaired_source.current_source_path) == moved_source
                and all(Path(getattr(track_b, attr)).is_file() for attr in (
                    "stem_vocals_path",
                    "stem_drums_path",
                    "stem_bass_path",
                    "stem_other_path",
                ))
            ),
            "db_path": str(db_path),
            "storage_root": str(storage_root),
            "migration": {
                "audio_tracks": migration.audio_tracks,
                "video_clips": migration.video_clips,
                "skipped_missing_sources": migration.skipped_missing_sources,
                "link_dir_exists": link_dir.exists(),
            },
            "cross_project_reuse": {
                "hit": reuse is not None,
                "toast": reuse.toast_message if reuse else None,
                "status": status.status if status else None,
                "value_summary": status.value_summary if status else None,
            },
            "file_tracking": {
                "checked": repair.checked,
                "repaired": repair.repaired,
                "missing": list(repair.missing),
                "repaired_path": str(repaired_source.current_source_path),
            },
            "jobs": sorted(job.step_id for job in jobs),
        }
    return result


def _manifest_fallback_reuse_run(wav_path: Path) -> dict[str, object]:
    _heartbeat("manifest-fallback-reuse", "separate DBs, manifest artifacts, flac stems")
    from database.models import AnalysisStatus, AudioTrack, Project
    from services.storage_provenance.cross_project_reuse import apply_cross_project_reuse_status
    from services.storage_provenance.schnitt_audio_adapter import ensure_schnitt_audio_adapter
    from services.storage_provenance.source_identity import compute_source_sha256
    from services.storage_provenance.source_manifest import manifest_path

    base = ARTIFACT_DIR / "manifest_fallback"
    storage_root = base / "global_storage"
    project_a = base / "project_a"
    project_b = base / "project_b"
    stems = project_a / "storage" / "stems" / "realistic_names"
    stems.mkdir(parents=True, exist_ok=True)
    stem_paths = {}
    for name in ("vocals", "drums", "bass", "other"):
        path = stems / f"track_{name}.flac"
        path.write_bytes(f"{name}-flac-stem".encode("utf-8"))
        stem_paths[name] = path

    source_sha = compute_source_sha256(wav_path, media_type="audio", mode="strict")
    db_a = base / "project_a.db"
    db_b = base / "project_b.db"
    with _session(db_a) as session_a:
        session_a.add(Project(id=1, name="Manifest A", path=str(project_a), resolution="1920x1080", fps=30.0))
        session_a.add(
            AudioTrack(
                id=1,
                project_id=1,
                file_path=str(wav_path),
                title="Manifest Source",
                stem_vocals_path=str(stem_paths["vocals"]),
                stem_drums_path=str(stem_paths["drums"]),
                stem_bass_path=str(stem_paths["bass"]),
                stem_other_path=str(stem_paths["other"]),
            )
        )
        session_a.commit()
        migration = ensure_schnitt_audio_adapter(session_a, storage_root=storage_root)

    with _session(db_b) as session_b:
        session_b.add(Project(id=1, name="Manifest B", path=str(project_b), resolution="1920x1080", fps=30.0))
        session_b.add(AudioTrack(id=1, project_id=1, file_path=str(wav_path), title="Manifest Reuse"))
        session_b.commit()
        hit = apply_cross_project_reuse_status(
            session_b,
            wav_path,
            media_type="audio",
            media_id=1,
            current_project_id=1,
            current_project_path=str(project_b),
            storage_root=storage_root,
        )
        status = (
            session_b.query(AnalysisStatus)
            .filter_by(media_type="audio", media_id=1, step_key="stem_separation")
            .one_or_none()
        )
        track_b = session_b.get(AudioTrack, 1)
        reused_paths = {
            "vocals": track_b.stem_vocals_path,
            "drums": track_b.stem_drums_path,
            "bass": track_b.stem_bass_path,
            "other": track_b.stem_other_path,
        }

    manifest = manifest_path(storage_root, source_sha)
    return {
        "ok": (
            migration.audio_tracks == 1
            and manifest.is_file()
            and hit is not None
            and status is not None
            and status.status == "done"
            and all(Path(path).suffix.lower() == ".flac" and Path(path).is_file() for path in reused_paths.values())
        ),
        "db_a": str(db_a),
        "db_b": str(db_b),
        "manifest": str(manifest),
        "manifest_exists": manifest.is_file(),
        "migration_audio_tracks": migration.audio_tracks,
        "hit": hit is not None,
        "status": status.status if status else None,
        "reused_paths": reused_paths,
    }


def _storage_browser_visible_check() -> dict[str, object]:
    _heartbeat("storage-browser-visible-check", "run B-547 visible verifier")
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "diag" / "verify_b547_storage_browser_delete_visible.py"),
        "--timeout-s",
        "20",
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=60,
    )
    stdout = proc.stdout.strip().lstrip("\ufeff")
    payload = json.loads(stdout) if stdout.startswith("{") else {}
    return {
        "ok": proc.returncode == 0 and bool(payload.get("ok")),
        "exit_code": proc.returncode,
        "row_count_before": payload.get("row_count_before"),
        "row_count_after": payload.get("row_count_after"),
        "source_root_exists_before": payload.get("source_root_exists_before"),
        "source_root_exists_after": payload.get("source_root_exists_after"),
        "clicked_messages": payload.get("clicked_messages"),
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def _vm_proof_check() -> dict[str, object]:
    _heartbeat("vm-proof-check", "check existing VM proof artifacts")
    probe_path = ROOT / "tests" / "qa_artifacts" / "otk021_vm_portability_probe.json"
    synthesis_path = ROOT / "docs" / "superpowers" / "synthesis" / "otk021-vm-portability-live-2026-07-02.md"
    probe = json.loads(probe_path.read_text(encoding="utf-8-sig")) if probe_path.is_file() else {}
    return {
        "ok": (
            probe_path.is_file()
            and synthesis_path.is_file()
            and probe.get("status") == "pass"
            and probe.get("project_bundle_ok") is True
            and probe.get("backup_restore_ok") is True
        ),
        "probe_path": str(probe_path),
        "synthesis_path": str(synthesis_path),
        "status": probe.get("status"),
        "project_bundle_ok": probe.get("project_bundle_ok"),
        "backup_restore_ok": probe.get("backup_restore_ok"),
    }


def _write_watch_config() -> dict[str, object]:
    _heartbeat("watch-config", "write log watcher config")
    payload = {
        "logs": [
            str(ROOT / "logs" / "pb_studio.log"),
            str(ROOT / "test-report" / "dg001-g-schnitt-gui-20260630" / "result.json"),
            str(ROOT / "tests" / "qa_artifacts" / "otk021_live_prep_heartbeat.json"),
        ],
        "patterns": [
            "Traceback",
            "ERROR",
            "CRITICAL",
            "CUDA out of memory",
            "out of memory",
            "OOM",
            "sqlite3.OperationalError",
            "Conversion failed",
            "Error while opening encoder",
            "InitializeEncoder failed",
        ],
        "created_at_utc": _now(),
        "mode": "tail-from-current-end-before-long-run",
    }
    _write_json(WATCH_CONFIG_JSON, payload)
    return payload


def _evidence_matrix(result: dict[str, object]) -> str:
    step_rows = [
        ("1", "Migration", "mini service prep run", "migration.audio_tracks == 1; by_sha stem link exists"),
        ("2", "SCHNITT audio adapter", "mini service prep run", "adapter links stems; manifest fallback separately checks non-wav stem paths"),
        ("3", "Cross-Project-Reuse", "DB + manifest prep runs", "DB reuse toast/status plus separate manifest fallback with flac paths"),
        ("4", "File-Tracking", "mini service run", "moved file repaired by SHA"),
        ("5", "Storage-Browser", "visible verifier rerun", "row 1 -> 0; source root true -> false"),
        ("6", "Project-Bundle VM", "existing VM proof checked", "otk021_vm_portability_probe.json project_bundle_ok true"),
        ("7", "Backup/Restore VM", "existing VM proof checked", "otk021_vm_portability_probe.json backup_restore_ok true"),
    ]
    lines = [
        "---",
        "status: prep-pass" if result["ok"] else "status: prep-fail",
        "task: OTK-021 live-run-prep",
        "date: 2026-07-03",
        "---",
        "",
        "# OTK-021 Live Run Prep - 2026-07-03",
        "",
        "No long run started.",
        "",
        "## Matrix",
        "",
        "| Step | Area | Prep evidence | Long-run proof target |",
        "|---|---|---|---|",
    ]
    for row in step_rows:
        lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
    lines.extend(
        [
            "",
            "## Results",
            "",
            f"- Dry-run imports: `{result['dry_run_imports']['ok']}`.",
            f"- Data preflight: `{result['data_preflight']['ok']}`.",
            f"- FFmpeg GPU command: `-hwaccel cuda`, `h264_nvenc`, `128x128`.",
            f"- Disk free bytes: `{result['data_preflight']['disk']['free_bytes']}`.",
            f"- Disk warning: `{result['data_preflight']['disk']['warning']}`.",
            f"- Mini service prep run: `{result['mini_product_run']['ok']}`.",
            f"- Manifest fallback reuse prep: `{result['manifest_fallback_reuse']['ok']}`.",
            f"- Storage-Browser visible verifier: `{result['storage_browser_visible']['ok']}`.",
            f"- VM proof check: `{result['vm_proof']['ok']}`.",
            f"- Stale prep artifacts removed: `{len(result['cleanup_removed'])}`.",
            f"- Heartbeat: `{HEARTBEAT_JSON}`.",
            f"- Watch config: `{WATCH_CONFIG_JSON}`.",
            f"- Watch patterns: `{result['watch_config']['patterns']}`.",
            "",
            "## Honest Limit",
            "",
            "Prep proves wiring and prerequisites for a long live run. It does not replace the long product-live verification and does not allow `fixed`.",
            "",
            "## Open / Not Verified",
            "",
            "- No long product-live verification started in this prep step.",
            "- Steps 1-4 still need long product-live proof with real migrated project data.",
            "- This document is `prep-pass`, not `fixed`.",
            "",
        ]
    )
    if result["data_preflight"]["disk"]["warning"]:  # type: ignore[index]
        lines.insert(-2, "- Free disk is below the 20GB recommendation for a long media run.")
    SYNTHESIS_MD.parent.mkdir(parents=True, exist_ok=True)
    SYNTHESIS_MD.write_text("\n".join(lines), encoding="utf-8")
    return str(SYNTHESIS_MD)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-free-gb", type=float, default=10.0)
    args = parser.parse_args()

    result: dict[str, object] = {
        "ok": False,
        "started_at_utc": _now(),
        "long_run_started": False,
        "cleanup_removed": [],
        "dry_run_imports": {},
        "data_preflight": {},
        "watch_config": {},
        "mini_product_run": {},
        "manifest_fallback_reuse": {},
        "storage_browser_visible": {},
        "vm_proof": {},
        "synthesis": str(SYNTHESIS_MD),
        "errors": [],
    }
    try:
        result["cleanup_removed"] = _cleanup_stale()
        _heartbeat("imports", "dry-run imports")
        result["dry_run_imports"] = _dry_run_imports()
        result["data_preflight"] = _data_preflight(args.min_free_gb)
        result["watch_config"] = _write_watch_config()
        wav_path = Path(result["data_preflight"]["wav"]["path"])  # type: ignore[index]
        result["mini_product_run"] = _mini_product_run(wav_path)
        result["manifest_fallback_reuse"] = _manifest_fallback_reuse_run(wav_path)
        result["storage_browser_visible"] = _storage_browser_visible_check()
        result["vm_proof"] = _vm_proof_check()
        result["ok"] = all(
            [
                result["dry_run_imports"].get("ok"),  # type: ignore[union-attr]
                result["data_preflight"].get("ok"),  # type: ignore[union-attr]
                result["mini_product_run"].get("ok"),  # type: ignore[union-attr]
                result["manifest_fallback_reuse"].get("ok"),  # type: ignore[union-attr]
                result["storage_browser_visible"].get("ok"),  # type: ignore[union-attr]
                result["vm_proof"].get("ok"),  # type: ignore[union-attr]
            ]
        )
        result["synthesis"] = _evidence_matrix(result)
        _heartbeat("done", "prep complete" if result["ok"] else "prep failed")
    except Exception as exc:  # noqa: BLE001 - diagnostic script must report failures.
        result["errors"].append(f"{type(exc).__name__}: {exc}")  # type: ignore[union-attr]
        _heartbeat("error", result["errors"][-1])  # type: ignore[index]
    finally:
        result["ended_at_utc"] = _now()
        _write_json(RESULT_JSON, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
