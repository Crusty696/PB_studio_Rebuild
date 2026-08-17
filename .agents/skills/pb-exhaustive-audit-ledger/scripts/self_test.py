from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch

import verify_line_coverage as coverage_module
from build_inventory import _snapshot_basis, build
from verify_audit_readiness import (
    AUTHORITY_BOUND_PATHS,
    AUTHORITY_POLICY_PATH,
    READINESS_VALIDATOR_PATH,
    REQUIRED_ARTIFACTS,
    REQUIRED_GATES,
    REVIEWER_RUNTIME_PATHS,
    _basis,
    _gate_matrix,
    _load_authority_policy,
    _materialize_bound_files,
    _run_materialized_reviewer,
    _run_test_node,
    _verify_attestation_bundle,
    verify_readiness,
)
from verify_feature_matrix import AXES, verify as verify_features, verify_snapshot
from verify_line_coverage import _enumerate_scope, _linklike, verify as _verify_coverage

RUN_ID = "SELFTEST-RUN"


def verify_coverage(*args: Path) -> list[str]:
    snapshot_path = Path(args[1])
    roster_path = snapshot_path.parent / "reviewer_roster.jsonl"
    return [
        error for error in _verify_coverage(*args, roster_path)
        if not error.startswith("Reviewer-Live-Enrollment-Harness fehlt")
    ]


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _git_bytes(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True,
    ).stdout


