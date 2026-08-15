#!/usr/bin/env python3
"""Fail-closed Phase-minus-1 gate with externally pinned authority policy."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

PLAN_ID = "PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15"
AUTHORITY_POLICY_PATH = "config/audit_readiness_authority_policy.json"
READINESS_VALIDATOR_PATH = (
    ".agents/skills/pb-exhaustive-audit-ledger/scripts/verify_audit_readiness.py"
)
REVIEWER_RUNTIME_PATHS = {
    "tools/audit_reviewer_roster.py",
    "tools/agent_session.py",
}
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
AUTHORITY_BOUND_PATHS = REQUIRED_ARTIFACTS | REVIEWER_RUNTIME_PATHS | {READINESS_VALIDATOR_PATH}
MANIFEST_FIELDS = {
    "schema_version", "plan_id", "run_id", "tooling_commit",
    "integration_head", "matrix_version", "artifacts",
    "reviewer_roster_path", "reviewer_roster_sha256",
    "attestation_bundle_path", "attestation_bundle_sha256",
}
MANIFEST_ARTIFACT_FIELDS = {"run_id", "tooling_commit", "path", "bytes", "sha256"}
AUTHORITY_POLICY_FIELDS = {"schema_version", "plan_id", "tooling_commit", "gate_matrix", "artifacts"}
AUTHORITY_ARTIFACT_FIELDS = {"path", "blob_oid", "bytes", "sha256"}
BUNDLE_FIELDS = {
    "schema_version", "receipts_dir", "attestations_dir", "contract_path",
    "contract_signature", "spawn_journal_path", "spawn_journal_signature",
    "readiness_binding_path", "readiness_binding_signature",
    "expected_readiness_binding_sha256", "audit_contract_path",
    "audit_contract_signature", "expected_audit_contract_sha256",
    "authority_public_key_path", "spawn_public_key_path",
    "lead_v_public_key_path", "adversarial_public_key_path",
}
BUNDLE_SHA_FIELDS = {"expected_readiness_binding_sha256", "expected_audit_contract_sha256"}
FULL_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
BLOB_OID_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
UNITTEST_LOADER = (
    "import importlib.util,sys,unittest;"
    "from pathlib import Path;"
    "p,n=sys.argv[1],sys.argv[2];"
    "sys.path.insert(0,str(Path(p).resolve().parents[2]));"
    "s=importlib.util.spec_from_file_location('pb_gate_contract',p);"
    "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
    "q=unittest.defaultTestLoader.loadTestsFromName(n,m);"
    "r=unittest.TextTestRunner(verbosity=2).run(q);"
    "raise SystemExit(0 if r.wasSuccessful() and r.testsRun==1 else 2)"
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_env() -> dict[str, str]:
    env = {**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"}
    for name in (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR",
    ):
        env.pop(name, None)
    return env


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, env=_git_env(),
    ).stdout


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _gate_matrix() -> dict[str, dict[str, Any]]:
    return {
        name: {"tool": pair[0], "test": pair[1], "nodes": [*COMMON_TESTS, pair[2]]}
        for name, pair in sorted(REQUIRED_GATES.items())
    }


def _basis(
    manifest: dict[str, Any], artifacts: list[dict[str, Any]], roster_sha: str,
    authority: dict[str, Any],
) -> str:
    payload = {
        "plan_id": PLAN_ID, "run_id": manifest.get("run_id"),
        "tooling_commit": manifest.get("tooling_commit"),
        "integration_head": manifest.get("integration_head"),
        "matrix_version": manifest.get("matrix_version"),
        "artifacts": sorted(artifacts, key=lambda row: row.get("path", "")),
        "reviewer_roster_sha256": roster_sha,
        "attestation_bundle_sha256": manifest.get("attestation_bundle_sha256"),
        "authority": {
            "authority_commit": authority.get("authority_commit"),
            "expected_authority_commit": authority.get("expected_authority_commit"),
            "policy_path": authority.get("policy_path"),
            "policy_blob_oid": authority.get("policy_blob_oid"),
            "policy_sha256": authority.get("policy_sha256"),
        },
        "gate_matrix": _gate_matrix(),
    }
    return _sha(_canonical(payload))


def _load_authority_policy(
    root: Path, authority_commit: str | None, expected_authority_commit: str | None,
) -> tuple[dict[str, Any], list[str]]:
    """Compare external pin before reading any authority object."""
    if not isinstance(authority_commit, str) or not FULL_COMMIT_RE.fullmatch(authority_commit):
        return {}, ["authority_commit muss externer voller 40-Zeichen-SHA sein"]
    if not isinstance(expected_authority_commit, str) or not FULL_COMMIT_RE.fullmatch(expected_authority_commit):
        return {}, ["expected_authority_commit als externer Trust-Pin fehlt/ungueltig"]
    if authority_commit != expected_authority_commit:
        return {}, ["authority_commit weicht vom externen Trust-Pin ab"]

    root = root.resolve()
    try:
        resolved = _git(root, "rev-parse", f"{authority_commit}^{{commit}}").decode().strip()
        if resolved != authority_commit:
            return {}, ["authority_commit ist nicht kanonisch"]
        raw = _git(root, "show", f"{authority_commit}:{AUTHORITY_POLICY_PATH}")
        blob_oid = _git(root, "rev-parse", f"{authority_commit}:{AUTHORITY_POLICY_PATH}").decode().strip()
    except (subprocess.CalledProcessError, OSError, UnicodeError) as exc:
        return {}, [f"Readiness-Authority-Policy nicht aus Git lesbar: {exc}"]
    try:
        policy = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, [f"Readiness-Authority-Policy unlesbar: {exc}"]
    if not isinstance(policy, dict):
        return {}, ["Readiness-Authority-Policy muss Objekt sein"]

    errors: list[str] = []
    if set(policy) != AUTHORITY_POLICY_FIELDS:
        errors.append("Readiness-Authority-Policy-Feldmenge falsch")
    if policy.get("schema_version") != 1:
        errors.append("Readiness-Authority-Policy schema_version muss 1 sein")
    if policy.get("plan_id") != PLAN_ID:
        errors.append("Readiness-Authority-Policy plan_id falsch")
    tooling_commit = policy.get("tooling_commit")
    if not isinstance(tooling_commit, str) or not FULL_COMMIT_RE.fullmatch(tooling_commit):
        errors.append("Readiness-Authority-Policy tooling_commit ungueltig")
        tooling_commit = ""
    if policy.get("gate_matrix") != _gate_matrix():
        errors.append("Readiness-Authority-Policy Gate-Matrix falsch")

    rows = policy.get("artifacts") if isinstance(policy.get("artifacts"), list) else []
    by_path: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(rows, 1):
        label = f"Readiness-Authority-Artefakt {number}"
        if not isinstance(row, dict) or set(row) != AUTHORITY_ARTIFACT_FIELDS:
            errors.append(f"{label}: Feldmenge falsch")
            continue
        path = row.get("path")
        if not isinstance(path, str) or path not in AUTHORITY_BOUND_PATHS or path in by_path:
            errors.append(f"{label}: Pfad fremd/fehlt/doppelt")
            continue
        if type(row.get("bytes")) is not int or row["bytes"] < 0:
            errors.append(f"{label}: bytes ungueltig")
        if not isinstance(row.get("sha256"), str) or not SHA256_RE.fullmatch(row["sha256"]):
            errors.append(f"{label}: sha256 ungueltig")
        if not isinstance(row.get("blob_oid"), str) or not BLOB_OID_RE.fullmatch(row["blob_oid"]):
            errors.append(f"{label}: blob_oid ungueltig")
        by_path[path] = row
    if set(by_path) != AUTHORITY_BOUND_PATHS or len(rows) != len(AUTHORITY_BOUND_PATHS):
        errors.append("Readiness-Authority-Artefaktmenge nicht exakt")

    if tooling_commit:
        try:
            resolved_tooling = _git(root, "rev-parse", f"{tooling_commit}^{{commit}}").decode().strip()
            if resolved_tooling != tooling_commit:
                errors.append("Policy-tooling_commit ist nicht kanonisch")
        except (subprocess.CalledProcessError, OSError, UnicodeError):
            errors.append("Policy-tooling_commit existiert nicht")
        for path, row in sorted(by_path.items()):
            try:
                data = _git(root, "show", f"{tooling_commit}:{path}")
                actual_oid = _git(root, "rev-parse", f"{tooling_commit}:{path}").decode().strip()
            except (subprocess.CalledProcessError, OSError, UnicodeError):
                errors.append(f"{path}: fehlt im Policy-tooling_commit")
                continue
            if row.get("bytes") != len(data) or row.get("sha256") != _sha(data) or row.get("blob_oid") != actual_oid:
                errors.append(f"{path}: Policy-Blob/Bytes/SHA weicht vom tooling_commit ab")

    validator = by_path.get(READINESS_VALIDATOR_PATH)
    try:
        live_bytes = Path(__file__).resolve().read_bytes()
    except OSError as exc:
        errors.append(f"Readiness-Validatorbytes unlesbar: {exc}")
    else:
        if validator and (
            validator.get("bytes") != len(live_bytes) or validator.get("sha256") != _sha(live_bytes)
        ):
            errors.append("Ausgefuehrter Readiness-Validator weicht vom Authority-Blob ab")

    binding = {
        "authority_commit": authority_commit,
        "expected_authority_commit": expected_authority_commit,
        "policy_path": AUTHORITY_POLICY_PATH,
        "policy_blob_oid": blob_oid,
        "policy_sha256": _sha(raw),
        "tooling_commit": tooling_commit,
        "gate_matrix": policy.get("gate_matrix"),
        "artifacts": by_path,
    }
    return binding, errors


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
            if not SHA256_RE.fullmatch(item):
                errors.append(f"Attestation-Bundle {field} muss SHA-256 sein")
        elif not Path(item).is_absolute():
            errors.append(f"Attestation-Bundle {field} muss absoluter Pfad sein")
    return value, errors


def _load_readiness_manifest(path: Path) -> tuple[dict[str, Any], list[str]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, [f"Readiness-Manifest unlesbar: {exc}"]
    if not isinstance(value, dict):
        return {}, ["Readiness-Manifest muss Objekt sein"]
    return value, []


def _materialize_bound_files(
    root: Path, tooling_commit: str, authority: dict[str, Any], destination: Path,
    paths: set[str],
) -> list[str]:
    errors: list[str] = []
    bindings = authority.get("artifacts")
    if not isinstance(bindings, dict):
        return ["Authority-Artefaktbindung fehlt"]
    for relative in sorted(paths):
        row = bindings.get(relative)
        if not isinstance(row, dict):
            errors.append(f"{relative}: Authority-Artefaktbindung fehlt")
            continue
        try:
            data = _git(root, "show", f"{tooling_commit}:{relative}")
            oid = _git(root, "rev-parse", f"{tooling_commit}:{relative}").decode().strip()
        except (subprocess.CalledProcessError, OSError, UnicodeError):
            errors.append(f"{relative}: commitgebundene Materialisierung fehlgeschlagen")
            continue
        if row.get("bytes") != len(data) or row.get("sha256") != _sha(data) or row.get("blob_oid") != oid:
            errors.append(f"{relative}: Authority-Bindung vor Materialisierung falsch")
            continue
        target = destination / Path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if target.read_bytes() != data:
            errors.append(f"{relative}: materialisierte Bytes weichen ab")
    return errors


def _run_test_node(
    cwd: Path, test_path: str, node: str, env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-B", "-c", UNITTEST_LOADER, test_path, f"GateContractTests.{node}"],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=120,
    )


def _run_gates(root: Path, commit: str, authority: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    env = _git_env()
    env.update({"PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"})
    with tempfile.TemporaryDirectory(prefix="pb-audit-readiness-") as temp:
        materialized = Path(temp) / "tree"
        errors.extend(_materialize_bound_files(root, commit, authority, materialized, AUTHORITY_BOUND_PATHS))
        if errors:
            return errors
        for gate, (_, test_path, specific) in sorted(REQUIRED_GATES.items()):
            for node in (*COMMON_TESTS, specific):
                try:
                    result = _run_test_node(materialized, test_path, node, env)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    errors.append(f"Gate {gate}/{node}: Testlauf fehlgeschlagen: {exc}")
                    continue
                if result.returncode != 0:
                    tail = (result.stdout + result.stderr)[-800:].replace("\n", " | ")
                    errors.append(f"Gate {gate}/{node}: echter Testlauf Exit {result.returncode}: {tail}")
    return errors


def _reviewer_command(
    script: Path, root: Path, bundle: dict[str, Any], *, basis_sha256: str,
    roster_path: Path, tooling_commit: str,
) -> list[str]:
    def value(name: str) -> str:
        return str(bundle[name])

    return [
        sys.executable, "-I", "-B", str(script), "verify-bundle",
        "--root", str(root), "--contract", value("contract_path"),
        "--contract-signature", value("contract_signature"),
        "--spawn-journal", value("spawn_journal_path"),
        "--spawn-journal-signature", value("spawn_journal_signature"),
        "--readiness-binding", value("readiness_binding_path"),
        "--readiness-binding-signature", value("readiness_binding_signature"),
        "--readiness-binding-sha256", value("expected_readiness_binding_sha256"),
        "--tooling-commit", tooling_commit,
        "--audit-contract", value("audit_contract_path"),
        "--audit-contract-signature", value("audit_contract_signature"),
        "--audit-contract-sha256", value("expected_audit_contract_sha256"),
        "--authority-public-key", value("authority_public_key_path"),
        "--spawn-public-key", value("spawn_public_key_path"),
        "--lead-v-public-key", value("lead_v_public_key_path"),
        "--adversarial-public-key", value("adversarial_public_key_path"),
        "--roster", str(roster_path), "--receipts-dir", value("receipts_dir"),
        "--basis-sha256", basis_sha256, "--attestations-dir", value("attestations_dir"),
    ]


def _run_materialized_reviewer(
    materialized: Path, root: Path, bundle: dict[str, Any], *, basis_sha256: str,
    roster_path: Path, tooling_commit: str,
) -> list[str]:
    script = materialized / "tools/audit_reviewer_roster.py"
    try:
        command = _reviewer_command(
            script, root, bundle, basis_sha256=basis_sha256,
            roster_path=roster_path, tooling_commit=tooling_commit,
        )
        env = _git_env()
        env.update({"PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        result = subprocess.run(
            command, cwd=materialized, env=env,
            capture_output=True, text=True, timeout=120,
        )
    except (KeyError, OSError, subprocess.TimeoutExpired) as exc:
        return [f"Reviewer-Bundle-Validator fehlgeschlagen: {exc}"]
    try:
        payload = json.loads(result.stdout.strip())
    except (json.JSONDecodeError, TypeError):
        tail = (result.stdout + result.stderr)[-800:].replace("\n", " | ")
        return [f"Reviewer-Bundle-Validator Exit {result.returncode} ohne gueltiges Receipt: {tail}"]
    if (
        not isinstance(payload, dict) or set(payload) != {"ok", "errors"}
        or not isinstance(payload.get("ok"), bool) or not isinstance(payload.get("errors"), list)
        or any(not isinstance(item, str) for item in payload.get("errors", []))
    ):
        return ["Reviewer-Bundle-Validator Receipt ungueltig"]
    errors = list(payload["errors"])
    if result.returncode == 0 and payload["ok"] is True and not errors:
        return []
    if result.returncode == 0 or payload["ok"] is True or not errors:
        return ["Reviewer-Bundle-Validator Exit/Receipt widerspruechlich"]
    return errors


def _verify_attestation_bundle(
    root: Path, bundle: dict[str, Any], authority: dict[str, Any], *,
    basis_sha256: str, roster_path: Path, tooling_commit: str,
) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="pb-audit-reviewer-") as temp:
        materialized = Path(temp) / "tree"
        errors = _materialize_bound_files(
            root, tooling_commit, authority, materialized, REVIEWER_RUNTIME_PATHS,
        )
        if errors:
            return errors
        return _run_materialized_reviewer(
            materialized, root, bundle, basis_sha256=basis_sha256,
            roster_path=roster_path, tooling_commit=tooling_commit,
        )


def verify_readiness(
    root: Path, manifest_path: Path, *, authority_commit: str | None = None,
    expected_authority_commit: str | None = None, verify_bundle: bool = True,
) -> list[str]:
    root = root.resolve()
    authority, authority_errors = _load_authority_policy(
        root, authority_commit, expected_authority_commit,
    )
    if authority_errors:
        return authority_errors
    manifest, manifest_errors = _load_readiness_manifest(manifest_path)
    if manifest_errors:
        return manifest_errors

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
    if not isinstance(commit, str) or not FULL_COMMIT_RE.fullmatch(commit):
        errors.append("tooling_commit muss volle 40-Zeichen-SHA sein")
        commit = ""
    if commit and authority.get("tooling_commit") != commit:
        errors.append("tooling_commit weicht von externer Authority-Policy ab")
    try:
        head = _git(root, "rev-parse", "HEAD").decode().strip()
        resolved = _git(root, "rev-parse", f"{commit}^{{commit}}").decode().strip() if commit else ""
        if resolved != commit:
            errors.append("tooling_commit ist nicht kanonisch")
        if manifest.get("integration_head") != head or commit != head:
            errors.append("tooling_commit/integration_head muessen aktuellem HEAD entsprechen")
    except (subprocess.CalledProcessError, OSError, UnicodeError):
        errors.append("tooling_commit existiert nicht als Commit")

    rows = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), list) else []
    paths = [row.get("path") for row in rows if isinstance(row, dict)]
    if set(paths) != REQUIRED_ARTIFACTS or len(paths) != len(REQUIRED_ARTIFACTS):
        errors.append("Artefaktmenge entspricht nicht exakt Phase-minus-1-Vertrag")
    for row in rows:
        if (
            not isinstance(row, dict) or set(row) != MANIFEST_ARTIFACT_FIELDS
            or row.get("path") not in REQUIRED_ARTIFACTS
        ):
            errors.append("Artefaktzeile ungueltig/fremd")
            continue
        path = str(row["path"])
        if row.get("run_id") != run_id or row.get("tooling_commit") != commit:
            errors.append(f"{path}: run_id/tooling_commit weicht ab")
        try:
            data = _git(root, "show", f"{commit}:{path}")
        except (subprocess.CalledProcessError, OSError):
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
    basis = _basis(manifest, rows, roster_sha, authority)
    if not errors:
        errors.extend(_run_gates(root, commit, authority))
    if not errors and verify_bundle:
        errors.extend(_verify_attestation_bundle(
            root, bundle, authority, basis_sha256=basis,
            roster_path=roster_path, tooling_commit=commit,
        ))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--authority-commit", required=True)
    parser.add_argument("--expected-authority-commit", required=True)
    parser.add_argument("--print-basis", action="store_true")
    args = parser.parse_args()
    errors = verify_readiness(
        args.root, args.manifest, authority_commit=args.authority_commit,
        expected_authority_commit=args.expected_authority_commit,
        verify_bundle=not args.print_basis,
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 2
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    authority, authority_errors = _load_authority_policy(
        args.root, args.authority_commit, args.expected_authority_commit,
    )
    if authority_errors:
        for error in authority_errors:
            print(f"ERROR: {error}")
        return 2
    basis = _basis(
        manifest, list(manifest["artifacts"]), str(manifest["reviewer_roster_sha256"]), authority,
    )
    if args.print_basis:
        print(basis)
        return 0
    print(json.dumps({
        "ok": True, "basis_sha256": basis,
        "authority_commit": authority["authority_commit"],
        "authority_policy_path": authority["policy_path"],
        "authority_policy_blob_oid": authority["policy_blob_oid"],
        "authority_policy_sha256": authority["policy_sha256"],
        "gate_matrix": _gate_matrix(),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
