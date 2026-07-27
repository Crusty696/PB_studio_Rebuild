from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
from typing import Any, Callable, Iterable


SIDECAR_SUFFIXES = ("", "-wal", "-shm")
PROJECT_DATABASE_PATHS = (
    Path("pb_studio.db"),
    Path("data/vector/embeddings.db"),
    Path("brain_v3/embeddings.db"),
    Path("brain_v3/state.db"),
)
APP_BRAIN_DATABASES = (
    "weights.db",
    "patterns.db",
    "embedding_cache.db",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _resolved_casefold(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _recent_project_roots(settings_path: Path) -> list[Path]:
    if not settings_path.is_file():
        return []
    payload = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    entries = payload.get("recentProjects", [])
    roots: list[Path] = []
    for entry in entries:
        raw_path = entry.get("path") if isinstance(entry, dict) else entry
        if isinstance(raw_path, str) and raw_path.strip():
            roots.append(Path(raw_path))
    return roots


def _project_databases(
    project_root: Path,
    *,
    include_missing: bool = False,
) -> Iterable[Path]:
    for relative_path in PROJECT_DATABASE_PATHS:
        candidate = project_root / relative_path
        if include_missing or candidate.is_file():
            yield candidate


def discover_protected_databases(
    *,
    repo_root: Path,
    appdata: Path,
    settings_path: Path | None = None,
    runtime_project_roots: Iterable[Path] = (),
    include_missing: bool = False,
) -> list[Path]:
    """Return protected DB paths without importing product modules or opening SQLite."""
    repo_root = repo_root.resolve()
    settings_path = settings_path or appdata / "PBStudio" / "settings.json"
    candidates: list[Path] = list(
        _project_databases(repo_root, include_missing=include_missing)
    )
    outputs = repo_root / "outputs"
    if outputs.is_dir():
        candidates.extend(path for path in outputs.rglob("*.db") if path.is_file())
    project_roots = [*_recent_project_roots(settings_path), *runtime_project_roots]
    for project_root in project_roots:
        candidates.extend(
            _project_databases(
                Path(project_root),
                include_missing=include_missing,
            )
        )
    app_brain_root = appdata / "PB_Studio" / "brain_v3"
    candidates.extend(app_brain_root / name for name in APP_BRAIN_DATABASES)

    excluded_parts = {".worktrees", ".claude", "backups", "storage"}
    unique: dict[str, Path] = {}
    for candidate in candidates:
        resolved = candidate.resolve()
        if not include_missing and not resolved.is_file():
            continue
        try:
            relative_parts = {part.casefold() for part in resolved.relative_to(repo_root).parts}
        except ValueError:
            relative_parts = set()
        if relative_parts & excluded_parts:
            continue
        unique[_resolved_casefold(resolved)] = resolved
    return sorted(unique.values(), key=_resolved_casefold)


def _component_snapshot(database: Path) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for suffix in SIDECAR_SUFFIXES:
        component = Path(f"{database}{suffix}")
        key = "database" if not suffix else suffix.removeprefix("-")
        if component.is_file():
            stat = component.stat()
            snapshot[key] = {
                "path": str(component.resolve()),
                "exists": True,
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha256": _sha256(component),
            }
        else:
            snapshot[key] = {
                "path": str(component.resolve()),
                "exists": False,
                "size": 0,
                "mtime_ns": None,
                "sha256": None,
            }
    return snapshot


def _snapshots_equal(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
) -> bool:
    fields = ("exists", "size", "mtime_ns", "sha256")
    return all(
        before[name][field] == after[name][field]
        for name in before
        for field in fields
    )


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _canonical_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {
            "type": "blob",
            "size": len(value),
            "sha256": hashlib.sha256(value).hexdigest(),
        }
    if isinstance(value, float):
        return {"type": "float", "value": value.hex()}
    if value is None:
        return {"type": "null"}
    return {"type": type(value).__name__, "value": value}


def _analyze_consolidated_database(database: Path) -> dict[str, Any]:
    connection = sqlite3.connect(database)
    try:
        quick_rows = connection.execute("PRAGMA quick_check").fetchall()
        quick_check = "; ".join(str(row[0]) for row in quick_rows)
        schema_rows = connection.execute(
            "SELECT name, type, COALESCE(sql, '') FROM sqlite_schema "
            "ORDER BY type, name"
        ).fetchall()
        schema_json = json.dumps(schema_rows, ensure_ascii=False, separators=(",", ":"))
        schema_sha256 = hashlib.sha256(schema_json.encode("utf-8")).hexdigest()
        table_names = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        table_counts: dict[str, int] = {}
        logical_digest = hashlib.sha256()
        for table_name in table_names:
            quoted_table = _quote_identifier(table_name)
            columns = [
                row[1]
                for row in connection.execute(f"PRAGMA table_info({quoted_table})")
            ]
            row_hashes: list[str] = []
            for row in connection.execute(f"SELECT * FROM {quoted_table}"):
                canonical_row = [
                    [column, _canonical_value(value)]
                    for column, value in zip(columns, row)
                ]
                encoded = json.dumps(
                    canonical_row,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
                row_hashes.append(hashlib.sha256(encoded).hexdigest())
            row_hashes.sort()
            table_counts[table_name] = len(row_hashes)
            logical_digest.update(table_name.encode("utf-8"))
            logical_digest.update(b"\0")
            for row_hash in row_hashes:
                logical_digest.update(row_hash.encode("ascii"))
                logical_digest.update(b"\n")
        alembic_version = None
        if "alembic_version" in table_names:
            versions = connection.execute(
                "SELECT version_num FROM alembic_version ORDER BY version_num"
            ).fetchall()
            alembic_version = [row[0] for row in versions]
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]
        return {
            "quick_check": quick_check,
            "schema_sha256": schema_sha256,
            "alembic_version": alembic_version,
            "user_version": user_version,
            "table_counts": table_counts,
            "logical_content_sha256": logical_digest.hexdigest(),
        }
    finally:
        connection.close()


def _copy_raw_bundle(
    database: Path,
    *,
    backup_root: Path,
    source_snapshot: dict[str, dict[str, Any]],
) -> dict[str, str | None]:
    source_key = hashlib.sha256(
        _resolved_casefold(database).encode("utf-8")
    ).hexdigest()[:16]
    destination = backup_root / source_key
    destination.mkdir(parents=True, exist_ok=False)
    copied: dict[str, str | None] = {}
    for suffix in SIDECAR_SUFFIXES:
        name = "database" if not suffix else suffix.removeprefix("-")
        component = Path(f"{database}{suffix}")
        if not source_snapshot[name]["exists"]:
            copied[name] = None
            continue
        target = destination / f"{database.name}{suffix}"
        shutil.copy2(component, target)
        if _sha256(target) != source_snapshot[name]["sha256"]:
            raise RuntimeError(f"Backup hash mismatch: {component}")
        copied[name] = str(target.resolve())
    return copied


def _consolidate_raw_bundle(raw_database: Path) -> Path:
    consolidated = raw_database.parent / "consolidated.db"
    source = sqlite3.connect(raw_database)
    target = sqlite3.connect(consolidated)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return consolidated


def capture_database(database: Path, *, backup_root: Path) -> dict[str, Any]:
    """Copy DB/WAL/SHM first, verify source stability, analyze copied data only."""
    database = database.resolve()
    source_before = _component_snapshot(database)
    backup = _copy_raw_bundle(
        database,
        backup_root=backup_root,
        source_snapshot=source_before,
    )
    source_after = _component_snapshot(database)
    stable = _snapshots_equal(source_before, source_after)
    analysis = None
    if stable and backup["database"] is not None:
        consolidated = _consolidate_raw_bundle(Path(str(backup["database"])))
        backup["consolidated_database"] = str(consolidated.resolve())
        analysis = _analyze_consolidated_database(consolidated)
    else:
        backup["consolidated_database"] = None
    return {
        "source": str(database),
        "stable": stable,
        "source_before": source_before,
        "source_after": source_after,
        "backup": backup,
        "analysis": analysis,
    }


def snapshot_relevant_processes() -> dict[str, Any]:
    script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object {$_.Name -match "
        "'^(python|pythonw|pb_studio|ffmpeg|ffprobe|ollama)'} | "
        "Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,CommandLine,CreationDate | "
        "ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    processes: list[dict[str, Any]] = []
    if result.returncode == 0 and result.stdout.strip():
        payload = json.loads(result.stdout)
        processes = payload if isinstance(payload, list) else [payload]
    return {
        "capture_exit_code": result.returncode,
        "processes": processes,
        "limits": [] if result.returncode == 0 else [result.stderr.strip()],
    }


def validate_git_source(repo_root: Path, baseline_commit: str) -> dict[str, Any]:
    """Bind evidence to the exact clean Git tree that will execute the gate."""
    try:
        actual_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.STDOUT,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        return {
            "verdict": "blocked",
            "expected_commit": baseline_commit,
            "actual_commit": None,
            "dirty_paths": [],
            "limits": [f"Git source inspection failed: {type(exc).__name__}: {exc}"],
        }
    dirty_paths = [
        line[3:] if len(line) > 3 else line
        for line in status.splitlines()
        if line.strip()
    ]
    limits: list[str] = []
    if actual_commit != baseline_commit:
        limits.append("Baseline commit does not match current HEAD")
    if dirty_paths:
        limits.append("Git worktree is not clean")
    return {
        "verdict": "pass" if not limits else "blocked",
        "expected_commit": baseline_commit,
        "actual_commit": actual_commit,
        "dirty_paths": dirty_paths,
        "limits": limits,
    }


def write_blocked_manifest(
    *,
    run_id: str,
    baseline_commit: str,
    phase: str,
    command: list[str],
    output_root: Path,
    limits: Iterable[str],
    source_status: dict[str, Any] | None = None,
    process_status: dict[str, Any] | None = None,
) -> Path:
    """Persist a pre-command blocker without executing the gate command."""
    started_at = _utc_now()
    output_root.mkdir(parents=True, exist_ok=False)
    stdout_path = output_root / "stdout.log"
    stderr_path = output_root / "stderr.log"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    manifest = {
        "run_id": run_id,
        "baseline_commit": baseline_commit,
        "phase": phase,
        "command": subprocess.list2cmdline(command),
        "started_at": started_at,
        "ended_at": _utc_now(),
        "exit_code": 1,
        "verdict": "blocked",
        "source_status": source_status,
        "process_status": process_status,
        "db_before": {},
        "db_after": {},
        "database_analysis_before": {},
        "database_analysis_after": {},
        "artifacts": [],
        "logs": [str(stdout_path.resolve()), str(stderr_path.resolve())],
        "limits": list(limits),
    }
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _absent_snapshot(database: Path) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for suffix in SIDECAR_SUFFIXES:
        component = Path(f"{database}{suffix}")
        key = "database" if not suffix else suffix.removeprefix("-")
        snapshot[key] = {
            "path": str(component.resolve()),
            "exists": False,
            "size": 0,
            "mtime_ns": None,
            "sha256": None,
        }
    return snapshot


def _descendant_processes(
    command_pid: int | None,
    process_status: dict[str, Any],
) -> list[dict[str, Any]]:
    if command_pid is None:
        return []
    processes = process_status.get("processes", [])
    descendants: list[dict[str, Any]] = []
    parent_ids = {command_pid}
    while parent_ids:
        generation = [
            process
            for process in processes
            if process.get("ParentProcessId") in parent_ids
            and process not in descendants
        ]
        descendants.extend(generation)
        parent_ids = {
            int(process["ProcessId"])
            for process in generation
            if process.get("ProcessId") is not None
        }
    return descendants


def write_baseline_manifest(
    *,
    run_id: str,
    baseline_commit: str,
    repo_root: Path,
    appdata: Path,
    output_root: Path,
    command: str,
    process_status: dict[str, Any],
    runtime_project_roots: Iterable[Path] = (),
) -> Path:
    started_at = _utc_now()
    output_root.mkdir(parents=True, exist_ok=False)
    backup_root = output_root / "backups"
    backup_root.mkdir()
    databases = discover_protected_databases(
        repo_root=repo_root,
        appdata=appdata,
        runtime_project_roots=runtime_project_roots,
    )
    captures: list[dict[str, Any]] = []
    errors: list[str] = []
    for database in databases:
        try:
            captures.append(capture_database(database, backup_root=backup_root))
        except Exception as exc:
            errors.append(f"{database}: {type(exc).__name__}: {exc}")
    stable = not errors and all(item["stable"] for item in captures)
    db_before = {item["source"]: item["source_before"] for item in captures}
    db_after = {item["source"]: item["source_after"] for item in captures}
    artifacts = [
        path
        for item in captures
        for path in item["backup"].values()
        if path is not None
    ]
    limits = [
        "Original SQLite databases were never opened; logical analysis used raw copies.",
        "Runtime-only project roots are included only when explicitly supplied.",
    ]
    limits.extend(process_status.get("limits", []))
    limits.extend(errors)
    manifest = {
        "run_id": run_id,
        "baseline_commit": baseline_commit,
        "phase": "STAB-1",
        "command": command,
        "started_at": started_at,
        "ended_at": _utc_now(),
        "exit_code": 0 if stable else 1,
        "verdict": "pass" if stable else "blocked",
        "process_status": process_status,
        "db_before": db_before,
        "db_after": db_after,
        "database_analysis": {
            item["source"]: item["analysis"] for item in captures
        },
        "artifacts": artifacts,
        "logs": [],
        "limits": limits,
    }
    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def run_evidenced_command(
    *,
    run_id: str,
    baseline_commit: str,
    phase: str,
    command: list[str],
    cwd: Path,
    databases: Iterable[Path],
    output_root: Path,
    process_status: dict[str, Any],
    env: dict[str, str] | None = None,
    database_discovery: Callable[[], Iterable[Path]] | None = None,
    process_snapshotter: Callable[[], dict[str, Any]] | None = None,
    source_status: dict[str, Any] | None = None,
) -> Path:
    """Run one gate while proving protected DB bytes and contents unchanged."""
    started_at = _utc_now()
    output_root.mkdir(parents=True, exist_ok=False)
    manifest_path = output_root / "manifest.json"
    stdout_path = output_root / "stdout.log"
    stderr_path = output_root / "stderr.log"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    skeleton = {
        "run_id": run_id,
        "baseline_commit": baseline_commit,
        "phase": phase,
        "command": subprocess.list2cmdline(command),
        "started_at": started_at,
        "ended_at": None,
        "exit_code": 1,
        "verdict": "blocked",
        "source_status": source_status,
        "process_status": {"before": process_status, "after": None},
        "db_before": {},
        "db_after": {},
        "database_analysis_before": {},
        "database_analysis_after": {},
        "artifacts": [],
        "logs": [str(stdout_path.resolve()), str(stderr_path.resolve())],
        "limits": ["Run incomplete; final evidence was not written"],
    }
    manifest_path.write_text(
        json.dumps(skeleton, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    before_root = output_root / "backups_before"
    after_root = output_root / "backups_after"
    before_root.mkdir()
    initial_paths = {
        _resolved_casefold(Path(database)): Path(database).resolve()
        for database in databases
    }
    errors: list[str] = []
    before_by_source: dict[str, dict[str, Any]] = {}
    for database in initial_paths.values():
        try:
            capture = capture_database(database, backup_root=before_root)
            before_by_source[capture["source"]] = capture
        except Exception as exc:
            errors.append(
                f"before capture {database}: {type(exc).__name__}: {exc}"
            )

    command_pid: int | None = None
    command_exit_code = 1
    command_stdout = ""
    command_stderr = ""
    process_before_ok = process_status.get("capture_exit_code", 0) == 0
    command_started = not errors and process_before_ok
    if command_started:
        try:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            command_pid = process.pid
            command_stdout, command_stderr = process.communicate()
            command_exit_code = int(process.returncode)
        except Exception as exc:
            errors.append(f"command start/run: {type(exc).__name__}: {exc}")
            command_stderr = f"{type(exc).__name__}: {exc}"
    else:
        errors.append("Command blocked by failed preflight evidence")
    stdout_path.write_text(command_stdout, encoding="utf-8")
    stderr_path.write_text(command_stderr, encoding="utf-8")

    snapshotter = process_snapshotter or snapshot_relevant_processes
    if command_started:
        try:
            process_after = snapshotter()
        except Exception as exc:
            errors.append(
                f"post process snapshot: {type(exc).__name__}: {exc}"
            )
            process_after = {
                "capture_exit_code": 1,
                "processes": [],
                "limits": [f"{type(exc).__name__}: {exc}"],
            }
    else:
        process_after = {
            "capture_exit_code": 0,
            "processes": [],
            "limits": [],
        }
    surviving_descendants = _descendant_processes(command_pid, process_after)

    final_paths = dict(initial_paths)
    if database_discovery is not None:
        try:
            for database in database_discovery():
                resolved = Path(database).resolve()
                final_paths[_resolved_casefold(resolved)] = resolved
        except Exception as exc:
            errors.append(
                f"after database discovery: {type(exc).__name__}: {exc}"
            )
    after_root.mkdir()
    after_by_source: dict[str, dict[str, Any]] = {}
    for database in final_paths.values():
        try:
            capture = capture_database(database, backup_root=after_root)
            after_by_source[capture["source"]] = capture
        except Exception as exc:
            errors.append(f"after capture {database}: {type(exc).__name__}: {exc}")

    for database in final_paths.values():
        source = str(database.resolve())
        if source not in before_by_source:
            absent = _absent_snapshot(database)
            before_by_source[source] = {
                "source": source,
                "stable": True,
                "source_before": absent,
                "source_after": absent,
                "backup": {},
                "analysis": None,
            }

    before_captures = list(before_by_source.values())
    after_captures = list(after_by_source.values())
    db_before = {
        item["source"]: item["source_after"] for item in before_captures
    }
    db_after = {
        item["source"]: item["source_before"] for item in after_captures
    }
    analysis_before = {
        item["source"]: item["analysis"] for item in before_captures
    }
    analysis_after = {
        item["source"]: item["analysis"] for item in after_captures
    }
    captures_stable = all(
        item["stable"] for item in [*before_captures, *after_captures]
    )
    bytes_unchanged = db_before == db_after
    logical_unchanged = analysis_before == analysis_after
    limits = [
        "Original SQLite databases were never opened; logical analysis used raw copies."
    ]
    limits.extend(process_status.get("limits", []))
    limits.extend(process_after.get("limits", []))
    limits.extend(errors)
    if not process_before_ok:
        limits.append("Pre-command process snapshot failed")
    if process_after.get("capture_exit_code", 0) != 0:
        limits.append("Post-command process snapshot failed")
    if surviving_descendants:
        limits.append("Command left relevant descendant processes running")
    if set(final_paths) != set(initial_paths):
        limits.append("Protected database set changed")
    if not captures_stable:
        limits.append("Protected database changed during evidence capture")
    if not bytes_unchanged:
        limits.append("Protected database bytes changed")
    if not logical_unchanged:
        limits.append("Protected database logical content changed")
    passed = (
        command_exit_code == 0
        and command_started
        and not errors
        and process_before_ok
        and process_after.get("capture_exit_code", 0) == 0
        and not surviving_descendants
        and captures_stable
        and bytes_unchanged
        and logical_unchanged
    )
    artifacts = [
        path
        for item in [*before_captures, *after_captures]
        for path in item["backup"].values()
        if path is not None
    ]
    manifest = {
        "run_id": run_id,
        "baseline_commit": baseline_commit,
        "phase": phase,
        "command": subprocess.list2cmdline(command),
        "started_at": started_at,
        "ended_at": _utc_now(),
        "exit_code": command_exit_code,
        "verdict": "pass" if passed else "fail",
        "source_status": source_status,
        "process_status": {
            "before": process_status,
            "after": process_after,
            "command_pid": command_pid,
            "surviving_descendants": surviving_descendants,
        },
        "db_before": db_before,
        "db_after": db_after,
        "database_analysis_before": analysis_before,
        "database_analysis_after": analysis_after,
        "artifacts": artifacts,
        "logs": [str(stdout_path.resolve()), str(stderr_path.resolve())],
        "limits": limits,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture a zero-touch PB Studio stability DB baseline."
    )
    parser.add_argument("capture", choices=["capture"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--baseline-commit", required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--appdata", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--runtime-project-root",
        action="append",
        type=Path,
        default=[],
    )
    parser.add_argument(
        "--confirmed-no-pb-db-writer",
        action="store_true",
        help="Required confirmation that no process has a protected PB DB open.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.confirmed_no_pb_db_writer:
        raise SystemExit(
            "BLOCKED: capture requires --confirmed-no-pb-db-writer "
            "after process/file-handle inspection"
        )
    process_status = snapshot_relevant_processes()
    process_status["verdict"] = "caller-confirmed-no-pb-db-writer"
    command = subprocess.list2cmdline(os.sys.argv)
    manifest_path = write_baseline_manifest(
        run_id=args.run_id,
        baseline_commit=args.baseline_commit,
        repo_root=args.repo_root,
        appdata=args.appdata,
        output_root=args.output_root,
        command=command,
        process_status=process_status,
        runtime_project_roots=args.runtime_project_root,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    print(manifest_path)
    return int(manifest["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
