#!/usr/bin/env python3
"""Fail-closed Phase-minus-1 readiness validator for the exhaustive audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


PLAN_ID = "PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15"
REQUIRED_ARTIFACTS = {
    "tools/audit_feature_inventory.py",
    "tools/audit_config_contracts.py",
    "tools/audit_runtime_evidence.py",
    "tools/audit_symbol_edges.py",
    "tools/audit_duplicate_candidates.py",
    "tools/audit_completion.py",
    "tests/audit/test_audit_feature_inventory.py",
    "tests/audit/test_audit_config_contracts.py",
    "tests/audit/test_audit_runtime_evidence.py",
    "tests/audit/test_audit_symbol_edges.py",
    "tests/audit/test_audit_duplicate_candidates.py",
    "tests/audit/test_audit_completion.py",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True
    ).stdout


def _commit_blob(root: Path, commit: str, path: str) -> bytes:
    return _git(root, "show", f"{commit}:{path}")


def _outside_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return True
    return False


def verify_readiness(root: Path, manifest_path: Path) -> list[str]:
    errors: list[str] = []
    root = root.resolve()
    try:
        manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Readiness-Manifest unlesbar: {exc}"]

    if manifest.get("schema_version") != 1:
        errors.append("schema_version muss 1 sein")
    if manifest.get("plan_id") != PLAN_ID:
        errors.append("plan_id falsch")
    run_id = manifest.get("run_id")
    tooling_commit = manifest.get("tooling_commit")
    if not isinstance(run_id, str) or not run_id.strip():
        errors.append("run_id fehlt")
    if not isinstance(tooling_commit, str) or len(tooling_commit) != 40:
        errors.append("tooling_commit muss volle 40-Zeichen-SHA sein")
        tooling_commit = ""
    if tooling_commit:
        try:
            resolved = _git(root, "rev-parse", f"{tooling_commit}^{{commit}}").decode().strip()
            if resolved != tooling_commit:
                errors.append("tooling_commit ist nicht kanonisch")
        except subprocess.CalledProcessError:
            errors.append("tooling_commit existiert nicht als Commit")

    rows = manifest.get("artifacts")
    if not isinstance(rows, list):
        errors.append("artifacts muss Liste sein")
        rows = []
    paths = [row.get("path") for row in rows if isinstance(row, dict)]
    if set(paths) != REQUIRED_ARTIFACTS or len(paths) != len(REQUIRED_ARTIFACTS):
        errors.append("Artefaktmenge entspricht nicht exakt Phase-minus-1-Vertrag")
    for row in rows:
        if not isinstance(row, dict):
            errors.append("Artefaktzeile muss Objekt sein")
            continue
        path = row.get("path")
        if path not in REQUIRED_ARTIFACTS:
            continue
        if row.get("run_id") != run_id or row.get("tooling_commit") != tooling_commit:
            errors.append(f"{path}: run_id/tooling_commit weicht ab")
        try:
            data = _commit_blob(root, str(tooling_commit), str(path))
        except subprocess.CalledProcessError:
            errors.append(f"{path}: fehlt im tooling_commit")
            continue
        if row.get("bytes") != len(data) or row.get("sha256") != _sha(data):
            errors.append(f"{path}: bytes/sha256 weicht vom tooling_commit ab")

    validations = manifest.get("validation_runs")
    if not isinstance(validations, list) or not validations:
        errors.append("validation_runs fehlt/leer")
        validations = []
    covered = set()
    for row in validations:
        if not isinstance(row, dict):
            errors.append("validation_run muss Objekt sein")
            continue
        target = row.get("target")
        if target in REQUIRED_ARTIFACTS:
            covered.add(target)
        required = (
            "run_id", "tooling_commit", "target", "command", "exit_code",
            "stdout_path", "stdout_sha256", "stderr_path", "stderr_sha256",
            "started_at", "ended_at", "reviewer_id",
        )
        if any(row.get(field) in (None, "") for field in required):
            errors.append(f"validation_run {target!r}: Pflichtfeld fehlt")
            continue
        if row.get("run_id") != run_id or row.get("tooling_commit") != tooling_commit:
            errors.append(f"validation_run {target!r}: Bindung weicht ab")
        if row.get("exit_code") != 0:
            errors.append(f"validation_run {target!r}: exit_code nicht 0")
        for prefix in ("stdout", "stderr"):
            artifact = Path(str(row.get(f"{prefix}_path")))
            if not artifact.is_file():
                errors.append(f"validation_run {target!r}: {prefix}-Artefakt fehlt")
                continue
            if not _outside_root(artifact, root):
                errors.append(f"validation_run {target!r}: {prefix} muss ausserhalb Repo liegen")
            if row.get(f"{prefix}_sha256") != _sha(artifact.read_bytes()):
                errors.append(f"validation_run {target!r}: {prefix}-Hash falsch")
    if covered != REQUIRED_ARTIFACTS:
        errors.append("Nicht jedes Phase-minus-1-Artefakt besitzt gruenen Validation-Run")
    if manifest.get("independent_review_status") != "pass":
        errors.append("independent_review_status muss pass sein")
    if not manifest.get("independent_reviewer_id"):
        errors.append("independent_reviewer_id fehlt")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    errors = verify_readiness(args.root, args.manifest)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 2
    print("audit-readiness: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
