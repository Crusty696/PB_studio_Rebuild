#!/usr/bin/env python3
"""Fail-closed Phase-minus-1 gate. Commands come from code, never manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

PLAN_ID = "PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15"
REQUIRED_GATES = {
    "feature_inventory": ("tools/audit_feature_inventory.py", "tests/audit/test_audit_feature_inventory.py", "test_exact_set_missing_extra_duplicate_rejected"),
    "symbol_contracts": ("tools/audit_symbol_contracts.py", "tests/audit/test_audit_symbol_contracts.py", "test_missing_symbol_state_or_edge_rejected"),
    "runtime_evidence": ("tools/audit_runtime_evidence.py", "tests/audit/test_audit_runtime_evidence.py", "test_missing_or_tampered_artifact_rejected"),
    "reviewer_roster": ("tools/audit_reviewer_roster.py", "tests/audit/test_audit_reviewer_roster.py", "test_same_session_or_ancestor_rejected"),
    "delta_ttl": ("tools/audit_delta_ttl.py", "tests/audit/test_audit_delta_ttl.py", "test_expired_ttl_or_product_delta_rejected"),
    "completion": ("tools/audit_completion.py", "tests/audit/test_audit_completion.py", "test_unknown_blocks_completion"),
}
COMMON_TESTS = (
    "test_positive_minimal", "test_missing_required_rejected",
    "test_tampered_binding_rejected", "test_duplicate_or_foreign_id_rejected",
)
REQUIRED_ARTIFACTS = {path for pair in REQUIRED_GATES.values() for path in pair[:2]}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True).stdout


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _basis(manifest: dict[str, Any], artifacts: list[dict[str, Any]], roster_sha: str) -> str:
    matrix = {
        name: {"tool": pair[0], "test": pair[1], "nodes": [*COMMON_TESTS, pair[2]]}
        for name, pair in sorted(REQUIRED_GATES.items())
    }
    payload = {
        "plan_id": PLAN_ID, "run_id": manifest.get("run_id"),
        "tooling_commit": manifest.get("tooling_commit"),
        "integration_head": manifest.get("integration_head"),
        "matrix_version": manifest.get("matrix_version"),
        "artifacts": sorted(artifacts, key=lambda row: row.get("path", "")),
        "reviewer_roster_sha256": roster_sha, "gate_matrix": matrix,
    }
    return _sha(_canonical(payload))


def _load_roster(path: Path, expected_sha: str, run_id: str, commit: str) -> tuple[dict[str, dict], list[str]]:
    try:
        data = path.read_bytes()
        rows = [json.loads(line) for line in data.decode().splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, [f"Reviewer-Roster unlesbar: {exc}"]
    errors = [] if _sha(data) == expected_sha else ["reviewer_roster_sha256 falsch"]
    roster: dict[str, dict] = {}
    sessions: set[str] = set()
    for number, row in enumerate(rows, 1):
        label = f"Reviewer-Roster Zeile {number}"
        if not isinstance(row, dict):
            errors.append(f"{label}: Objekt erwartet")
            continue
        reviewer, session = row.get("reviewer_id"), row.get("session_id")
        if not isinstance(reviewer, str) or not reviewer or reviewer in roster:
            errors.append(f"{label}: reviewer_id fehlt/doppelt")
            continue
        if not isinstance(session, str) or not session or session in sessions:
            errors.append(f"{label}: session_id fehlt/doppelt")
        sessions.add(str(session))
        if row.get("run_id") != run_id or row.get("commit_sha") != commit:
            errors.append(f"{label}: Run-/Commitbindung falsch")
        lineage = row.get("ancestor_session_ids")
        if not isinstance(lineage, list) or any(not isinstance(item, str) or not item for item in lineage):
            errors.append(f"{label}: ancestor_session_ids ungueltig")
        if session in (lineage or []):
            errors.append(f"{label}: eigene Session in ancestor_session_ids")
        roster[reviewer] = row
    return roster, errors


def _run_gates(root: Path, commit: str) -> list[str]:
    errors: list[str] = []
    env = {**os.environ, "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    with tempfile.TemporaryDirectory(prefix="pb-audit-readiness-") as temp:
        worktree = Path(temp) / "tree"
        try:
            subprocess.run(["git", "worktree", "add", "--detach", str(worktree), commit], cwd=root, check=True, capture_output=True, timeout=60)
            for gate, (_, test_path, specific) in sorted(REQUIRED_GATES.items()):
                for node in (*COMMON_TESTS, specific):
                    result = subprocess.run(
                        [sys.executable, "-B", test_path, f"GateContractTests.{node}"],
                        cwd=worktree, env=env, capture_output=True, text=True, timeout=120,
                    )
                    if result.returncode != 0:
                        tail = (result.stdout + result.stderr)[-800:].replace("\n", " | ")
                        errors.append(f"Gate {gate}/{node}: echter Testlauf Exit {result.returncode}: {tail}")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            errors.append(f"Detached tooling_commit-Testlauf fehlgeschlagen: {exc}")
        finally:
            if worktree.exists():
                subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=root, capture_output=True)
            subprocess.run(["git", "worktree", "prune"], cwd=root, capture_output=True)
    return errors


def verify_readiness(root: Path, manifest_path: Path) -> list[str]:
    root = root.resolve()
    try:
        manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Readiness-Manifest unlesbar: {exc}"]
    errors: list[str] = []
    if manifest.get("schema_version") != 2:
        errors.append("schema_version muss 2 sein")
    if manifest.get("plan_id") != PLAN_ID or manifest.get("matrix_version") != 1:
        errors.append("plan_id/matrix_version falsch")
    run_id, commit = manifest.get("run_id"), manifest.get("tooling_commit")
    if not isinstance(run_id, str) or not run_id.strip():
        errors.append("run_id fehlt")
    if not isinstance(commit, str) or len(commit) != 40:
        errors.append("tooling_commit muss volle 40-Zeichen-SHA sein")
        commit = ""
    try:
        head = _git(root, "rev-parse", "HEAD").decode().strip()
        resolved = _git(root, "rev-parse", f"{commit}^{{commit}}").decode().strip() if commit else ""
        if resolved != commit:
            errors.append("tooling_commit ist nicht kanonisch")
        if manifest.get("integration_head") != head or commit != head:
            errors.append("tooling_commit/integration_head muessen aktuellem HEAD entsprechen")
    except subprocess.CalledProcessError:
        errors.append("tooling_commit existiert nicht als Commit")

    rows = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    paths = [row.get("path") for row in rows if isinstance(row, dict)]
    if set(paths) != REQUIRED_ARTIFACTS or len(paths) != len(REQUIRED_ARTIFACTS):
        errors.append("Artefaktmenge entspricht nicht exakt Phase-minus-1-Vertrag")
    for row in rows:
        if not isinstance(row, dict) or row.get("path") not in REQUIRED_ARTIFACTS:
            errors.append("Artefaktzeile ungueltig/fremd")
            continue
        path = str(row["path"])
        if row.get("run_id") != run_id or row.get("tooling_commit") != commit:
            errors.append(f"{path}: run_id/tooling_commit weicht ab")
        try:
            data = _git(root, "show", f"{commit}:{path}")
        except subprocess.CalledProcessError:
            errors.append(f"{path}: fehlt im tooling_commit")
            continue
        if row.get("bytes") != len(data) or row.get("sha256") != _sha(data):
            errors.append(f"{path}: bytes/sha256 weicht vom tooling_commit ab")

    roster_path = Path(str(manifest.get("reviewer_roster_path", "")))
    roster_sha = str(manifest.get("reviewer_roster_sha256", ""))
    roster, roster_errors = _load_roster(roster_path, roster_sha, str(run_id), commit)
    errors.extend(roster_errors)
    basis = _basis(manifest, rows, roster_sha)
    signoffs = manifest.get("signoffs") if isinstance(manifest.get("signoffs"), list) else []
    if len(signoffs) != 2 or {row.get("role") for row in signoffs if isinstance(row, dict)} != {"lead-v", "adversarial"}:
        errors.append("Signoffs muessen exakt lead-v und adversarial enthalten")
    valid_rows: list[dict] = []
    for row in signoffs:
        if not isinstance(row, dict):
            errors.append("Signoff muss Objekt sein")
            continue
        reviewer = roster.get(str(row.get("reviewer_id", "")))
        if reviewer is None:
            errors.append("Signoff-Reviewer fehlt im Roster")
            continue
        if row.get("session_id") != reviewer.get("session_id") or row.get("run_id") != run_id or row.get("tooling_commit") != commit:
            errors.append("Signoff-Bindung weicht vom Roster/Run/Commit ab")
        if row.get("basis_sha256") != basis or row.get("verdict") != "pass" or not row.get("signed_at"):
            errors.append("Signoff-Basis/Verdict/Zeit ungueltig")
        valid_rows.append(reviewer)
    if len(valid_rows) == 2:
        a, b = valid_rows
        if a.get("reviewer_id") == b.get("reviewer_id") or a.get("session_id") == b.get("session_id"):
            errors.append("Signoff-Reviewer/Session muessen verschieden sein")
        if a.get("session_id") in (b.get("ancestor_session_ids") or []) or b.get("session_id") in (a.get("ancestor_session_ids") or []):
            errors.append("Signoff-Reviewer duerfen nicht Vorfahr/Nachfahre sein")
    if not errors:
        errors.extend(_run_gates(root, commit))
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
