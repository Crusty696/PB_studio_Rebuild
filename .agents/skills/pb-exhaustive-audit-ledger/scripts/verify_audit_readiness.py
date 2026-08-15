#!/usr/bin/env python3
"""Fail-closed Phase-minus-1 gate. Commands come from code, never manifest."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
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
MANIFEST_FIELDS = {
    "schema_version", "plan_id", "run_id", "tooling_commit",
    "integration_head", "matrix_version", "artifacts",
    "reviewer_roster_path", "reviewer_roster_sha256",
    "attestation_bundle_path", "attestation_bundle_sha256",
}
BUNDLE_FIELDS = {
    "schema_version", "receipts_dir", "attestations_dir", "contract_path",
    "contract_signature", "spawn_journal_path", "spawn_journal_signature",
    "readiness_binding_path", "readiness_binding_signature",
    "expected_readiness_binding_sha256", "audit_contract_path",
    "audit_contract_signature", "expected_audit_contract_sha256",
    "authority_public_key_path", "spawn_public_key_path",
    "lead_v_public_key_path", "adversarial_public_key_path",
}
BUNDLE_SHA_FIELDS = {
    "expected_readiness_binding_sha256", "expected_audit_contract_sha256",
}
UNITTEST_LOADER = (
    "import importlib.util,sys,unittest;"
    "p,n=sys.argv[1],sys.argv[2];"
    "s=importlib.util.spec_from_file_location('pb_gate_contract',p);"
    "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
    "q=unittest.defaultTestLoader.loadTestsFromName(n,m);"
    "r=unittest.TextTestRunner(verbosity=2).run(q);"
    "raise SystemExit(0 if r.wasSuccessful() and r.testsRun==1 else 2)"
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(root: Path, *args: str) -> bytes:
    env = {**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"}
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, env=env,
    ).stdout


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
        "reviewer_roster_sha256": roster_sha,
        "attestation_bundle_sha256": manifest.get("attestation_bundle_sha256"),
        "gate_matrix": matrix,
    }
    return _sha(_canonical(payload))


def _load_bundle_manifest(path: Path, expected_sha: str) -> tuple[dict[str, Any], list[str]]:
    try:
        data = path.read_bytes()
        value = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, [f"Attestation-Bundle-Manifest unlesbar: {exc}"]
    errors: list[str] = []
    if _sha(data) != expected_sha:
        errors.append("attestation_bundle_sha256 falsch")
    if not isinstance(value, dict) or set(value) != BUNDLE_FIELDS:
        errors.append("Attestation-Bundle-Manifest-Feldmenge falsch")
        return {}, errors
    if value.get("schema_version") != 1:
        errors.append("Attestation-Bundle schema_version muss 1 sein")
    for field in BUNDLE_FIELDS - {"schema_version"}:
        item = value.get(field)
        if not isinstance(item, str) or not item.strip():
            errors.append(f"Attestation-Bundle {field} fehlt")
            continue
        if field in BUNDLE_SHA_FIELDS:
            if len(item) != 64 or any(char not in "0123456789abcdef" for char in item):
                errors.append(f"Attestation-Bundle {field} muss SHA-256 sein")
        elif not Path(item).is_absolute():
            errors.append(f"Attestation-Bundle {field} muss absoluter Pfad sein")
    return value, errors


def _verify_attestation_bundle(
    root: Path, bundle: dict[str, Any], *, basis_sha256: str,
    roster_path: Path, tooling_commit: str,
) -> list[str]:
    tool_path = root / "tools" / "audit_reviewer_roster.py"
    try:
        spec = importlib.util.spec_from_file_location("pb_audit_reviewer_roster", tool_path)
        if spec is None or spec.loader is None:
            return ["Reviewer-Bundle-Validator nicht ladbar"]
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except (OSError, ImportError, AttributeError) as exc:
        return [f"Reviewer-Bundle-Validator nicht ladbar: {exc}"]
    verifier = getattr(module, "verify_attestation_bundle", None)
    if not callable(verifier):
        return ["Reviewer-Bundle-Validator exportiert verify_attestation_bundle nicht"]
    def path(name: str) -> Path:
        return Path(str(bundle[name]))

    try:
        result = verifier(
            root, roster_path, path("receipts_dir"), path("attestations_dir"),
            basis_sha256=basis_sha256,
            contract_path=path("contract_path"),
            contract_signature=path("contract_signature"),
            spawn_journal_path=path("spawn_journal_path"),
            spawn_journal_signature=path("spawn_journal_signature"),
            readiness_binding_path=path("readiness_binding_path"),
            readiness_binding_signature=path("readiness_binding_signature"),
            expected_readiness_binding_sha256=str(bundle["expected_readiness_binding_sha256"]),
            tooling_commit=tooling_commit,
            audit_contract_path=path("audit_contract_path"),
            audit_contract_signature=path("audit_contract_signature"),
            expected_audit_contract_sha256=str(bundle["expected_audit_contract_sha256"]),
            authority_public_key_path=path("authority_public_key_path"),
            spawn_public_key_path=path("spawn_public_key_path"),
            lead_v_public_key_path=path("lead_v_public_key_path"),
            adversarial_public_key_path=path("adversarial_public_key_path"),
        )
    except Exception as exc:
        return [f"Reviewer-Bundle-Validator fehlgeschlagen: {exc}"]
    if not isinstance(result, list) or any(not isinstance(item, str) for item in result):
        return ["Reviewer-Bundle-Validator Rueckgabe ungueltig"]
    return result


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


def _run_test_node(cwd: Path, test_path: str, node: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", "-c", UNITTEST_LOADER, test_path, f"GateContractTests.{node}"],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
    )


def _run_gates(root: Path, commit: str) -> list[str]:
    errors: list[str] = []
    env = {
        **os.environ, "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
    }
    with tempfile.TemporaryDirectory(prefix="pb-audit-readiness-") as temp:
        worktree = Path(temp) / "tree"
        try:
            subprocess.run(["git", "worktree", "add", "--detach", str(worktree), commit], cwd=root, check=True, capture_output=True, timeout=60, env=env)
            for gate, (_, test_path, specific) in sorted(REQUIRED_GATES.items()):
                for node in (*COMMON_TESTS, specific):
                    result = _run_test_node(worktree, test_path, node, env)
                    if result.returncode != 0:
                        tail = (result.stdout + result.stderr)[-800:].replace("\n", " | ")
                        errors.append(f"Gate {gate}/{node}: echter Testlauf Exit {result.returncode}: {tail}")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            errors.append(f"Detached tooling_commit-Testlauf fehlgeschlagen: {exc}")
        finally:
            if worktree.exists():
                removed = subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=root, capture_output=True, env=env)
                if removed.returncode != 0:
                    errors.append("Detached Worktree konnte nicht entfernt werden")
            pruned = subprocess.run(["git", "worktree", "prune"], cwd=root, capture_output=True, env=env)
            if pruned.returncode != 0:
                errors.append("Git-Worktree-Prune fehlgeschlagen")
    return errors


def verify_readiness(
    root: Path, manifest_path: Path, *, verify_bundle: bool = True,
) -> list[str]:
    root = root.resolve()
    try:
        manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Readiness-Manifest unlesbar: {exc}"]
    errors: list[str] = []
    if set(manifest) != MANIFEST_FIELDS:
        errors.append("Readiness-Manifest-Feldmenge falsch")
    if manifest.get("schema_version") != 3:
        errors.append("schema_version muss 3 sein")
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
    if not roster_path.is_absolute():
        errors.append("reviewer_roster_path muss absolut sein")
    try:
        if _sha(roster_path.read_bytes()) != roster_sha:
            errors.append("reviewer_roster_sha256 falsch")
    except OSError as exc:
        errors.append(f"Reviewer-Roster unlesbar: {exc}")

    bundle_path = Path(str(manifest.get("attestation_bundle_path", "")))
    bundle_sha = str(manifest.get("attestation_bundle_sha256", ""))
    if not bundle_path.is_absolute():
        errors.append("attestation_bundle_path muss absolut sein")
    bundle, bundle_errors = _load_bundle_manifest(bundle_path, bundle_sha)
    errors.extend(bundle_errors)
    basis = _basis(manifest, rows, roster_sha)
    if not errors:
        errors.extend(_run_gates(root, commit))
    if not errors and verify_bundle:
        errors.extend(_verify_attestation_bundle(
            root, bundle, basis_sha256=basis, roster_path=roster_path,
            tooling_commit=commit,
        ))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--print-basis", action="store_true")
    args = parser.parse_args()
    errors = verify_readiness(
        args.root, args.manifest, verify_bundle=not args.print_basis,
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 2
    if args.print_basis:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        print(_basis(
            manifest, list(manifest["artifacts"]),
            str(manifest["reviewer_roster_sha256"]),
        ))
        return 0
    print("audit-readiness: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