def _commit_authority_policy(
    root: Path, base: Path, tooling_commit: str, policy: dict, branch: str,
) -> str:
    worktree = base / branch
    _git(root, "worktree", "add", "--detach", str(worktree), tooling_commit)
    try:
        target = worktree / AUTHORITY_POLICY_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(json.dumps(
            policy, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8"))
        _git(worktree, "add", "--", AUTHORITY_POLICY_PATH)
        _git(worktree, "commit", "-m", branch)
        return _git_bytes(worktree, "rev-parse", "HEAD").decode().strip()
    finally:
        _git(root, "worktree", "remove", "--force", str(worktree))


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _bind_reviewer_roster(evidence_dir: Path, root: Path) -> Path:
    snapshot_path = evidence_dir / "snapshot.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    inventory = [
        json.loads(line)
        for line in (evidence_dir / "files.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    snapshot_id = inventory[0]["snapshot_id"]
    audited_commit = snapshot["commit_sha"]
    rows = []
    for label in ("a", "b"):
        rows.append({
            "run_id": RUN_ID,
            "audited_commit": audited_commit,
            "snapshot_id": snapshot_id,
            "reviewer_id": f"reviewer-{label}",
            "session_id": f"session-{label}",
            "parent_session_id": f"director-{label}",
            "ancestor_session_ids": [f"root-{label}", f"director-{label}"],
            "worktree": str((root.parent / f"reviewer-{label}").resolve()),
            "branch": f"audit/{label}",
            "commit_sha": audited_commit,
            "claims": ["*"],
            "review_scope": ["*"],
        })
    roster = evidence_dir / "reviewer_roster.jsonl"
    _write_jsonl(roster, rows)
    snapshot["audited_commit"] = audited_commit
    snapshot["reviewer_roster_sha256"] = hashlib.sha256(roster.read_bytes()).hexdigest()
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    return roster


def _range(meta: dict, label: str, reviewer: str, start: int, end: int) -> dict:
    return {
        "run_id": RUN_ID, "snapshot_id": meta["snapshot_id"], "pass": label,
        "reviewer_id": reviewer, "path": meta["path"],
        "file_sha256": meta["sha256"], "start_line": start, "end_line": end,
        "checks": {key: "done" for key in ("semantics", "errors", "state", "threading", "io_db_gpu", "wiring")},
        "finding_ids": [], "verdict": "reviewed",
        "signed_at": "2026-08-15T00:00:00Z",
    }


def _unit(meta: dict, kind: str, label: str, reviewer: str) -> dict:
    return {
        "run_id": RUN_ID, "snapshot_id": meta["snapshot_id"], "pass": label,
        "reviewer_id": reviewer, "path": meta["path"], "unit_kind": kind,
        "file_sha256": meta["sha256"],
        "checks": {key: "done" for key in ("identity", "format", "provenance", "consumer", "integrity")},
        "verdict": "reviewed", "signed_at": "2026-08-15T00:00:00Z",
    }


def _ranges_for(meta: dict, label: str, reviewer: str) -> list[dict]:
    lines = int(meta.get("line_count") or 0)
    if meta.get("media") != "text" or not lines:
        return []
    if lines <= 200:
        return [_range(meta, label, reviewer, 1, lines)]
    rows = []
    start = 1
    while lines - start + 1 > 200:
        rows.append(_range(meta, label, reviewer, start, start + 149))
        start += 150
    rows.append(_range(meta, label, reviewer, start, lines))
    return rows


def _feature(head: str, snapshot_id: str, path_id: str) -> dict:
    evidence = {
        axis: {
            "value": "UNKNOWN",
            "evidence": [{
                "kind": "not-checked", "ref": f"SELF-{axis}",
                "reason": "self-test intentionally not executed",
                "commit_sha": head, "run_id": RUN_ID,
                "timestamp": "2026-08-15T00:00:00Z",
            }],
        }
        for axis in AXES
    }
    return {
        "run_id": RUN_ID, "feature_id": "FEAT-001", "path_id": path_id,
        "name": "Fixture Feature", "user_surface": "self-test",
        "trigger": "fixture", "handler": "sample.py:1", "service": "N-A",
        "worker": "N-A", "state_store": "N-A", "config_keys": [],
        "expected_result": "fixture result", "evidence_age": "current-head",
        "verdict": "not-checked", "blockers": [], "not_checked": list(AXES),
        "snapshot_id": snapshot_id, "commit_sha": head,
        "reviewer_id": "reviewer-a", "signed_at": "2026-08-15T00:00:00Z",
        "states": evidence, "overall_state": "not-checked",
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="pb-audit-ledger-") as temp:
        base = Path(temp)
        root = base / "repo"
        root.mkdir()
        _git(root, "init")
        _git(root, "config", "user.name", "Ledger Self Test")
        _git(root, "config", "user.email", "ledger@example.invalid")
        (root / "sample.py").write_text("".join(f"x_{n} = {n}\n" for n in range(250)), encoding="utf-8")
        (root / "small.py").write_text("".join(f"y_{n} = {n}\n" for n in range(150)), encoding="utf-8")
        (root / "empty.txt").write_bytes(b"")
        (root / "asset.bin").write_bytes(b"\x00\x01")
        _git(root, "add", "sample.py", "small.py", "empty.txt", "asset.bin")
        _git(root, "commit", "-m", "fixture")

        evidence_dir = base / "evidence"
        summary = build(root, evidence_dir, run_id=RUN_ID)
        _bind_reviewer_roster(evidence_dir, root)
        files = [json.loads(line) for line in (evidence_dir / "files.jsonl").read_text(encoding="utf-8").splitlines()]
        by_path = {row["path"]: row for row in files}
        pass_a = evidence_dir / "a.jsonl"
        pass_b = evidence_dir / "b.jsonl"
        _write_jsonl(pass_a, [
            _range(by_path["sample.py"], "A", "reviewer-a", 1, 150),
            _range(by_path["sample.py"], "A", "reviewer-a", 151, 250),
            _range(by_path["small.py"], "A", "reviewer-a", 1, 150),
        ])
        _write_jsonl(pass_b, [
            _range(by_path["sample.py"], "B", "reviewer-b", 1, 150),
            _range(by_path["sample.py"], "B", "reviewer-b", 151, 250),
            _range(by_path["small.py"], "B", "reviewer-b", 1, 150),
        ])
        units = []
        for meta in files:
            kinds = ["metadata"]
            if meta["media"] == "binary":
                kinds.append("binary-content")
            if meta["media"] == "text" and not meta["line_count"]:
                kinds.append("empty-file")
            for kind in kinds:
                units.extend([
                    _unit(meta, kind, "A", "reviewer-a"),
                    _unit(meta, kind, "B", "reviewer-b"),
                ])
        non_line = evidence_dir / "non_line.jsonl"
        exclusions = evidence_dir / "exclusions.jsonl"
        workspace_units = evidence_dir / "workspace_units.jsonl"
        _write_jsonl(non_line, units)
        _write_jsonl(exclusions, [])
        assert not verify_coverage(
            root, evidence_dir / "snapshot.json", evidence_dir / "files.jsonl",
            pass_a, pass_b, non_line, exclusions, workspace_units,
        )
        missing_inventory = [row for row in files if row["path"] != "small.py"]
        missing_path = evidence_dir / "missing-file.jsonl"
        _write_jsonl(missing_path, missing_inventory)
        missing_inventory_errors = verify_coverage(
            root, evidence_dir / "snapshot.json", missing_path,
            pass_a, pass_b, non_line, exclusions, workspace_units,
        )
        assert any("Inventory/audited_commit-Pfadmenge" in error for error in missing_inventory_errors), missing_inventory_errors

        _write_jsonl(pass_b, [
            _range(by_path["sample.py"], "B", "reviewer-b", 1, 250),
            _range(by_path["small.py"], "B", "reviewer-b", 1, 150),
        ])
        assert any("Rangegroesse" in error for error in verify_coverage(
            root, evidence_dir / "snapshot.json", evidence_dir / "files.jsonl",
            pass_a, pass_b, non_line, exclusions, workspace_units,
        ))
        _write_jsonl(pass_b, [
            _range(by_path["sample.py"], "B", "reviewer-b", 1, 150),
            _range(by_path["sample.py"], "B", "reviewer-b", 151, 250),
            _range(by_path["small.py"], "B", "reviewer-b", 1, 50),
            _range(by_path["small.py"], "B", "reviewer-b", 51, 150),
        ])
        assert any("genau eine Range" in error for error in verify_coverage(
            root, evidence_dir / "snapshot.json", evidence_dir / "files.jsonl",
            pass_a, pass_b, non_line, exclusions, workspace_units,
        ))
        _write_jsonl(pass_b, [
            _range(by_path["sample.py"], "B", "reviewer-b", 1, 150),
            _range(by_path["sample.py"], "B", "reviewer-b", 151, 250),
            _range(by_path["small.py"], "B", "reviewer-b", 1, 150),
        ])

        altered = copy.deepcopy(files)
        altered[0]["snapshot_id"] = "manipulated"
        altered_path = evidence_dir / "altered.jsonl"
        _write_jsonl(altered_path, altered)
        assert any("snapshot_id" in error for error in verify_coverage(
            root, evidence_dir / "snapshot.json", altered_path,
            pass_a, pass_b, non_line, exclusions, workspace_units,
        ))
        derived = copy.deepcopy(files)
        next(row for row in derived if row["path"] == "sample.py")["line_count"] = 1
        derived_path = evidence_dir / "derived.jsonl"
        _write_jsonl(derived_path, derived)
        assert any("abgeleitetes Feld line_count" in error for error in verify_coverage(
            root, evidence_dir / "snapshot.json", derived_path,
            pass_a, pass_b, non_line, exclusions, workspace_units,
        ))
        _write_jsonl(workspace_units, [{
            "scope": "ignored-root", "path": "cache/", "decision": "unresolved",
        }])
        scope_errors = verify_coverage(
            root, evidence_dir / "snapshot.json", evidence_dir / "files.jsonl",
            pass_a, pass_b, non_line, exclusions, workspace_units,
        )
        assert any("Scopeentscheidung" in error for error in scope_errors)
        assert any("workspace_unit_count" in error for error in scope_errors)
        _write_jsonl(workspace_units, [{
            "scope": "external", "path": "models/", "decision": "included-expanded",
            "expanded_manifest": str(evidence_dir / "missing-manifest.jsonl"),
            "manifest_sha256": "missing",
        }])
        assert any("Expansionmanifest" in error for error in verify_coverage(
            root, evidence_dir / "snapshot.json", evidence_dir / "files.jsonl",
            pass_a, pass_b, non_line, exclusions, workspace_units,
        ))
        scope_root = base / "scope-root"
        scope_root.mkdir()
        (scope_root / "included.txt").write_text("included", encoding="utf-8")
        empty_manifest = evidence_dir / "empty-manifest.jsonl"
        _write_jsonl(empty_manifest, [])
        _write_jsonl(workspace_units, [{
            "scope": "external", "path": str(scope_root), "scope_id": "SCOPE-1",
            "scope_root": str(scope_root), "decision": "included-expanded",
            "expanded_manifest": str(empty_manifest),
            "manifest_sha256": hashlib.sha256(empty_manifest.read_bytes()).hexdigest(),
        }])
        assert any("Expansionmanifest ist leer" in error for error in verify_coverage(
            root, evidence_dir / "snapshot.json", evidence_dir / "files.jsonl",
            pass_a, pass_b, non_line, exclusions, workspace_units,
        ))
        _write_jsonl(workspace_units, [{
            "scope": "ignored-root", "path": "cache/", "decision": "excluded-approved",
            "approved_by": "user",
        }])
        assert any("Scope-Exklusionsgenehmigung" in error for error in verify_coverage(
            root, evidence_dir / "snapshot.json", evidence_dir / "files.jsonl",
            pass_a, pass_b, non_line, exclusions, workspace_units,
        ))
        _write_jsonl(workspace_units, [])
        excluded = copy.deepcopy(files)
        asset = next(row for row in excluded if row["path"] == "asset.bin")
        asset["disposition"] = "excluded-approved"
        asset["exclusion_id"] = "EX-001"
        excluded_path = evidence_dir / "excluded.jsonl"
        _write_jsonl(excluded_path, excluded)
        assert any("Exklusion fehlt" in error for error in verify_coverage(
            root, evidence_dir / "snapshot.json", excluded_path,
            pass_a, pass_b, non_line, exclusions, workspace_units,
        ))
        excluded_basis = [
            {key: value for key, value in row.items() if key != "snapshot_id"}
            for row in excluded
        ]
        excluded_snapshot_id = _snapshot_basis(excluded_basis, [])
        for row in excluded:
            row["snapshot_id"] = excluded_snapshot_id
        positive_excluded_path = evidence_dir / "positive-excluded.jsonl"
        _write_jsonl(positive_excluded_path, excluded)
        positive_excluded_snapshot = json.loads(
            (evidence_dir / "snapshot.json").read_text(encoding="utf-8")
        )
        positive_excluded_snapshot["snapshot_id"] = excluded_snapshot_id
        positive_excluded_snapshot_path = evidence_dir / "positive-excluded-snapshot.json"
        positive_excluded_snapshot_path.write_text(
            json.dumps(positive_excluded_snapshot), encoding="utf-8"
        )
        excluded_a_rows = [json.loads(line) for line in pass_a.read_text(encoding="utf-8").splitlines()]
        excluded_b_rows = [json.loads(line) for line in pass_b.read_text(encoding="utf-8").splitlines()]
        excluded_unit_rows = [
            json.loads(line) for line in non_line.read_text(encoding="utf-8").splitlines()
            if json.loads(line).get("path") != "asset.bin"
        ]
        for row in excluded_a_rows + excluded_b_rows + excluded_unit_rows:
            row["snapshot_id"] = excluded_snapshot_id
        positive_excluded_a = evidence_dir / "positive-excluded-a.jsonl"
        positive_excluded_b = evidence_dir / "positive-excluded-b.jsonl"
        positive_excluded_units = evidence_dir / "positive-excluded-units.jsonl"
        positive_exclusions = evidence_dir / "positive-exclusions.jsonl"
        positive_excluded_roster = evidence_dir / "positive-excluded-roster.jsonl"
        _write_jsonl(positive_excluded_a, excluded_a_rows)
        _write_jsonl(positive_excluded_b, excluded_b_rows)
        _write_jsonl(positive_excluded_units, excluded_unit_rows)
        _write_jsonl(positive_exclusions, [{
            "run_id": RUN_ID, "exclusion_id": "EX-001", "path": "asset.bin",
            "reason": "self-test", "approved_by": "user",
            "approved_at": "2026-08-15T00:00:00Z", "decision_ref": "D-SELFTEST",
        }])
        excluded_roster_rows = [
            json.loads(line)
            for line in (evidence_dir / "reviewer_roster.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        for row in excluded_roster_rows:
            row["snapshot_id"] = excluded_snapshot_id
        _write_jsonl(positive_excluded_roster, excluded_roster_rows)
        positive_excluded_snapshot = json.loads(
            positive_excluded_snapshot_path.read_text(encoding="utf-8")
        )
        positive_excluded_snapshot["reviewer_roster_sha256"] = hashlib.sha256(
            positive_excluded_roster.read_bytes()
        ).hexdigest()
        positive_excluded_snapshot_path.write_text(
            json.dumps(positive_excluded_snapshot), encoding="utf-8"
        )
        positive_excluded_errors = _verify_coverage(
            root, positive_excluded_snapshot_path, positive_excluded_path,
            positive_excluded_a, positive_excluded_b, positive_excluded_units,
            positive_exclusions, workspace_units, positive_excluded_roster,
        )
        assert not [error for error in positive_excluded_errors if not error.startswith("Reviewer-Live-Enrollment-Harness fehlt")]

        dirty = root / "dirty.tmp"
        dirty.write_text("dirty", encoding="utf-8")
        try:
            build(root, base / "dirty-evidence", run_id=RUN_ID)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Dirty working tree wurde nicht abgewiesen")
        dirty.unlink()
        try:
            build(root, root / "in-repo-evidence", run_id=RUN_ID)
        except RuntimeError as exc:
            assert "innerhalb Produkt-Worktree" in str(exc)
        else:
            raise AssertionError("In-Repo-Evidence wurde nicht abgewiesen")
        included_source = scope_root / "included.txt"
        included_data = included_source.read_bytes()
        positive_manifest = base / "positive-manifest.jsonl"
        _write_jsonl(positive_manifest, [{
            "path": "scope/SCOPE-1/included.txt",
            "source_path": str(included_source.resolve()),
            "relative_path": "included.txt",
            "git_mode": "external", "git_object_type": "file", "git_blob": None,
            "sha256": hashlib.sha256(included_data).hexdigest(),
            "bytes": len(included_data), "media": "text", "encoding": "utf-8",
            "eol": "none", "line_count": 1,
            "category": "repo_dependency_config", "generated_candidate": False,
            "lfs_pointer": False, "disposition": "direct-review", "exclusion_id": None,
        }])
        decisions = base / "scope-decisions.jsonl"
        _write_jsonl(decisions, [{
            "scope": "external", "path": str(scope_root), "scope_id": "SCOPE-1",
            "scope_root": str(scope_root), "decision": "included-expanded",
            "expanded_manifest": str(positive_manifest),
            "manifest_sha256": hashlib.sha256(positive_manifest.read_bytes()).hexdigest(),
        }])
        scoped_evidence = base / "scoped-evidence"
        scoped_summary = build(root, scoped_evidence, decisions, RUN_ID)
        _bind_reviewer_roster(scoped_evidence, root)
        scoped_files = [
            json.loads(line) for line in (scoped_evidence / "files.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert scoped_summary["workspace_unit_count"] == 1
        assert any(row.get("origin") == "scope" and row.get("scope_id") == "SCOPE-1" for row in scoped_files)
        scoped_a = scoped_evidence / "a.jsonl"
        scoped_b = scoped_evidence / "b.jsonl"
        _write_jsonl(scoped_a, [
            row for meta in scoped_files for row in _ranges_for(meta, "A", "reviewer-a")
        ])
        _write_jsonl(scoped_b, [
            row for meta in scoped_files for row in _ranges_for(meta, "B", "reviewer-b")
        ])
        scoped_units = []
        for meta in scoped_files:
            kinds = ["metadata"]
            if meta["media"] == "binary":
                kinds.append("binary-content")
            if meta["media"] == "text" and not meta["line_count"]:
                kinds.append("empty-file")
            for kind in kinds:
                scoped_units.extend([
                    _unit(meta, kind, "A", "reviewer-a"),
                    _unit(meta, kind, "B", "reviewer-b"),
                ])
        scoped_non_line = scoped_evidence / "non-line.jsonl"
        scoped_exclusions = scoped_evidence / "exclusions.jsonl"
        _write_jsonl(scoped_non_line, scoped_units)
        _write_jsonl(scoped_exclusions, [])
        positive_scope_errors = verify_coverage(
            root, scoped_evidence / "snapshot.json", scoped_evidence / "files.jsonl",
            scoped_a, scoped_b, scoped_non_line, scoped_exclusions,
            scoped_evidence / "workspace_units.jsonl",
        )
        assert not positive_scope_errors, positive_scope_errors
        info_exclude = root / ".git" / "info" / "exclude"
        original_exclude = info_exclude.read_text(encoding="utf-8")
        info_exclude.write_text(original_exclude + "\nignored-current/\n", encoding="utf-8")
        ignored_current = root / "ignored-current"
        ignored_current.mkdir()
        (ignored_current / "drift.txt").write_text("drift", encoding="utf-8")
        assert any("untracked/ignored Scopewurzeln" in error for error in verify_coverage(
            root, scoped_evidence / "snapshot.json", scoped_evidence / "files.jsonl",
            scoped_a, scoped_b, scoped_non_line, scoped_exclusions,
            scoped_evidence / "workspace_units.jsonl",
        ))
        (ignored_current / "drift.txt").unlink()
        ignored_current.rmdir()
        info_exclude.write_text(original_exclude, encoding="utf-8")
        manifest_rows = [json.loads(line) for line in positive_manifest.read_text(encoding="utf-8").splitlines()]
        duplicate_manifest_rows = copy.deepcopy(manifest_rows)
        duplicate = copy.deepcopy(duplicate_manifest_rows[0])
        duplicate["path"] = "scope/SCOPE-1/duplicate.txt"
        duplicate_manifest_rows.append(duplicate)
        duplicate_manifest = scoped_evidence / "duplicate-source-manifest.jsonl"
        _write_jsonl(duplicate_manifest, duplicate_manifest_rows)
        duplicate_workspace = [json.loads(line) for line in (scoped_evidence / "workspace_units.jsonl").read_text(encoding="utf-8").splitlines()]
        duplicate_workspace[0]["expanded_manifest"] = str(duplicate_manifest)
        duplicate_workspace[0]["manifest_sha256"] = hashlib.sha256(duplicate_manifest.read_bytes()).hexdigest()
        duplicate_workspace_path = scoped_evidence / "duplicate-source-workspace.jsonl"
        _write_jsonl(duplicate_workspace_path, duplicate_workspace)
        assert any("doppelte source_path" in error for error in verify_coverage(
            root, scoped_evidence / "snapshot.json", scoped_evidence / "files.jsonl",
            scoped_a, scoped_b, scoped_non_line, scoped_exclusions,
            duplicate_workspace_path,
        ))
        overlap_workspace = [json.loads(line) for line in (scoped_evidence / "workspace_units.jsonl").read_text(encoding="utf-8").splitlines()]
        overlap_unit = copy.deepcopy(overlap_workspace[0])
        overlap_unit["scope_id"] = "SCOPE-2"
        overlap_unit["path"] = str(scope_root) + "-overlap"
        overlap_workspace.append(overlap_unit)
        overlap_workspace_path = scoped_evidence / "overlap-workspace.jsonl"
        _write_jsonl(overlap_workspace_path, overlap_workspace)
        assert any("bereits deklariert in Scope" in error for error in verify_coverage(
            root, scoped_evidence / "snapshot.json", scoped_evidence / "files.jsonl",
            scoped_a, scoped_b, scoped_non_line, scoped_exclusions,
            overlap_workspace_path,
        ))
        same_id_workspace = [json.loads(line) for line in (scoped_evidence / "workspace_units.jsonl").read_text(encoding="utf-8").splitlines()]
        same_id_alias = copy.deepcopy(same_id_workspace[0])
        same_id_alias["path"] = str(scope_root) + "-same-id-alias"
        same_id_workspace.append(same_id_alias)
        same_id_workspace_path = scoped_evidence / "same-id-alias-workspace.jsonl"
        _write_jsonl(same_id_workspace_path, same_id_workspace)
        same_id_errors = verify_coverage(
            root, scoped_evidence / "snapshot.json", scoped_evidence / "files.jsonl",
            scoped_a, scoped_b, scoped_non_line, scoped_exclusions,
            same_id_workspace_path,
        )
        assert any("doppelte scope_id" in error for error in same_id_errors)
        assert any("bereits deklariert in Scope" in error for error in same_id_errors)
        wrong_relative_rows = copy.deepcopy(manifest_rows)
        wrong_relative_rows[0]["relative_path"] = "wrong.txt"
        wrong_relative_manifest = scoped_evidence / "wrong-relative-manifest.jsonl"
        _write_jsonl(wrong_relative_manifest, wrong_relative_rows)
        wrong_relative_workspace = copy.deepcopy(duplicate_workspace)
        wrong_relative_workspace[0]["expanded_manifest"] = str(wrong_relative_manifest)
        wrong_relative_workspace[0]["manifest_sha256"] = hashlib.sha256(wrong_relative_manifest.read_bytes()).hexdigest()
        wrong_relative_workspace_path = scoped_evidence / "wrong-relative-workspace.jsonl"
        _write_jsonl(wrong_relative_workspace_path, wrong_relative_workspace)
        assert any("relative_path/source_path" in error for error in verify_coverage(
            root, scoped_evidence / "snapshot.json", scoped_evidence / "files.jsonl",
            scoped_a, scoped_b, scoped_non_line, scoped_exclusions,
            wrong_relative_workspace_path,
        ))
        link_node = scope_root / "link-node"
        link_node.mkdir()
        real_linklike = coverage_module._linklike
        with patch.object(
            coverage_module, "_linklike",
            side_effect=lambda path: path.name == "link-node" or real_linklike(path),
        ):
            _files, link_errors = _enumerate_scope(scope_root)
        assert any("Symlink/Junction" in error for error in link_errors)
        link_node.rmdir()

        class FakeJunction:
            @staticmethod
            def is_symlink() -> bool:
                return False

            @staticmethod
            def is_junction() -> bool:
                return True

        assert _linklike(FakeJunction())  # type: ignore[arg-type]

        def denied_walk(_root: Path, *, followlinks: bool, onerror):
            assert followlinks is False
            onerror(PermissionError("self-test denied"))
            return []

        with patch.object(coverage_module.os, "walk", side_effect=denied_walk):
            _files, permission_errors = _enumerate_scope(scope_root)
        assert any("nicht vollstaendig lesbar" in error for error in permission_errors)
        bad_mode = copy.deepcopy(scoped_files)
        next(row for row in bad_mode if row.get("origin") == "scope")["git_mode"] = "160000"
        bad_mode_path = scoped_evidence / "bad-mode.jsonl"
        _write_jsonl(bad_mode_path, bad_mode)
        assert any("Scope-Dateimodus" in error for error in verify_coverage(
            root, scoped_evidence / "snapshot.json", bad_mode_path,
            scoped_a, scoped_b, scoped_non_line, scoped_exclusions,
            scoped_evidence / "workspace_units.jsonl",
        ))
        bad_source = copy.deepcopy(scoped_files)
        next(row for row in bad_source if row.get("origin") == "scope")["source_path"] = str((root / "sample.py").resolve())
        bad_source_path = scoped_evidence / "bad-source.jsonl"
        _write_jsonl(bad_source_path, bad_source)
        assert any("Manifest-/Inventory-source_path" in error for error in verify_coverage(
            root, scoped_evidence / "snapshot.json", bad_source_path,
            scoped_a, scoped_b, scoped_non_line, scoped_exclusions,
            scoped_evidence / "workspace_units.jsonl",
        ))
        bad_workspace = [json.loads(line) for line in (scoped_evidence / "workspace_units.jsonl").read_text(encoding="utf-8").splitlines()]
        bad_workspace[0]["scope"] = "ignored-root"
        bad_workspace[0]["path"] = "wrong-root/"
        bad_workspace_path = scoped_evidence / "bad-workspace.jsonl"
        _write_jsonl(bad_workspace_path, bad_workspace)
        assert any("ignored scope_root" in error for error in verify_coverage(
            root, scoped_evidence / "snapshot.json", scoped_evidence / "files.jsonl",
            scoped_a, scoped_b, scoped_non_line, scoped_exclusions, bad_workspace_path,
        ))
        bad_summary = dict(scoped_summary)
        bad_summary["file_count"] += 1
        bad_summary_path = scoped_evidence / "bad-summary.json"
        bad_summary_path.write_text(json.dumps(bad_summary), encoding="utf-8")
        assert any("file_count" in error for error in verify_coverage(
            root, bad_summary_path, scoped_evidence / "files.jsonl",
            scoped_a, scoped_b, scoped_non_line, scoped_exclusions,
            scoped_evidence / "workspace_units.jsonl",
        ))

        head = summary["commit_sha"]
        matrix = evidence_dir / "features.jsonl"
        rows = [
            _feature(head, summary["snapshot_id"], "preview"),
            _feature(head, summary["snapshot_id"], "auto-edit"),
        ]
        _write_jsonl(matrix, rows)
        assert not verify_features(matrix, head, summary["snapshot_id"], RUN_ID)
        broken = copy.deepcopy(rows)
        broken[0]["states"]["result"] = {
            "value": "YES",
            "evidence": [{
                "kind": "static", "ref": "sample.py:1", "commit_sha": head,
                "run_id": RUN_ID, "timestamp": "2026-08-15T00:00:00Z",
            }],
        }
        broken[0]["not_checked"].remove("result")
        _write_jsonl(matrix, broken)
        assert any("Runtimebeleg" in error for error in verify_features(matrix, head, summary["snapshot_id"], RUN_ID))
        missing = copy.deepcopy(rows)
        del missing[0]["path_id"]
        _write_jsonl(matrix, missing)
        assert any("path_id" in error for error in verify_features(matrix, head, summary["snapshot_id"], RUN_ID))
        wrong_snapshot = copy.deepcopy(rows)
        wrong_snapshot[0]["snapshot_id"] = "wrong"
        _write_jsonl(matrix, wrong_snapshot)
        assert any("Audit-Snapshot" in error for error in verify_features(matrix, head, summary["snapshot_id"], RUN_ID))
        snapshot = json.loads((evidence_dir / "snapshot.json").read_text(encoding="utf-8"))
        fake_snapshot = dict(snapshot)
        fake_snapshot["snapshot_id"] = "fake"
        assert any("Inventory/Workspace" in error for error in verify_snapshot(
            fake_snapshot, files, [], head,
        ))

        tool_source = (
            "import json\n\n"
            "def validate(value):\n"
            "    return isinstance(value, dict) and set(value) == {'valid'} and value.get('valid') is True\n\n"
            "def verify_attestation_bundle(*args, **kwargs):\n"
            "    return ['fixture bundle missing']\n\n"
            "if __name__ == '__main__':\n"
            "    print(json.dumps({'ok': False, 'errors': ['fixture bundle missing']}))\n"
            "    raise SystemExit(2)\n"
        )
        common_tests = """
import importlib.util
import unittest
from pathlib import Path

TOOL = Path(__file__).parents[2] / {tool_name!r}
spec = importlib.util.spec_from_file_location("gate_tool", TOOL)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class GateContractTests(unittest.TestCase):
    def test_positive_minimal(self): self.assertTrue(module.validate({{"valid": True}}))
    def test_missing_required_rejected(self): self.assertFalse(module.validate({{}}))
    def test_tampered_binding_rejected(self): self.assertFalse(module.validate({{"valid": False}}))
    def test_duplicate_or_foreign_id_rejected(self): self.assertFalse(module.validate({{"valid": True, "foreign": True}}))
    def {specific}(self): self.assertFalse(module.validate(None))

if __name__ == "__main__": unittest.main()
"""
        for _, (tool_path, test_path, specific) in sorted(REQUIRED_GATES.items()):
            tool = root / tool_path
            tool.parent.mkdir(parents=True, exist_ok=True)
            tool.write_text(tool_source, encoding="utf-8")
            test = root / test_path
            test.parent.mkdir(parents=True, exist_ok=True)
            test.write_text(common_tests.format(tool_name=tool_path, specific=specific), encoding="utf-8")
        source_root = Path(__file__).resolve().parents[4]
        support_paths = (REVIEWER_RUNTIME_PATHS - {"tools/audit_reviewer_roster.py"}) | {
            READINESS_VALIDATOR_PATH,
        }
        for relative in sorted(support_paths):
            source = source_root / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        _git(root, "add", "--", *sorted(AUTHORITY_BOUND_PATHS))
        _git(root, "commit", "-m", "add readiness fixtures")
        tooling_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True,
            capture_output=True, text=True,
        ).stdout.strip()
        authority_artifacts = []
        for relative in sorted(AUTHORITY_BOUND_PATHS):
            data = _git_bytes(root, "show", f"{tooling_commit}:{relative}")
            blob_oid = _git_bytes(
                root, "rev-parse", f"{tooling_commit}:{relative}",
            ).decode().strip()
            authority_artifacts.append({
                "path": relative, "blob_oid": blob_oid, "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            })
        authority_policy = {
            "schema_version": 1,
            "plan_id": "PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15",
            "tooling_commit": tooling_commit,
            "gate_matrix": _gate_matrix(),
            "artifacts": authority_artifacts,
        }
        authority_commit = _commit_authority_policy(
            root, base, tooling_commit, authority_policy, "authority-valid",
        )
        authority, authority_errors = _load_authority_policy(
            root, authority_commit, authority_commit,
        )
        assert authority_errors == [], authority_errors
        artifact_rows = []
        for relative in sorted(REQUIRED_ARTIFACTS):
            data = subprocess.run(
                ["git", "show", f"{tooling_commit}:{relative}"], cwd=root,
                check=True, capture_output=True,
            ).stdout
            artifact_rows.append({
                "run_id": RUN_ID, "tooling_commit": tooling_commit,
                "path": relative, "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            })
        readiness_roster = base / "readiness-roster.jsonl"
        roster_rows = [
            {"run_id": RUN_ID, "reviewer_id": "lead-v", "session_id": "session-lead", "ancestor_session_ids": ["director"], "commit_sha": tooling_commit},
            {"run_id": RUN_ID, "reviewer_id": "adversarial", "session_id": "session-adversarial", "ancestor_session_ids": ["director"], "commit_sha": tooling_commit},
        ]
        _write_jsonl(readiness_roster, roster_rows)
        roster_sha = hashlib.sha256(readiness_roster.read_bytes()).hexdigest()
        bundle_manifest = base / "readiness-attestation-bundle.json"
        bundle_manifest.write_text(json.dumps({
            "schema_version": 1,
            "receipts_dir": str(base / "receipts"),
            "attestations_dir": str(base / "attestations"),
            "contract_path": str(base / "reviewer-contract.json"),
            "contract_signature": str(base / "reviewer-contract.json.sig"),
            "spawn_journal_path": str(base / "spawn-journal.json"),
            "spawn_journal_signature": str(base / "spawn-journal.json.sig"),
            "readiness_binding_path": str(base / "readiness-binding.json"),
            "readiness_binding_signature": str(base / "readiness-binding.json.sig"),
            "expected_readiness_binding_sha256": "a" * 64,
            "audit_contract_path": str(base / "audit-contract.json"),
            "audit_contract_signature": str(base / "audit-contract.json.sig"),
            "expected_audit_contract_sha256": "b" * 64,
            "authority_public_key_path": str(base / "authority.pub"),
            "spawn_public_key_path": str(base / "spawn.pub"),
            "lead_v_public_key_path": str(base / "lead-v.pub"),
            "adversarial_public_key_path": str(base / "adversarial.pub"),
        }, sort_keys=True), encoding="utf-8")
        readiness = {
            "schema_version": 3, "plan_id": "PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15",
            "run_id": RUN_ID, "tooling_commit": tooling_commit, "integration_head": tooling_commit,
            "matrix_version": 1, "artifacts": artifact_rows,
            "reviewer_roster_path": str(readiness_roster), "reviewer_roster_sha256": roster_sha,
            "attestation_bundle_path": str(bundle_manifest),
            "attestation_bundle_sha256": hashlib.sha256(bundle_manifest.read_bytes()).hexdigest(),
        }
        basis = _basis(readiness, artifact_rows, roster_sha, authority)
        missing_bridge = _verify_attestation_bundle(
            root, json.loads(bundle_manifest.read_text(encoding="utf-8")), authority,
            basis_sha256=basis, roster_path=readiness_roster,
            tooling_commit=tooling_commit,
        )
        assert missing_bridge == ["fixture bundle missing"], missing_bridge
        readiness_path = base / "readiness.json"
        readiness_path.write_text(json.dumps(readiness), encoding="utf-8")
        readiness_args = {
            "authority_commit": authority_commit,
            "expected_authority_commit": authority_commit,
        }
        cli = subprocess.run(
            [
                sys.executable, "-B", str(Path(__file__).with_name("verify_audit_readiness.py")),
                "--root", str(root), "--manifest", str(readiness_path),
                "--authority-commit", authority_commit,
                "--expected-authority-commit", authority_commit,
                "--print-basis",
            ],
            cwd=root,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert cli.returncode == 0, cli.stdout + cli.stderr
        assert cli.stdout.strip() == basis, cli.stdout
        with patch("verify_audit_readiness._run_gates", return_value=[]), patch(
            "verify_audit_readiness._verify_attestation_bundle", return_value=[]
        ) as signed_bundle:
            readiness_errors = verify_readiness(root, readiness_path, **readiness_args)
        assert readiness_errors == [], readiness_errors
        assert signed_bundle.call_args.kwargs["basis_sha256"] == basis
        empty_test = base / "comment-only-test.py"
        empty_test.write_text("# no tests\n", encoding="utf-8")
        test_env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        assert _run_test_node(
            base, str(empty_test), "test_positive_minimal", test_env,
        ).returncode != 0
        broken_readiness = copy.deepcopy(readiness)
        broken_readiness["signoffs"] = []
        broken_readiness_path = base / "readiness-broken.json"
        broken_readiness_path.write_text(json.dumps(broken_readiness), encoding="utf-8")
        assert any(
            "Manifest-Feldmenge" in error
            for error in verify_readiness(root, broken_readiness_path, **readiness_args)
        )
        tampered_bundle = copy.deepcopy(readiness)
        tampered_bundle["attestation_bundle_sha256"] = "0" * 64
        tampered_bundle_path = base / "readiness-tampered-bundle.json"
        tampered_bundle_path.write_text(json.dumps(tampered_bundle), encoding="utf-8")
        assert any(
            "attestation_bundle_sha256" in error
            for error in verify_readiness(root, tampered_bundle_path, **readiness_args)
        )
        with patch("verify_audit_readiness._run_gates", return_value=[]), patch(
            "verify_audit_readiness._verify_attestation_bundle", return_value=["Signatur falsch"]
        ):
            assert "Signatur falsch" in verify_readiness(
                root, readiness_path, **readiness_args,
            )
        with patch("verify_audit_readiness._run_gates", return_value=[]):
            real_bridge_errors = verify_readiness(root, readiness_path, **readiness_args)
        assert real_bridge_errors == ["fixture bundle missing"], real_bridge_errors

        for number, non_object in enumerate(([], 1, None)):
            path = base / f"readiness-non-object-{number}.json"
            path.write_text(json.dumps(non_object), encoding="utf-8")
            errors = verify_readiness(root, path, **readiness_args)
            assert errors == ["Readiness-Manifest muss Objekt sein"], errors
        assert verify_readiness(root, readiness_path)[0].startswith("authority_commit")
        mismatched_pin = dict(readiness_args)
        mismatched_pin["authority_commit"] = "0" * 40
        assert "externen Trust-Pin" in verify_readiness(
            root, readiness_path, **mismatched_pin,
        )[0]

        no_op = (
            b"import unittest\nclass GateContractTests(unittest.TestCase):\n"
            b"    def test_positive_minimal(self): pass\n"
        )
        no_op_oid = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"], cwd=root, check=True,
            input=no_op, capture_output=True,
        ).stdout.decode().strip()
        bad_policy = copy.deepcopy(authority_policy)
        substituted_test = "tests/audit/test_audit_feature_inventory.py"
        for row in bad_policy["artifacts"]:
            if row["path"] == substituted_test:
                row.update({
                    "blob_oid": no_op_oid, "bytes": len(no_op),
                    "sha256": hashlib.sha256(no_op).hexdigest(),
                })
        bad_authority_commit = _commit_authority_policy(
            root, base, tooling_commit, bad_policy, "authority-no-op-test",
        )
        _, bad_policy_errors = _load_authority_policy(
            root, bad_authority_commit, bad_authority_commit,
        )
        assert any(substituted_test in error for error in bad_policy_errors), bad_policy_errors
        _, joint_substitution_errors = _load_authority_policy(
            root, bad_authority_commit, authority_commit,
        )
        assert joint_substitution_errors == [
            "authority_commit weicht vom externen Trust-Pin ab",
        ]

        _git(root, "replace", authority_commit, bad_authority_commit)
        try:
            _, replacement_errors = _load_authority_policy(
                root, authority_commit, authority_commit,
            )
            assert replacement_errors == [], replacement_errors
        finally:
            _git(root, "replace", "-d", authority_commit)

        dirty_test = root / substituted_test
        committed_test = _git_bytes(root, "show", f"{tooling_commit}:{substituted_test}")
        dirty_test.write_bytes(no_op)
        materialized = base / "materialized-no-op-attack"
        assert _materialize_bound_files(
            root, tooling_commit, authority, materialized, {substituted_test},
        ) == []
        assert (materialized / substituted_test).read_bytes() == committed_test
        assert (materialized / substituted_test).read_bytes() != no_op
        dirty_test.write_bytes(committed_test)

        committed_reviewer = _git_bytes(
            root, "show", f"{tooling_commit}:tools/audit_reviewer_roster.py",
        )
        mutable_reviewer = root / "tools/audit_reviewer_roster.py"
        mutable_reviewer.write_text(
            "import json\nprint(json.dumps({'ok': True, 'errors': []}))\n",
            encoding="utf-8",
        )
        saved_modules = {
            name: sys.modules.get(name) for name in ("tools", "tools.agent_session")
        }
        sys.modules["tools"] = types.ModuleType("tools")
        sys.modules["tools.agent_session"] = types.ModuleType("tools.agent_session")
        try:
            immutable_bridge_errors = _verify_attestation_bundle(
                root, json.loads(bundle_manifest.read_text(encoding="utf-8")), authority,
                basis_sha256=basis, roster_path=readiness_roster,
                tooling_commit=tooling_commit,
            )
            assert immutable_bridge_errors == ["fixture bundle missing"], immutable_bridge_errors
        finally:
            for name, previous in saved_modules.items():
                if previous is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = previous
            mutable_reviewer.write_bytes(committed_reviewer)

        bundle_value = json.loads(bundle_manifest.read_text(encoding="utf-8"))
        for label, source in (
            ("syntax", "def broken(:\n"),
            ("runtime", "raise RuntimeError('boom')\n"),
        ):
            broken_root = base / f"reviewer-{label}"
            broken_tool = broken_root / "tools/audit_reviewer_roster.py"
            broken_tool.parent.mkdir(parents=True)
            broken_tool.write_text(source, encoding="utf-8")
            bridge_errors = _run_materialized_reviewer(
                broken_root, root, bundle_value, basis_sha256=basis,
                roster_path=readiness_roster, tooling_commit=tooling_commit,
            )
            assert bridge_errors and "Receipt" in bridge_errors[0], bridge_errors
    print("self-test: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
