from __future__ import annotations

import argparse
import json
from pathlib import Path

from stability_manifest import (
    discover_protected_databases,
    run_evidenced_command,
    snapshot_relevant_processes,
    validate_git_source,
    write_blocked_manifest,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one stability gate with protected-DB evidence."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--baseline-commit", required=True)
    parser.add_argument("--phase", required=True)
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
        help="Required confirmation after process/file-handle inspection.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not args.confirmed_no_pb_db_writer:
        raise SystemExit(
            "BLOCKED: run requires --confirmed-no-pb-db-writer "
            "after process/file-handle inspection"
        )
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("BLOCKED: no gate command supplied after --")

    source_status = validate_git_source(args.repo_root, args.baseline_commit)
    if source_status["verdict"] != "pass":
        manifest_path = write_blocked_manifest(
            run_id=args.run_id,
            baseline_commit=args.baseline_commit,
            phase=args.phase,
            command=command,
            output_root=args.output_root,
            source_status=source_status,
            limits=source_status["limits"],
        )
        print(manifest_path)
        return 1

    try:
        process_status = snapshot_relevant_processes()
    except Exception as exc:
        process_status = {
            "capture_exit_code": 1,
            "processes": [],
            "limits": [f"{type(exc).__name__}: {exc}"],
        }
    if process_status["capture_exit_code"] != 0:
        manifest_path = write_blocked_manifest(
            run_id=args.run_id,
            baseline_commit=args.baseline_commit,
            phase=args.phase,
            command=command,
            output_root=args.output_root,
            process_status=process_status,
            source_status=source_status,
            limits=[
                *process_status.get("limits", []),
                "Pre-command process snapshot failed",
            ],
        )
        print(manifest_path)
        return 1
    process_status["verdict"] = "caller-confirmed-no-pb-db-writer"
    databases = discover_protected_databases(
        repo_root=args.repo_root,
        appdata=args.appdata,
        runtime_project_roots=args.runtime_project_root,
        include_missing=True,
    )

    def rediscover_databases():
        return discover_protected_databases(
            repo_root=args.repo_root,
            appdata=args.appdata,
            runtime_project_roots=args.runtime_project_root,
            include_missing=True,
        )

    manifest_path = run_evidenced_command(
        run_id=args.run_id,
        baseline_commit=args.baseline_commit,
        phase=args.phase,
        command=command,
        cwd=args.repo_root,
        databases=databases,
        output_root=args.output_root,
        process_status=process_status,
        database_discovery=rediscover_databases,
        source_status=source_status,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    print(manifest_path)
    if manifest["verdict"] == "pass":
        return 0
    return int(manifest["exit_code"]) or 1


if __name__ == "__main__":
    raise SystemExit(main())
