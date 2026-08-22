#!/usr/bin/env python3
"""Execute externally pinned audit scenarios and emit content-addressed evidence."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


SHA_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
KNOWN_AXES = {
    "declared", "configured", "wired", "reachable", "enabled", "executed",
    "result", "persisted", "restart_safe", "error", "cancel", "retry",
    "cleanup", "GPU", "DB", "UI", "live_evidence",
}
SURFACE_OBSERVERS = {
    "GPU": ("gpu-device", "cuda:0-observed"),
    "DB": ("db-state", "state-observed"),
    "UI": ("ui-delivery", "delivery-observed"),
}
REQUIRED_SCENARIO_FIELDS = {
    "schema_version", "run_id", "scenario_id", "audited_commit", "tooling_commit",
    "snapshot_id", "scenario_sha256", "feature_target", "harness", "target",
    "timeout_seconds", "inputs", "allowed_symbol_ids", "allowed_axes",
    "required_modules", "required_stdlib_modules", "postcondition", "artifacts",
}
CONTRACT_ARTIFACTS = {
    "scenario_catalog": "runtime-scenario-catalog",
    "feature_universe": "runtime-feature-universe",
    "symbol_universe": "runtime-symbol-universe",
    "executor_manifest": "runtime-executor-manifest",
    "dependency_manifest": "runtime-dependency-manifest",
}
GLOBAL_CONTRACT_ARTIFACTS = {
    "requirements-universe", "trigger-universe", "feature-catalog",
    "symbol-catalog", "edge-catalog", "runtime-scenario-catalog",
    "runtime-feature-universe", "runtime-symbol-universe",
    "runtime-executor-manifest", "runtime-dependency-manifest",
    "reviewer-trust-policy", "reviewer-contract",
    "reviewer-readiness-binding", "reviewer-spawn-journal",
}
CONTRACT_FIELDS = {
    "schema_version", "plan_id", "run_id", "audited_commit", "tooling_commit",
    "snapshot_id", "frozen_at", "expires_at", "artifacts", "contract_sha256",
}
ALLOWED_EXECUTORS = {"python"}
AUTHORITY_POLICY_PATH = "config/audit_runtime_authority_policy.json"
AUTHORITY_POLICY_FIELDS = {
    "schema_version", "audit_contract_sha256", "plan_id", "run_id", "snapshot_id",
    "audited_commit", "tooling_commit", "allow_same_audited_tooling_commit",
}
PROJECTION_FIELDS = {
    "evidence_id", "evidence_kind", "runtime_run_id",
    "covered_feature_paths", "covered_symbol_ids", "covered_axes",
    "proof_ref", "proof_sha256", "run_id", "audited_commit",
    "tooling_commit", "snapshot_id", "timestamp", "record_sha256",
}
RICH_RECEIPT_FIELDS = {
    "plan_id", "run_id", "runtime_run_id", "audited_commit", "tooling_commit",
    "snapshot_id", "scenario_id", "scenario_sha256", "timestamp", "authority",
    "audit_contract", "scenario_catalog", "sealed_contract_inputs",
    "materialization", "runner", "environment", "observer", "input", "inputs",
    "harness", "target", "stdout", "stderr", "exit", "trace", "postcondition",
    "artifacts", "covered_feature_paths", "covered_symbol_ids", "covered_axes",
    "final_integrity_sha256", "evidence_id",
}
RICH_RECEIPT_OPTIONAL_FIELDS = {
    "forced_state", "observed_surfaces", "restart", "reopen",
}
SEALED_INPUT_NAMES = {
    "audit_contract", "authority", "runner", "scenario_catalog",
    "feature_universe", "symbol_universe", "executor_manifest",
    "dependency_manifest",
}
RUN_OWNERSHIP_FILE = ".publish-owner.json"


class ContractError(RuntimeError):
    """Fail-closed contract violation."""


def _canonical_bytes(value: Any, *, omit: set[str] | None = None) -> bytes:
    if isinstance(value, dict) and omit:
        value = {key: item for key, item in value.items() if key not in omit}
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_sha256(value: Any, *, omit: set[str] | None = None) -> str:
    return hashlib.sha256(_canonical_bytes(value, omit=omit)).hexdigest()


def canonical_evidence_id(value: dict[str, Any]) -> str:
    return "sha256:" + canonical_sha256(value, omit={"evidence_id"})


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(repo: Path, *args: str, input_data: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    env = os.environ.copy()
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    return subprocess.run(
        ["git", *args], cwd=repo, input=input_data, check=check,
        capture_output=True, shell=False, env=env,
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _contained(root: Path, candidate: Path, label: str) -> Path:
    root = root.resolve()
    candidate = candidate.resolve()
    if not _is_relative_to(candidate, root):
        raise ContractError(f"{label} liegt ausserhalb erlaubter Wurzel")
    return candidate


def _relative_ref(root: Path, ref: object, label: str) -> Path:
    if not isinstance(ref, str) or not ref.strip():
        raise ContractError(f"{label}: ref fehlt")
    path = Path(ref)
    if path.is_absolute():
        raise ContractError(f"{label}: absoluter Pfad verboten")
    return _contained(root, root / path, label)


def _parse_json(data: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"{label} ist kein gueltiges JSON") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{label}: Objekt erwartet")
    return value


def _parse_jsonl(data: bytes, label: str, *, allow_empty: bool = False) -> list[dict[str, Any]]:
    try:
        lines = data.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise ContractError(f"{label} ist nicht UTF-8") from exc
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractError(f"{label} Zeile {number}: ungueltiges JSON") from exc
        if not isinstance(row, dict):
            raise ContractError(f"{label} Zeile {number}: Objekt erwartet")
        rows.append(row)
    if not rows and not allow_empty:
        raise ContractError(f"{label} ist leer")
    return rows


def _descriptor_record_count(data: bytes, label: str) -> int:
    if label in {
        "runtime-scenario-catalog", "runtime-feature-universe", "runtime-symbol-universe",
    }:
        return len(_parse_jsonl(data, f"Auditvertrag/{label}", allow_empty=True))
    _parse_json(data, f"Auditvertrag/{label}")
    return 1


def _read_bound_ref(evidence: Path, record: object, label: str) -> tuple[Path, bytes]:
    if not isinstance(record, dict):
        raise ContractError(f"Auditvertrag/{label}: Objekt fehlt")
    path = _relative_ref(evidence, record.get("ref"), f"Auditvertrag/{label}")
    if not path.is_file():
        raise ContractError(f"Auditvertrag/{label}: Datei fehlt")
    data = path.read_bytes()
    expected = record.get("sha256")
    if not isinstance(expected, str) or not HASH_RE.fullmatch(expected) or _sha_bytes(data) != expected:
        raise ContractError(f"Auditvertrag/{label}: SHA256 stimmt nicht")
    if set(record) != {"artifact_id", "ref", "sha256", "bytes", "record_count"}:
        raise ContractError(f"Auditvertrag/{label}: Artifact-Schema falsch")
    if (
        record.get("artifact_id") != f"sha256:{expected}"
        or type(record.get("bytes")) is not int
        or record.get("bytes") != len(data)
    ):
        raise ContractError(f"Auditvertrag/{label}: artifact_id/bytes falsch")
    count = _descriptor_record_count(data, label)
    if type(record.get("record_count")) is not int or record["record_count"] != count:
        raise ContractError(f"Auditvertrag/{label}: record_count falsch")
    return path, data


def _load_contract(evidence: Path, contract_path: Path) -> tuple[dict[str, Any], bytes, dict[str, tuple[Path, bytes]]]:
    contract_path = _contained(evidence, contract_path, "audit_contract")
    if not contract_path.is_file():
        raise ContractError("audit_contract fehlt")
    data = contract_path.read_bytes()
    contract = _parse_json(data, "audit_contract")
    if set(contract) != CONTRACT_FIELDS or contract.get("schema_version") != 1:
        raise ContractError("audit_contract Schema/Felder muessen exakt Version 1 entsprechen")
    if contract.get("contract_sha256") != canonical_sha256(contract, omit={"contract_sha256"}):
        raise ContractError("audit_contract.contract_sha256 stimmt nicht")
    for field in ("plan_id", "run_id", "snapshot_id"):
        if not isinstance(contract.get(field), str) or not contract[field]:
            raise ContractError(f"audit_contract.{field} fehlt")
    for field in ("audited_commit", "tooling_commit"):
        if not isinstance(contract.get(field), str) or not SHA_RE.fullmatch(contract[field]):
            raise ContractError(f"audit_contract.{field} muss voller SHA sein")
    timestamps: dict[str, datetime] = {}
    for field in ("frozen_at", "expires_at"):
        try:
            parsed = datetime.fromisoformat(str(contract.get(field)))
        except ValueError as exc:
            raise ContractError(f"audit_contract.{field} ungueltig") from exc
        if parsed.tzinfo is None:
            raise ContractError(f"audit_contract.{field} braucht Zeitzone")
        timestamps[field] = parsed
    now = datetime.now(timezone.utc)
    if timestamps["frozen_at"] > now or timestamps["expires_at"] <= timestamps["frozen_at"]:
        raise ContractError("audit_contract frozen_at/expires_at Reihenfolge ungueltig")
    if timestamps["expires_at"] <= now:
        raise ContractError("audit_contract ist abgelaufen")
    artifacts = contract.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != GLOBAL_CONTRACT_ARTIFACTS:
        raise ContractError("audit_contract.artifacts hat falsche Exact-Set-Menge")
    refs = {name: _read_bound_ref(evidence, artifacts[key], key) for name, key in CONTRACT_ARTIFACTS.items()}
    return contract, data, refs


def _load_authority_policy(
    repo: Path, authority_commit: str, expected_authority_commit: str,
    tooling_commit: str, policy_path: str,
    expected_contract_sha256: str, contract: dict[str, Any],
) -> tuple[dict[str, Any], bytes, str]:
    if not isinstance(authority_commit, str) or not SHA_RE.fullmatch(authority_commit):
        raise ContractError("authority_commit muss voller SHA sein")
    if not isinstance(expected_authority_commit, str) or not SHA_RE.fullmatch(expected_authority_commit):
        raise ContractError("expected_authority_commit muss attestierter voller SHA sein")
    if authority_commit != expected_authority_commit:
        raise ContractError("Authority authority_commit stimmt nicht mit extern attestiertem expected_authority_commit ueberein")
    if authority_commit in {tooling_commit, contract.get("audited_commit")}:
        raise ContractError("authority_commit muss von audited_commit und tooling_commit getrennt sein")
    if _git(repo, "cat-file", "-e", f"{authority_commit}^{{commit}}", check=False).returncode != 0:
        raise ContractError("authority_commit existiert nicht")
    if not isinstance(expected_contract_sha256, str) or not HASH_RE.fullmatch(expected_contract_sha256):
        raise ContractError("Authority expected_contract_sha256 ungueltig")
    if policy_path != AUTHORITY_POLICY_PATH:
        raise ContractError(f"Authority-Policy-Pfad muss fest {AUTHORITY_POLICY_PATH!r} sein")
    result = _git(repo, "show", f"{authority_commit}:{policy_path}", check=False)
    if result.returncode != 0:
        raise ContractError("Authority-Policy fehlt im authority_commit")
    authority = _parse_json(result.stdout, "Authority-Policy")
    if set(authority) != AUTHORITY_POLICY_FIELDS or authority.get("schema_version") != 1:
        raise ContractError("Authority-Policy Exact-Fields/schema_version falsch")
    bindings = {
        "audit_contract_sha256": expected_contract_sha256,
        "plan_id": contract.get("plan_id"), "run_id": contract.get("run_id"),
        "snapshot_id": contract.get("snapshot_id"),
        "audited_commit": contract.get("audited_commit"),
        "tooling_commit": contract.get("tooling_commit"),
    }
    if contract.get("contract_sha256") != expected_contract_sha256:
        raise ContractError("Authority/Auditvertrag expected_contract_sha256 falsch")
    for field, expected in bindings.items():
        if authority.get(field) != expected:
            raise ContractError(f"Authority-Policy Binding falsch: {field}")
    if type(authority.get("allow_same_audited_tooling_commit")) is not bool:
        raise ContractError("Authority-Policy allow_same_audited_tooling_commit muss bool sein")
    if contract.get("audited_commit") == contract.get("tooling_commit") and authority.get("allow_same_audited_tooling_commit") is not True:
        raise ContractError("audited_commit und tooling_commit sind gleich; Authority-Policy verbietet dies")
    oid = _git(repo, "rev-parse", f"{authority_commit}:{policy_path}").stdout.decode().strip()
    return authority, result.stdout, oid


def _load_catalog(data: bytes) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    semantic_targets: set[tuple[str, tuple[str, ...]]] = set()
    for number, row in enumerate(_parse_jsonl(data, "Scenario-Katalog"), 1):
        scenario_id = row.get("scenario_id")
        if not isinstance(scenario_id, str) or not ID_RE.fullmatch(scenario_id):
            raise ContractError(f"Scenario-Katalog Zeile {number}: scenario_id ungueltig")
        if scenario_id in rows:
            raise ContractError(f"Scenario-Katalog: scenario_id {scenario_id!r} doppelt")
        missing = sorted(REQUIRED_SCENARIO_FIELDS - row.keys())
        if missing:
            raise ContractError(f"Scenario {scenario_id}: Pflichtfelder fehlen: {', '.join(missing)}")
        if row.get("schema_version") != 3:
            raise ContractError(f"Scenario {scenario_id}: schema_version muss exakt 3 sein")
        if row.get("scenario_sha256") != canonical_sha256(row, omit={"scenario_sha256"}):
            raise ContractError(f"Scenario {scenario_id}: scenario_sha256 stimmt nicht")
        axes = row.get("allowed_axes")
        if not isinstance(axes, list) or not all(isinstance(axis, str) for axis in axes):
            raise ContractError(f"Scenario {scenario_id}: allowed_axes ungueltig")
        feature_target = row.get("feature_target")
        symbols = row.get("allowed_symbol_ids")
        if not isinstance(feature_target, str) or not feature_target:
            raise ContractError(f"Scenario {scenario_id}: feature_target fehlt")
        if (not isinstance(symbols, list)
            or not all(isinstance(symbol, str) and symbol for symbol in symbols)
            or len(symbols) != len(set(symbols))):
            raise ContractError(f"Scenario {scenario_id}: allowed_symbol_ids ungueltig/doppelt")
        target = (str(row.get("feature_target", "")), tuple(sorted(axes)))
        if target in semantic_targets:
            raise ContractError(f"Scenario-Katalog: semantisches Ziel doppelt: {target}")
        semantic_targets.add(target)
        rows[scenario_id] = row
    return rows


def _validate_contract_bindings(row: dict[str, Any], contract: dict[str, Any]) -> None:
    for field in ("run_id", "snapshot_id", "audited_commit", "tooling_commit"):
        if row.get(field) != contract.get(field):
            raise ContractError(f"Scenario {row.get('scenario_id')}: {field} weicht vom Auditvertrag ab")


def _feature_and_symbol_sets(
    feature_data: bytes, symbol_data: bytes,
) -> tuple[set[str], dict[str, set[str]]]:
    features: set[str] = set()
    for number, row in enumerate(_parse_jsonl(feature_data, "Feature-Universum"), 1):
        feature_id, path_id = row.get("feature_id"), row.get("path_id")
        if not isinstance(feature_id, str) or not isinstance(path_id, str) or not feature_id or not path_id:
            raise ContractError(f"Feature-Universum Zeile {number}: ID/Pfad fehlt")
        key = f"{feature_id}/{path_id}"
        if key in features:
            raise ContractError(f"Feature-Universum: {key!r} doppelt")
        features.add(key)
    symbols: dict[str, set[str]] = {}
    for number, row in enumerate(_parse_jsonl(symbol_data, "Symbol-Universum", allow_empty=True), 1):
        symbol_id, feature_paths = row.get("symbol_id"), row.get("feature_paths")
        if not isinstance(symbol_id, str) or not symbol_id:
            raise ContractError(f"Symbol-Universum Zeile {number}: symbol_id fehlt")
        if symbol_id in symbols:
            raise ContractError(f"Symbol-Universum: {symbol_id!r} doppelt")
        if not isinstance(feature_paths, list) or not all(isinstance(item, str) for item in feature_paths):
            raise ContractError(f"Symbol-Universum Zeile {number}: feature_paths ungueltig")
        if len(feature_paths) != len(set(feature_paths)) or not set(feature_paths).issubset(features):
            raise ContractError(f"Symbol-Universum Zeile {number}: fremde/doppelte Featurepfade")
        symbols[symbol_id] = set(feature_paths)
    return features, symbols


def _validate_target_sets(row: dict[str, Any], features: set[str], symbols: dict[str, set[str]]) -> None:
    target = row.get("feature_target")
    if target not in features:
        raise ContractError(f"Scenario {row.get('scenario_id')}: fremdes Featuretarget")
    values = row.get("allowed_symbol_ids")
    if not isinstance(values, list) or not all(isinstance(item, str) and item for item in values):
        raise ContractError(f"Scenario {row.get('scenario_id')}: allowed_symbol_ids fehlt/ungueltig")
    if len(values) != len(set(values)):
        raise ContractError(f"Scenario {row.get('scenario_id')}: allowed_symbol_ids doppelt")
    for symbol in values:
        if symbol not in symbols:
            raise ContractError(f"Scenario {row.get('scenario_id')}: fremdes Symbol {symbol}")
        if target not in symbols[symbol]:
            raise ContractError(f"Symbol {symbol} ist nicht an Featuretarget {target} gebunden")
    if values:
        raise ContractError("Symbol-Runtimeachse braucht trusted externen Observer; Produktintrospektion reicht nicht")


def _validate_catalog_exact_set(
    catalog: dict[str, dict[str, Any]], features: set[str], symbols: dict[str, set[str]],
) -> None:
    catalog_features = {row.get("feature_target") for row in catalog.values()}
    catalog_symbols = {
        symbol
        for row in catalog.values()
        for symbol in (row.get("allowed_symbol_ids") if isinstance(row.get("allowed_symbol_ids"), list) else [])
    }
    if catalog_features != features:
        raise ContractError(
            f"Scenario-Katalog/Feature-Universum keine Exact-Set-Gleichheit: "
            f"fehlend={sorted(features - catalog_features)} extra={sorted(catalog_features - features, key=str)}"
        )
    if catalog_symbols != set(symbols):
        raise ContractError(
            f"Scenario-Katalog/Symbol-Universum keine Exact-Set-Gleichheit: "
            f"fehlend={sorted(set(symbols) - catalog_symbols)} extra={sorted(catalog_symbols - set(symbols))}"
        )


def _validate_executor_and_dependencies(
    executor_data: bytes, dependency_data: bytes, row: dict[str, Any],
) -> tuple[dict[str, dict[str, str]], dict[str, Any]]:
    executors = _parse_json(executor_data, "Executor-Manifest")
    normalized: dict[str, dict[str, str]] = {}
    for name, item in executors.items():
        if not isinstance(name, str) or not isinstance(item, dict):
            raise ContractError("Executor-Manifest ungueltig")
        if name not in ALLOWED_EXECUTORS:
            raise ContractError(f"Executor {name}: nicht in harter Allowlist")
        path = Path(str(item.get("path", ""))).resolve()
        expected = item.get("sha256")
        if not path.is_file() or not isinstance(expected, str) or not HASH_RE.fullmatch(expected) or _sha(path) != expected:
            raise ContractError(f"Executor {name}: Pfad/Hash stimmt nicht")
        if name == "python" and (path != Path(sys.executable).resolve() or item.get("version") != sys.version):
            raise ContractError("Python-Executor/Version weicht vom laufenden Runner ab")
        normalized[name] = {"path": str(path), "sha256": expected, "version": str(item.get("version", ""))}
    dependencies = _parse_json(dependency_data, "Dependency-Manifest")
    if dependencies.get("schema_version") != 1:
        raise ContractError("Dependency-Manifest.schema_version muss exakt 1 sein")
    if dependencies.get("python_version") != sys.version:
        raise ContractError("Dependency-Manifest: python_version stimmt nicht")
    module_rows = dependencies.get("modules")
    if not isinstance(module_rows, list):
        raise ContractError("Dependency-Manifest: modules muss Liste sein")
    modules: dict[str, dict[str, Any]] = {}
    for item in module_rows:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or item["name"] in modules:
            raise ContractError("Dependency-Manifest: Modul fehlt/doppelt")
        try:
            actual_version = importlib.metadata.version(item["name"])
        except importlib.metadata.PackageNotFoundError as exc:
            raise ContractError(f"Dependency-Modul fehlt: {item['name']}") from exc
        if item.get("version") != actual_version:
            raise ContractError(f"Dependency-Version stimmt nicht: {item['name']}")
        files = item.get("files")
        if not isinstance(files, list) or not files:
            raise ContractError(f"Dependency-Modul {item['name']}: gehashte files fehlen")
        seen_files: set[str] = set()
        for file_record in files:
            if not isinstance(file_record, dict):
                raise ContractError(f"Dependency-Modul {item['name']}: file-Record ungueltig")
            path = Path(str(file_record.get("path", ""))).resolve()
            expected = file_record.get("sha256")
            key = str(path).casefold()
            if (
                key in seen_files or not path.is_file() or not isinstance(expected, str)
                or not HASH_RE.fullmatch(expected) or _sha(path) != expected
            ):
                raise ContractError(f"Dependency-Modul {item['name']}: file Pfad/Hash falsch oder doppelt")
            seen_files.add(key)
        modules[item["name"]] = item
    required = row.get("required_modules")
    if not isinstance(required, list) or len(required) != len(set(required)) or not all(isinstance(x, str) for x in required):
        raise ContractError("Scenario.required_modules ungueltig")
    if not set(required).issubset(modules):
        raise ContractError("Scenario.required_modules fehlen im Dependency-Manifest")
    stdlib = dependencies.get("stdlib_modules")
    required_stdlib = row.get("required_stdlib_modules")
    if (not isinstance(stdlib, list) or len(stdlib) != len(set(stdlib))
        or not all(isinstance(item, str) and item for item in stdlib)):
        raise ContractError("Dependency-Manifest.stdlib_modules ungueltig")
    if (not isinstance(required_stdlib, list) or len(required_stdlib) != len(set(required_stdlib))
        or not all(isinstance(item, str) and item for item in required_stdlib)):
        raise ContractError("Scenario.required_stdlib_modules ungueltig")
    if set(required_stdlib) != set(stdlib):
        raise ContractError("Scenario/Manifest-Stdlibmodule keine Exact-Set-Gleichheit")
    return normalized, dependencies


def _materialize_commit(repo: Path, commit: str, destination: Path) -> dict[str, Any]:
    if _git(repo, "cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode != 0:
        raise ContractError(f"Commit existiert nicht: {commit}")
    result = _git(repo, "ls-tree", "-rz", "--full-tree", commit)
    records = result.stdout.split(b"\0")
    seen_casefold: set[str] = set()
    manifest: list[dict[str, Any]] = []
    destination.mkdir(parents=True)
    for raw in records:
        if not raw:
            continue
        try:
            meta, raw_path = raw.split(b"\t", 1)
            mode, kind, oid = meta.decode("ascii").split(" ")
            path_text = raw_path.decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise ContractError("Git-Tree-Record ungueltig") from exc
        if kind != "blob" or mode == "120000":
            raise ContractError(f"Git-Tree enthaelt nicht materialisierbare Einheit: {path_text} ({mode}/{kind})")
        folded = path_text.casefold()
        if folded in seen_casefold:
            raise ContractError(f"Git-Tree hat Case-Kollision: {path_text}")
        seen_casefold.add(folded)
        target = _contained(destination, destination / path_text, "Git-Tree-Pfad")
        target.parent.mkdir(parents=True, exist_ok=True)
        data = _git(repo, "cat-file", "blob", oid).stdout
        target.write_bytes(data)
        if target.read_bytes() != data:
            raise ContractError(f"Blob-Materialisierung nicht bytegleich: {path_text}")
        manifest.append({"path": path_text, "mode": mode, "git_blob": oid, "sha256": _sha_bytes(data), "bytes": len(data)})
    basis = canonical_sha256(sorted(manifest, key=lambda item: item["path"]))
    return {"commit": commit, "files": len(manifest), "manifest_sha256": basis, "method": "git-cat-file"}


def _git_manifest_summary(repo: Path, commit: str) -> dict[str, Any]:
    """Recompute materialization receipt directly from replacement-free Git objects."""
    if not isinstance(commit, str) or not SHA_RE.fullmatch(commit):
        raise ContractError("Git-Manifest Commit ungueltig")
    if _git(repo, "cat-file", "-e", f"{commit}^{{commit}}", check=False).returncode != 0:
        raise ContractError(f"Git-Manifest Commit fehlt: {commit}")
    result = _git(repo, "ls-tree", "-rz", "--full-tree", commit)
    seen_casefold: set[str] = set()
    tree_rows: list[tuple[str, str, str]] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        try:
            meta, raw_path = raw.split(b"\t", 1)
            mode, kind, oid = meta.decode("ascii").split(" ")
            path_text = raw_path.decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise ContractError("Git-Manifest Tree-Record ungueltig") from exc
        if kind != "blob" or mode == "120000":
            raise ContractError(f"Git-Manifest nicht materialisierbar: {path_text} ({mode}/{kind})")
        folded = path_text.casefold()
        if folded in seen_casefold:
            raise ContractError(f"Git-Manifest Case-Kollision: {path_text}")
        seen_casefold.add(folded)
        tree_rows.append((path_text, mode, oid))
    batch_input = b"".join(oid.encode("ascii") + b"\n" for _, _, oid in tree_rows)
    batch_output = _git(repo, "cat-file", "--batch", input_data=batch_input).stdout
    offset = 0
    manifest: list[dict[str, Any]] = []
    for path_text, mode, oid in tree_rows:
        header_end = batch_output.find(b"\n", offset)
        if header_end < 0:
            raise ContractError("Git-Manifest Batch-Header fehlt")
        try:
            returned_oid, kind, size_text = batch_output[offset:header_end].decode("ascii").split(" ")
            size = int(size_text)
        except (ValueError, UnicodeError) as exc:
            raise ContractError("Git-Manifest Batch-Header ungueltig") from exc
        data_start = header_end + 1
        data_end = data_start + size
        if (
            returned_oid != oid or kind != "blob" or size < 0
            or data_end >= len(batch_output) or batch_output[data_end:data_end + 1] != b"\n"
        ):
            raise ContractError("Git-Manifest Batch-Blob ungueltig")
        data = batch_output[data_start:data_end]
        offset = data_end + 1
        manifest.append({
            "path": path_text, "mode": mode, "git_blob": oid,
            "sha256": _sha_bytes(data), "bytes": len(data),
        })
    if offset != len(batch_output):
        raise ContractError("Git-Manifest Batch hat unerwartete Restbytes")
    return {
        "commit": commit, "files": len(manifest),
        "manifest_sha256": canonical_sha256(sorted(manifest, key=lambda item: item["path"])),
        "method": "git-cat-file",
    }


def _verify_tool_identity(repo: Path, tooling_commit: str) -> str:
    result = _git(repo, "show", f"{tooling_commit}:tools/audit_runtime_evidence.py", check=False)
    if result.returncode != 0:
        raise ContractError("Runner fehlt im tooling_commit")
    current = Path(__file__).read_bytes()
    if result.stdout != current:
        raise ContractError("ausgefuehrter Runner stimmt nicht mit tooling_commit ueberein")
    return _sha_bytes(result.stdout)


def _validate_command(command: object, label: str, fallback_timeout: float, expected_root: str) -> tuple[dict[str, Any], float]:
    if not isinstance(command, dict):
        raise ContractError(f"{label}: Objekt fehlt")
    if command.get("root") != expected_root:
        raise ContractError(f"{label}.root muss {expected_root} sein")
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) and arg for arg in argv):
        raise ContractError(f"{label}.argv fehlt/ungueltig")
    if not isinstance(command.get("cwd"), str) or not command["cwd"]:
        raise ContractError(f"{label}.cwd fehlt")
    timeout = command.get("timeout_seconds", fallback_timeout)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0 or timeout > 86400:
        raise ContractError(f"{label}.timeout_seconds ungueltig")
    return command, float(timeout)


def _expand_arg(
    arg: str, *, root: Path, run_dir: Path, inputs: dict[str, Path], label: str,
    special_paths: dict[str, Path] | None = None,
) -> str:
    expanded = arg.replace("{run_dir}", str(run_dir))
    for name, path in (special_paths or {}).items():
        expanded = expanded.replace(f"{{{name}}}", str(path))
    for name, path in inputs.items():
        expanded = expanded.replace(f"{{input:{name}}}", str(path))
    if "{" in expanded or "}" in expanded:
        raise ContractError(f"{label}: unbekannter Placeholder")
    pathish = Path(expanded)
    if ".." in pathish.parts:
        raise ContractError(f"{label}: Pfad-Escape verboten")
    if pathish.is_absolute():
        resolved = pathish.resolve()
        allowed = [root.resolve(), run_dir.resolve(), *[path.resolve() for path in inputs.values()],
                   *[path.resolve() for path in (special_paths or {}).values()]]
        if not any(resolved == base or (base.is_dir() and _is_relative_to(resolved, base)) for base in allowed):
            raise ContractError(f"{label}: absoluter Pfad ausserhalb erlaubter Wurzeln")
    return expanded


def _resolve_command(
    command: dict[str, Any], *, root: Path, run_dir: Path, inputs: dict[str, Path],
    executors: dict[str, dict[str, str]], label: str, commit: str,
    special_paths: dict[str, Path] | None = None,
) -> tuple[list[str], Path, dict[str, Any]]:
    cwd = _contained(root, root / command["cwd"], f"{label}.cwd")
    if not cwd.is_dir():
        raise ContractError(f"{label}.cwd fehlt")
    executable_key = command["argv"][0].lower().removesuffix(".exe")
    if executable_key not in executors:
        raise ContractError(f"{label}: Executable {command['argv'][0]!r} ist nicht erlaubt")
    resolved = [executors[executable_key]["path"]]
    if executable_key == "python":
        resolved.extend(["-I", "-S"])
    for index, arg in enumerate(command["argv"][1:], 1):
        resolved.append(_expand_arg(arg, root=root, run_dir=run_dir, inputs=inputs,
                                    special_paths=special_paths, label=f"{label}.argv[{index}]"))
    if executable_key == "python":
        if len(resolved) < 4 or Path(resolved[3]).suffix.lower() != ".py":
            raise ContractError(f"{label}: Python braucht gebundenes .py-Script")
        source = Path(resolved[3])
        source = source if source.is_absolute() else cwd / source
    else:
        source = Path(resolved[0])
    source = _contained(root, source, f"{label}.source")
    if not source.is_file():
        raise ContractError(f"{label}: Command-Quelle fehlt")
    relative = source.relative_to(root).as_posix()
    blob = _git(root, "hash-object", "--no-filters", str(source)).stdout.decode().strip()
    provenance = {
        "commit": commit,
        "executor": executors[executable_key],
        "source": {"path": relative, "git_blob": blob, "sha256": _sha(source), "commit": commit},
    }
    return resolved, cwd, provenance


def _sanitized_environment(root: Path, run_dir: Path) -> dict[str, str]:
    keep = ("SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP")
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env.update({
        "PB_AUDIT_ROOT": str(root), "PB_AUDIT_RUN_DIR": str(run_dir),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1", "PYTHONSAFEPATH": "1",
        "PATH": str(Path(sys.executable).resolve().parent),
    })
    return env


def _windows_kernel32():
    import ctypes

    return ctypes.WinDLL("kernel32", use_last_error=True)


def _windows_close_handle(kernel32, handle: int, label: str) -> None:
    import ctypes
    from ctypes import wintypes

    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    if not close_handle(handle):
        raise ContractError(f"{label} nicht schliessbar: {ctypes.get_last_error()}")


def _report_base_cleanup_error(primary_error: BaseException, message: str) -> None:
    try:
        primary_error._pb_audit_cleanup_error = message
    except BaseException:
        pass
    try:
        print(f"FEHLER: {message}", file=sys.stderr)
    except BaseException:
        pass


def _windows_create_kill_job() -> int:
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = _windows_kernel32()
    create_job = kernel32.CreateJobObjectW
    create_job.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    create_job.restype = wintypes.HANDLE
    set_information = kernel32.SetInformationJobObject
    set_information.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    set_information.restype = wintypes.BOOL
    job = create_job(None, None)
    if not job:
        raise ContractError(f"Windows Job Object nicht erstellbar: {ctypes.get_last_error()}")
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not set_information(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        error = ctypes.get_last_error()
        try:
            _windows_close_handle(kernel32, job, "Windows Job Object nach Konfigurationsfehler")
        except ContractError as close_error:
            raise ContractError(
                f"Windows Job Object nicht konfigurierbar: {error}; Cleanup fehlgeschlagen: {close_error}"
            ) from close_error
        raise ContractError(f"Windows Job Object nicht konfigurierbar: {error}")
    return int(job)


def _windows_assign_process_to_job(job: int, process: subprocess.Popen[bytes]) -> None:
    import ctypes
    from ctypes import wintypes

    assign = _windows_kernel32().AssignProcessToJobObject
    assign.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    assign.restype = wintypes.BOOL
    if not assign(job, int(process._handle)):
        raise ContractError(f"Windows-Prozess nicht an Job Object bindbar: {ctypes.get_last_error()}")


def _windows_resume_suspended_process(pid: int) -> None:
    import ctypes
    from ctypes import wintypes

    class THREADENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD), ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", wintypes.LONG), ("tpDeltaPri", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
        ]

    kernel32 = _windows_kernel32()
    create_snapshot = kernel32.CreateToolhelp32Snapshot
    create_snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    create_snapshot.restype = wintypes.HANDLE
    thread_first = kernel32.Thread32First
    thread_first.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
    thread_first.restype = wintypes.BOOL
    thread_next = kernel32.Thread32Next
    thread_next.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
    thread_next.restype = wintypes.BOOL
    open_thread = kernel32.OpenThread
    open_thread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_thread.restype = wintypes.HANDLE
    resume_thread = kernel32.ResumeThread
    resume_thread.argtypes = [wintypes.HANDLE]
    resume_thread.restype = wintypes.DWORD
    snapshot = create_snapshot(0x00000004, 0)  # TH32CS_SNAPTHREAD
    if snapshot == wintypes.HANDLE(-1).value:
        raise ContractError(f"Windows-Threadsnapshot fehlgeschlagen: {ctypes.get_last_error()}")
    resumed = 0
    operation_error: BaseException | None = None
    try:
        entry = THREADENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        ok = thread_first(snapshot, ctypes.byref(entry))
        while ok:
            if int(entry.th32OwnerProcessID) == pid:
                thread = open_thread(0x0002, False, entry.th32ThreadID)  # THREAD_SUSPEND_RESUME
                if not thread:
                    raise ContractError(f"Windows-Startthread nicht oeffenbar: {ctypes.get_last_error()}")
                thread_error: BaseException | None = None
                try:
                    if resume_thread(thread) == 0xFFFFFFFF:
                        raise ContractError(f"Windows-Startthread nicht fortsetzbar: {ctypes.get_last_error()}")
                    resumed += 1
                except BaseException as exc:
                    thread_error = exc
                try:
                    _windows_close_handle(kernel32, thread, "Windows-Startthread-Handle")
                except ContractError as close_error:
                    if thread_error is None:
                        thread_error = close_error
                    elif not isinstance(thread_error, Exception):
                        _report_base_cleanup_error(
                            thread_error, f"Thread-Cleanup fehlgeschlagen: {close_error}"
                        )
                    else:
                        thread_error = ContractError(
                            f"{thread_error}; Thread-Cleanup fehlgeschlagen: {close_error}"
                        )
                if thread_error is not None:
                    raise thread_error
            ok = thread_next(snapshot, ctypes.byref(entry))
    except BaseException as exc:
        operation_error = exc
    try:
        _windows_close_handle(kernel32, snapshot, "Windows-Threadsnapshot-Handle")
    except ContractError as close_error:
        if operation_error is None:
            operation_error = close_error
        elif not isinstance(operation_error, Exception):
            _report_base_cleanup_error(
                operation_error, f"Snapshot-Cleanup fehlgeschlagen: {close_error}"
            )
        else:
            operation_error = ContractError(
                f"{operation_error}; Snapshot-Cleanup fehlgeschlagen: {close_error}"
            )
    if operation_error is not None:
        raise operation_error
    if resumed != 1:
        raise ContractError(f"Windows-Startthread-Anzahl ungueltig: {resumed}")


def _windows_job_active_processes(job: int) -> int:
    import ctypes
    from ctypes import wintypes

    class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong),
            ("ThisPeriodTotalUserTime", ctypes.c_longlong),
            ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
            ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    query = _windows_kernel32().QueryInformationJobObject
    query.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
    query.restype = wintypes.BOOL
    info = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()
    if not query(job, 1, ctypes.byref(info), ctypes.sizeof(info), None):
        raise ContractError(f"Windows Job Object nicht attestierbar: {ctypes.get_last_error()}")
    return int(info.ActiveProcesses)


def _windows_terminate_job(job: int) -> None:
    import ctypes
    from ctypes import wintypes

    terminate = _windows_kernel32().TerminateJobObject
    terminate.argtypes = [wintypes.HANDLE, wintypes.UINT]
    terminate.restype = wintypes.BOOL
    if not terminate(job, 1) and _windows_job_active_processes(job) != 0:
        raise ContractError(f"Windows Job Object nicht terminierbar: {ctypes.get_last_error()}")


def _windows_wait_job_empty(job: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while _windows_job_active_processes(job) != 0:
        if time.monotonic() >= deadline:
            raise ContractError("Windows Job Object bleibt nach Timeout aktiv")
        time.sleep(0.01)


def _windows_close_job(job: int) -> None:
    _windows_close_handle(_windows_kernel32(), job, "Windows Job Object")


def _kill_process_tree(process: subprocess.Popen[bytes]) -> None:
    initial_status = process.poll()
    if os.name != "nt" and initial_status is not None:
        return
    if os.name == "nt" and hasattr(process, "_pb_audit_job_handle"):
        job = int(process._pb_audit_job_handle)
        _windows_terminate_job(job)
        _windows_wait_job_empty(job)
    elif os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, check=False, shell=False,
        )
        if result.returncode != 0:
            error = result.stderr.decode(errors="replace").strip() or result.stdout.decode(errors="replace").strip()
            missing_process = any(
                marker in error.casefold()
                for marker in ("not found", "nicht gefunden", "no running instance")
            )
            if not (missing_process and process.poll() is not None):
                raise ContractError(f"Timeout: Prozessbaum-Kill nicht attestierbar: {error}")
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        raise ContractError("Prozessbaum liess sich nach Timeout nicht beenden")


def _execute(
    argv: list[str], *, cwd: Path, timeout: float, environment: dict[str, str],
    label: str,
) -> tuple[int, bytes, bytes, int, int, int]:
    job: int | None = None
    flags = 0
    if os.name == "nt":
        job = _windows_create_kill_job()
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000004  # CREATE_SUSPENDED
    start_ns = time.time_ns()
    primary_error: BaseException | None = None
    try:
        process = subprocess.Popen(
            argv, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
            creationflags=flags, start_new_session=(os.name != "nt"),
        )
        if job is not None:
            try:
                _windows_assign_process_to_job(job, process)
                process._pb_audit_job_handle = job
                _windows_resume_suspended_process(process.pid)
            except Exception as setup_error:
                cleanup_errors: list[str] = []
                try:
                    process.kill()
                except OSError as exc:
                    cleanup_errors.append(f"kill: {exc}")
                try:
                    process.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    cleanup_errors.append(f"wait: {exc}")
                if cleanup_errors:
                    raise ContractError(
                        f"{setup_error}; Setup-Cleanup fehlgeschlagen: {'; '.join(cleanup_errors)}"
                    ) from setup_error
                raise
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _kill_process_tree(process)
            raise ContractError(f"{label}: Timeout nach {timeout:g}s") from exc
        if job is not None and _windows_job_active_processes(job) != 0:
            _windows_terminate_job(job)
            _windows_wait_job_empty(job)
            raise ContractError(f"{label}: Command hinterliess aktive Kindprozesse")
        end_ns = time.time_ns()
        return process.returncode, stdout, stderr, process.pid, start_ns, end_ns
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        if job is not None:
            try:
                _windows_close_job(job)
            except ContractError as close_error:
                if primary_error is None:
                    raise
                if not isinstance(primary_error, Exception):
                    _report_base_cleanup_error(
                        primary_error, f"Job-Cleanup fehlgeschlagen: {close_error}"
                    )
                else:
                    raise ContractError(
                        f"{primary_error}; Job-Cleanup fehlgeschlagen: {close_error}"
                    ) from primary_error


def _snapshot_files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha(path)
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def _assert_snapshot(root: Path, expected: dict[str, str], label: str) -> None:
    actual = _snapshot_files(root)
    if actual != expected:
        raise ContractError(f"{label} hat Runner-Evidenz veraendert")


def _assert_sources_unchanged(sources: dict[Path, str]) -> None:
    for path, expected in sources.items():
        if not path.is_file() or _sha(path) != expected:
            raise ContractError(f"TOCTOU: externe Quelle geaendert: {path.name}")


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        if os.name == "nt":
            return
        raise
    try:
        try:
            os.fsync(descriptor)
        except OSError:
            if os.name != "nt":
                raise
    finally:
        os.close(descriptor)


def _durable_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)


def _fsync_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            try:
                with path.open("r+b") as handle:
                    handle.flush()
                    os.fsync(handle.fileno())
            except OSError:
                if os.name != "nt":
                    raise
    directories = [path for path in root.rglob("*") if path.is_dir()]
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        _fsync_directory(directory)
    _fsync_directory(root)


def _write(path: Path, data: bytes) -> dict[str, Any]:
    _durable_write(path, data)
    return {"bytes": len(data), "sha256": _sha_bytes(data)}


def _validate_harness_report_payload(
    report: dict[str, Any], descriptor_bytes: bytes,
    dependencies: dict[str, Any], row: dict[str, Any],
) -> dict[str, Any]:
    if report.get("schema_version") != 1 or report.get("descriptor_sha256") != _sha_bytes(descriptor_bytes):
        raise ContractError("harness_report Schema/Descriptor-Bindung falsch")
    if report.get("target_exit_code") != 0:
        raise ContractError(f"Audited Target Exit {report.get('target_exit_code')}")
    loaded = report.get("loaded_modules")
    if not isinstance(loaded, list):
        raise ContractError("harness_report.loaded_modules fehlt")
    expected_stdlib = set(row["required_stdlib_modules"])
    external = {item["name"]: item for item in dependencies["modules"]}
    expected_external = set(row["required_modules"])
    actual_stdlib: set[str] = set()
    actual_external: set[str] = set()
    seen: set[str] = set()
    stdlib_root = Path(os.__file__).resolve().parent
    for item in loaded:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or item["name"] in seen:
            raise ContractError("harness_report Modul fehlt/doppelt")
        seen.add(item["name"])
        origin = Path(str(item.get("origin", ""))).resolve()
        if not origin.is_file() or item.get("sha256") != _sha(origin):
            raise ContractError(f"Geladenes Modul Pfad/Hash falsch: {item['name']}")
        top = item["name"].split(".", 1)[0]
        if _is_relative_to(origin, stdlib_root):
            actual_stdlib.add(top)
        elif top in external:
            allowed_files = {str(Path(record["path"]).resolve()).casefold() for record in external[top]["files"]}
            if str(origin).casefold() not in allowed_files:
                raise ContractError(f"Geladenes Dependency-Modul unpinned: {item['name']}")
            actual_external.add(top)
        else:
            raise ContractError(f"Geladenes Modul nicht in Policy: {item['name']}")
    if actual_stdlib != expected_stdlib or actual_external != expected_external:
        raise ContractError(
            f"Geladene Module keine Exact-Set-Gleichheit: stdlib={sorted(actual_stdlib)} deps={sorted(actual_external)}"
        )
    return report


def _validate_harness_report(
    path: Path, descriptor_bytes: bytes, dependencies: dict[str, Any], row: dict[str, Any],
) -> dict[str, Any]:
    if not path.is_file():
        raise ContractError("Trusted Harness hat keinen harness_report erzeugt")
    report = _parse_json(path.read_bytes(), "harness_report")
    return _validate_harness_report_payload(report, descriptor_bytes, dependencies, row)


def _validated_projection_list(
    receipt: dict[str, Any], field: str, *, singleton: bool = False,
) -> list[str]:
    value = receipt.get(field)
    if (
        not isinstance(value, list)
        or (singleton and len(value) != 1)
        or any(not isinstance(item, str) or not item.strip() or item != item.strip() for item in value)
        or value != sorted(set(value))
    ):
        suffix = " und genau einen Wert" if singleton else ""
        raise ContractError(f"Runtime-Receipt {field} muss sortierte eindeutige Stringliste{suffix} sein")
    return value


def _run_ref_file(run_dir: Path, ref: object, label: str) -> Path:
    prefix = f"runs/{run_dir.name}/"
    if not isinstance(ref, str) or not ref.startswith(prefix):
        raise ContractError(f"{label}: Run-Ref falsch")
    relative = ref[len(prefix):]
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ContractError(f"{label}: Run-Ref ungueltig")
    path = _contained(run_dir, run_dir / relative, label)
    if not path.is_file():
        raise ContractError(f"{label}: Datei fehlt")
    return path


def _file_binding(
    run_dir: Path, record: object, fields: set[str], label: str,
) -> tuple[Path, bytes]:
    if not isinstance(record, dict) or set(record) != fields:
        raise ContractError(f"{label}: Exact-Fields falsch")
    path = _run_ref_file(run_dir, record.get("ref"), label)
    data = path.read_bytes()
    if (
        type(record.get("bytes")) is not int
        or record["bytes"] != len(data)
        or not isinstance(record.get("sha256"), str)
        or not HASH_RE.fullmatch(record["sha256"])
        or record["sha256"] != _sha_bytes(data)
    ):
        raise ContractError(f"{label}: Bytes/SHA falsch")
    return path, data


def _provenance_shape(
    value: object, commit: str, label: str, *, repo: Path,
    expected_executor: dict[str, str], expected_source_path: str,
) -> None:
    if not isinstance(value, dict) or set(value) != {"commit", "executor", "source"}:
        raise ContractError(f"{label}: Provenienzfelder falsch")
    if value.get("commit") != commit:
        raise ContractError(f"{label}: Commitbindung falsch")
    executor, source = value.get("executor"), value.get("source")
    if not isinstance(executor, dict) or set(executor) != {"path", "sha256", "version"}:
        raise ContractError(f"{label}: Executor-Provenienz falsch")
    if executor != expected_executor:
        raise ContractError(f"{label}: Executor weicht vom versiegelten Manifest ab")
    executor_path = Path(executor["path"]).resolve()
    if (
        executor_path != Path(sys.executable).resolve() or not executor_path.is_file()
        or _sha(executor_path) != executor["sha256"] or executor["version"] != sys.version
    ):
        raise ContractError(f"{label}: versiegelte Executor-Runtimeidentitaet falsch")
    if not isinstance(source, dict) or set(source) != {"path", "git_blob", "sha256", "commit"}:
        raise ContractError(f"{label}: Source-Provenienz falsch")
    source_path = source.get("path")
    if not isinstance(source_path, str):
        raise ContractError(f"{label}: Source-Pfad fehlt")
    posix_path = PurePosixPath(source_path)
    if (
        source_path != expected_source_path or "\\" in source_path or ":" in source_path
        or posix_path.is_absolute() or any(part in {"", ".", ".."} for part in posix_path.parts)
    ):
        raise ContractError(f"{label}: Source-Pfad ungueltig/falsch")
    if (
        source.get("commit") != commit
        or not HASH_RE.fullmatch(str(source.get("sha256", "")))
        or not SHA_RE.fullmatch(str(source.get("git_blob", "")))
    ):
        raise ContractError(f"{label}: Source-Bindung falsch")
    blob = _git(repo, "rev-parse", f"{commit}:{source_path}", check=False)
    raw = _git(repo, "show", f"{commit}:{source_path}", check=False)
    if (
        blob.returncode != 0 or raw.returncode != 0
        or blob.stdout.decode().strip() != source["git_blob"]
        or _sha_bytes(raw.stdout) != source["sha256"]
    ):
        raise ContractError(f"{label}: replacement-freie Source-Gitbytes falsch")


def _validate_receipt_for_projection(
    receipt: dict[str, Any], receipt_bytes: bytes, run_dir: Path, *,
    repo_root: Path, expected_contract_sha256: str, expected_authority_commit: str,
) -> None:
    keys = set(receipt)
    if not RICH_RECEIPT_FIELDS.issubset(keys) or not keys.issubset(
        RICH_RECEIPT_FIELDS | RICH_RECEIPT_OPTIONAL_FIELDS
    ):
        raise ContractError("Rich Receipt Exact-Fields falsch")
    if receipt_bytes != _canonical_bytes(receipt) + b"\n":
        raise ContractError("Runtime-Receipt ist nicht kanonisch serialisiert")
    runtime_run_id = receipt.get("runtime_run_id")
    if not isinstance(runtime_run_id, str) or not ID_RE.fullmatch(runtime_run_id):
        raise ContractError("Runtime-Receipt runtime_run_id ungueltig")
    if run_dir.name != runtime_run_id or run_dir.is_symlink() or not run_dir.is_dir():
        raise ContractError("Runtime-Receipt Run-Verzeichnisbindung falsch")
    if any(path.is_symlink() for path in run_dir.rglob("*")):
        raise ContractError("Runtime-Receipt Run-Verzeichnis enthaelt Symlink")
    for field in ("plan_id", "run_id", "snapshot_id", "scenario_id", "timestamp"):
        value = receipt.get(field)
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            raise ContractError(f"Runtime-Receipt {field} fehlt/ungueltig")
    for field in ("audited_commit", "tooling_commit"):
        value = receipt.get(field)
        if not isinstance(value, str) or not SHA_RE.fullmatch(value):
            raise ContractError(f"Runtime-Receipt {field} muss voller SHA sein")
    try:
        timestamp = datetime.fromisoformat(receipt["timestamp"])
    except ValueError as exc:
        raise ContractError("Runtime-Receipt timestamp ungueltig") from exc
    if timestamp.tzinfo is None:
        raise ContractError("Runtime-Receipt timestamp braucht Zeitzone")
    _validated_projection_list(receipt, "covered_feature_paths", singleton=True)
    symbols = _validated_projection_list(receipt, "covered_symbol_ids")
    if symbols:
        raise ContractError(
            "trusted externer Symbol-Observer ist nicht implementiert; plural Symbols sind nur Adapterkapazitaet"
        )
    axes = _validated_projection_list(receipt, "covered_axes")
    if not set(axes).issubset(KNOWN_AXES):
        raise ContractError("Runtime-Receipt covered_axes enthaelt unbekannte Achse")
    expected_evidence_id = canonical_evidence_id(receipt)
    if receipt.get("evidence_id") != expected_evidence_id:
        raise ContractError("Runtime-Receipt evidence_id ist nicht kanonisch")

    forced = sorted({"error", "cancel", "retry"} & set(axes))
    expected_optional: set[str] = set()
    if forced:
        expected_optional.add("forced_state")
    surfaces = sorted(set(SURFACE_OBSERVERS) & set(axes))
    if surfaces:
        expected_optional.add("observed_surfaces")
    if "restart_safe" in axes:
        expected_optional.update({"restart", "reopen"})
    if keys - RICH_RECEIPT_FIELDS != expected_optional:
        raise ContractError("Rich Receipt optionale Zustandsfelder falsch")
    if forced and (len(forced) != 1 or receipt.get("forced_state") != forced[0]):
        raise ContractError("Rich Receipt forced_state falsch")
    if surfaces and receipt.get("observed_surfaces") != surfaces:
        raise ContractError("Rich Receipt observed_surfaces falsch")
    if "restart_safe" in axes and (receipt.get("restart") is not True or receipt.get("reopen") is not True):
        raise ContractError("Rich Receipt Restart/Reopen falsch")

    integrity = _snapshot_files(run_dir)
    integrity.pop("receipt.json", None)
    integrity.pop("projection.json", None)
    if receipt.get("final_integrity_sha256") != canonical_sha256(integrity):
        raise ContractError("Rich Receipt final_integrity_sha256 stimmt nicht")

    sealed_rows = receipt.get("sealed_contract_inputs")
    if not isinstance(sealed_rows, list):
        raise ContractError("Rich Receipt sealed_contract_inputs fehlt")
    sealed: dict[str, tuple[dict[str, Any], bytes]] = {}
    for item in sealed_rows:
        name = item.get("name") if isinstance(item, dict) else None
        fields = {"name", "ref", "sha256", "git_blob"} if name == "authority" else {"name", "ref", "sha256"}
        if (
            not isinstance(name, str) or name in sealed or set(item) != fields
            or not isinstance(item.get("sha256"), str) or not HASH_RE.fullmatch(item["sha256"])
        ):
            raise ContractError("Rich Receipt sealed_contract_inputs Record falsch/doppelt")
        path = _run_ref_file(run_dir, item.get("ref"), f"Sealed {name}")
        data = path.read_bytes()
        if _sha_bytes(data) != item["sha256"]:
            raise ContractError(f"Sealed {name}: SHA falsch")
        sealed[name] = (item, data)
    if set(sealed) != SEALED_INPUT_NAMES:
        raise ContractError("Rich Receipt sealed_contract_inputs Exact-Set falsch")

    audit_info = receipt.get("audit_contract")
    if not isinstance(audit_info, dict) or set(audit_info) != {"ref", "sha256", "contract_sha256"}:
        raise ContractError("Rich Receipt audit_contract Felder falsch")
    if audit_info.get("ref") != sealed["audit_contract"][0]["ref"] or audit_info.get("sha256") != sealed["audit_contract"][0]["sha256"]:
        raise ContractError("Rich Receipt audit_contract/Sealed-Bindung falsch")
    contract = _parse_json(sealed["audit_contract"][1], "Sealed Auditvertrag")
    if set(contract) != CONTRACT_FIELDS or contract.get("schema_version") != 1:
        raise ContractError("Sealed Auditvertrag Exact-Fields/schema_version falsch")
    contract_sha = canonical_sha256(contract, omit={"contract_sha256"})
    if contract.get("contract_sha256") != contract_sha or audit_info.get("contract_sha256") != contract_sha:
        raise ContractError("Sealed Auditvertrag Body-SHA falsch")
    for field in ("plan_id", "run_id", "snapshot_id", "audited_commit", "tooling_commit"):
        if contract.get(field) != receipt.get(field):
            raise ContractError(f"Rich Receipt Auditvertrag-Bindung falsch: {field}")
    contract_artifacts = contract.get("artifacts")
    if not isinstance(contract_artifacts, dict) or set(contract_artifacts) != GLOBAL_CONTRACT_ARTIFACTS:
        raise ContractError("Sealed Auditvertrag Artifact-Exact-Set falsch")
    for internal_name, artifact_key in CONTRACT_ARTIFACTS.items():
        descriptor = contract_artifacts.get(artifact_key)
        data = sealed[internal_name][1]
        if not isinstance(descriptor, dict) or set(descriptor) != {"artifact_id", "ref", "sha256", "bytes", "record_count"}:
            raise ContractError(f"Sealed Auditvertrag Descriptor falsch: {artifact_key}")
        digest = _sha_bytes(data)
        if (
            descriptor.get("artifact_id") != f"sha256:{digest}"
            or descriptor.get("sha256") != digest
            or type(descriptor.get("bytes")) is not int
            or descriptor["bytes"] != len(data)
            or type(descriptor.get("record_count")) is not int
            or descriptor["record_count"] != _descriptor_record_count(data, artifact_key)
        ):
            raise ContractError(f"Sealed Auditvertrag Descriptor-Bindung falsch: {artifact_key}")

    authority_info = receipt.get("authority")
    authority_fields = {
        "git_blob", "path", "authority_commit", "expected_authority_commit",
        "sha256", "policy", "expected_contract_sha256", "trust_boundary",
    }
    if not isinstance(authority_info, dict) or set(authority_info) != authority_fields:
        raise ContractError("Rich Receipt Authority Exact-Fields falsch")
    authority_record, authority_bytes = sealed["authority"]
    authority_policy = _parse_json(authority_bytes, "Sealed Authority")
    if authority_info.get("policy") != authority_policy or authority_info.get("sha256") != _sha_bytes(authority_bytes):
        raise ContractError("Rich Receipt Authority-Bytes/Policy falsch")
    if authority_info.get("git_blob") != authority_record.get("git_blob") or not SHA_RE.fullmatch(str(authority_info.get("git_blob", ""))):
        raise ContractError("Rich Receipt Authority-Gitblob falsch")
    if authority_info.get("path") != AUTHORITY_POLICY_PATH:
        raise ContractError("Rich Receipt Authority-Pfad falsch")
    authority_commit = authority_info.get("authority_commit")
    if (
        not isinstance(authority_commit, str) or not SHA_RE.fullmatch(authority_commit)
        or authority_info.get("expected_authority_commit") != authority_commit
        or authority_commit in {receipt["audited_commit"], receipt["tooling_commit"]}
    ):
        raise ContractError("Rich Receipt Authority-Commitbindung falsch")
    if set(authority_policy) != AUTHORITY_POLICY_FIELDS or authority_policy.get("schema_version") != 1:
        raise ContractError("Rich Receipt Authority-Policy Exact-Fields falsch")
    authority_bindings = {
        "audit_contract_sha256": contract_sha, "plan_id": receipt["plan_id"],
        "run_id": receipt["run_id"], "snapshot_id": receipt["snapshot_id"],
        "audited_commit": receipt["audited_commit"], "tooling_commit": receipt["tooling_commit"],
    }
    if any(authority_policy.get(field) != value for field, value in authority_bindings.items()):
        raise ContractError("Rich Receipt Authority-Policy Bindings falsch")
    if authority_info.get("expected_contract_sha256") != contract_sha:
        raise ContractError("Rich Receipt Authority Contract-Pin falsch")
    if authority_info.get("trust_boundary") != "trusted-external-authority-pin-required; compromised-external-pin-not-detected":
        raise ContractError("Rich Receipt Authority Trust-Boundary falsch")
    repo = repo_root.resolve()
    if not (repo / ".git").exists():
        raise ContractError("Projection-Trust repo_root ist kein Git-Worktree")
    if not HASH_RE.fullmatch(str(expected_contract_sha256)) or contract_sha != expected_contract_sha256:
        raise ContractError("Projection-Trust externer Contract-Pin falsch")
    if not SHA_RE.fullmatch(str(expected_authority_commit)) or authority_commit != expected_authority_commit:
        raise ContractError("Projection-Trust externer Authority-Pin falsch")
    authority_git = _git(repo, "show", f"{expected_authority_commit}:{AUTHORITY_POLICY_PATH}", check=False)
    if authority_git.returncode != 0 or authority_git.stdout != authority_bytes:
        raise ContractError("Projection-Trust Authority-Gitbytes falsch")
    authority_oid = _git(repo, "rev-parse", f"{expected_authority_commit}:{AUTHORITY_POLICY_PATH}", check=False)
    if authority_oid.returncode != 0 or authority_oid.stdout.decode().strip() != authority_info["git_blob"]:
        raise ContractError("Projection-Trust Authority-Gitblob falsch")

    scenario_info = receipt.get("scenario_catalog")
    if not isinstance(scenario_info, dict) or set(scenario_info) != {"ref", "sha256"}:
        raise ContractError("Rich Receipt scenario_catalog Felder falsch")
    if scenario_info != {"ref": sealed["scenario_catalog"][0]["ref"], "sha256": sealed["scenario_catalog"][0]["sha256"]}:
        raise ContractError("Rich Receipt Scenario-Katalog/Sealed-Bindung falsch")
    catalog = _load_catalog(sealed["scenario_catalog"][1])
    features, symbol_map = _feature_and_symbol_sets(
        sealed["feature_universe"][1], sealed["symbol_universe"][1],
    )
    _validate_catalog_exact_set(catalog, features, symbol_map)
    row = catalog.get(receipt["scenario_id"])
    if row is None or row.get("scenario_sha256") != receipt.get("scenario_sha256"):
        raise ContractError("Rich Receipt Scenario-ID/SHA falsch")
    _validate_contract_bindings(row, contract)
    _validate_target_sets(row, features, symbol_map)
    if (
        receipt["covered_feature_paths"] != [row.get("feature_target")]
        or receipt["covered_symbol_ids"] != sorted(row.get("allowed_symbol_ids", []))
        or receipt["covered_axes"] != sorted(set(row.get("allowed_axes", [])))
    ):
        raise ContractError("Rich Receipt Scenario-Coverage falsch")

    runner = receipt.get("runner")
    if not isinstance(runner, dict) or set(runner) != {"path", "ref", "tooling_commit", "sha256", "shell"}:
        raise ContractError("Rich Receipt Runner Exact-Fields falsch")
    if (
        runner.get("path") != "tools/audit_runtime_evidence.py"
        or runner.get("tooling_commit") != receipt["tooling_commit"]
        or runner.get("shell") is not False
        or runner.get("ref") != sealed["runner"][0]["ref"]
        or runner.get("sha256") != sealed["runner"][0]["sha256"]
    ):
        raise ContractError("Rich Receipt Runner-Bindung falsch")
    runner_git = _git(
        repo, "show", f"{receipt['tooling_commit']}:tools/audit_runtime_evidence.py", check=False,
    )
    if runner_git.returncode != 0 or runner_git.stdout != sealed["runner"][1]:
        raise ContractError("Projection-Trust Runner-Gitbytes falsch")
    if _git(repo, "cat-file", "-e", f"{receipt['audited_commit']}^{{commit}}", check=False).returncode != 0:
        raise ContractError("Projection-Trust audited_commit fehlt")

    materialization = receipt.get("materialization")
    if not isinstance(materialization, dict) or set(materialization) != {"method", "audited", "tooling"} or materialization.get("method") != "git-cat-file":
        raise ContractError("Rich Receipt Materialization falsch")
    for name, commit in (("audited", receipt["audited_commit"]), ("tooling", receipt["tooling_commit"])):
        item = materialization.get(name)
        if (
            not isinstance(item, dict)
            or set(item) != {"commit", "files", "manifest_sha256", "method"}
            or item.get("commit") != commit or item.get("method") != "git-cat-file"
            or type(item.get("files")) is not int or item["files"] < 1
            or not HASH_RE.fullmatch(str(item.get("manifest_sha256", "")))
        ):
            raise ContractError(f"Rich Receipt Materialization {name} falsch")
        if item != _git_manifest_summary(repo, commit):
            raise ContractError(f"Rich Receipt Materialization {name} Gitmanifest falsch")

    environment = receipt.get("environment")
    environment_fields = {
        "python_no_user_site", "python_safe_path", "python_flags", "path",
        "executor_manifest_sha256", "dependency_manifest_sha256",
        "required_modules", "dependency_manifest",
    }
    executors, dependencies = _validate_executor_and_dependencies(
        sealed["executor_manifest"][1], sealed["dependency_manifest"][1], row,
    )
    expected_executor = executors["python"]
    if not isinstance(environment, dict) or set(environment) != environment_fields:
        raise ContractError("Rich Receipt Environment Exact-Fields falsch")
    if (
        environment.get("python_no_user_site") is not True
        or environment.get("python_safe_path") is not True
        or environment.get("python_flags") != ["-I", "-S"]
        or environment.get("executor_manifest_sha256") != sealed["executor_manifest"][0]["sha256"]
        or environment.get("dependency_manifest_sha256") != sealed["dependency_manifest"][0]["sha256"]
        or environment.get("dependency_manifest") != dependencies
        or environment.get("required_modules") != row.get("required_modules")
    ):
        raise ContractError("Rich Receipt Environment-Bindung falsch")

    observer = receipt.get("observer")
    observer_fields = {"source", "pid", "start_ns", "end_ns", "events", "threat_boundary", "cryptographic_anti_tamper"}
    if not isinstance(observer, dict) or set(observer) != observer_fields:
        raise ContractError("Rich Receipt Observer Exact-Fields falsch")
    if (
        observer.get("source") != "harness-controlled"
        or observer.get("threat_boundary") != "shared-interpreter-no-cryptographic-anti-tamper"
        or observer.get("cryptographic_anti_tamper") is not False
        or any(type(observer.get(field)) is not int for field in ("pid", "start_ns", "end_ns", "events"))
        or observer["start_ns"] > observer["end_ns"]
    ):
        raise ContractError("Rich Receipt Observer-Bindung falsch")

    stdout_path, _ = _file_binding(run_dir, receipt.get("stdout"), {"ref", "bytes", "sha256"}, "Runtime stdout")
    stderr_path, _ = _file_binding(run_dir, receipt.get("stderr"), {"ref", "bytes", "sha256"}, "Runtime stderr")
    del stdout_path, stderr_path
    exit_record = receipt.get("exit")
    _file_binding(run_dir, exit_record, {"code", "ref", "bytes", "sha256"}, "Runtime exit")
    if type(exit_record.get("code")) is not int or exit_record["code"] not in row.get("expected_exit_codes", [0]):
        raise ContractError("Rich Receipt Exit-Code falsch")

    trace_record = receipt.get("trace")
    _, trace_bytes = _file_binding(run_dir, trace_record, {"ref", "bytes", "sha256", "owner"}, "Runtime trace")
    if trace_record.get("owner") != "runner-from-trusted-harness-report":
        raise ContractError("Rich Receipt Trace-Owner falsch")
    events = _parse_jsonl(trace_bytes, "Runtime trace")
    event_axes = [event.get("axis") for event in events]
    if any(not isinstance(axis, str) or axis not in KNOWN_AXES for axis in event_axes):
        raise ContractError("Rich Receipt Trace-Achse Typ/Wert falsch")
    if len(events) != observer["events"] or sorted(event_axes) != axes:
        raise ContractError("Rich Receipt Trace-Achsen/Eventzahl falsch")
    for event in events:
        if event.get("feature_path") != row.get("feature_target") or event.get("axis") not in axes:
            raise ContractError("Rich Receipt Trace-Feature/Achse falsch")
        expected_observer = "trusted-tooling-harness" if event.get("axis") == "executed" else "runner-postcondition"
        if event.get("observer") != expected_observer:
            raise ContractError("Rich Receipt Trace-Observer falsch")
        expected_fields = (
            {"observer", "source", "event", "feature_path", "axis", "pid", "start_ns", "end_ns", "descriptor_sha256"}
            if event.get("axis") == "executed"
            else {"observer", "event", "feature_path", "axis", "pid", "time_ns"}
        )
        if set(event) != expected_fields:
            raise ContractError("Rich Receipt Trace-Event Exact-Fields falsch")
        if event.get("axis") == "executed" and (
            event.get("source") != "harness-controlled"
            or event.get("event") != "target-completed"
            or event.get("pid") != observer["pid"]
            or event.get("start_ns") != observer["start_ns"]
            or event.get("end_ns") != observer["end_ns"]
        ):
            raise ContractError("Rich Receipt Executed-Trace-Bindung falsch")
        if event.get("axis") != "executed" and (
            event.get("event") != "pass" or type(event.get("pid")) is not int
            or type(event.get("time_ns")) is not int
        ):
            raise ContractError("Rich Receipt Postcondition-Trace-Bindung falsch")

    post_record = receipt.get("postcondition")
    _, post_bytes = _file_binding(
        run_dir, post_record,
        {"ref", "bytes", "sha256", "result", "checker_exit_code", "checker"},
        "Runtime postcondition",
    )
    post_payload = _parse_json(post_bytes, "Runtime postcondition payload")
    if set(post_payload) != {"exit_code", "stdout_sha256", "stderr_sha256", "result"}:
        raise ContractError("Rich Receipt Postcondition-Payload Felder falsch")
    post_stdout = run_dir / "postcondition.stdout.bin"
    post_stderr = run_dir / "postcondition.stderr.bin"
    if not post_stdout.is_file() or not post_stderr.is_file():
        raise ContractError("Rich Receipt Postcondition stdout/stderr fehlt")
    if (
        post_record.get("result") != "pass" or post_record.get("checker_exit_code") != 0
        or post_payload.get("exit_code") != 0 or post_payload.get("result") != "pass"
        or post_payload.get("stdout_sha256") != _sha(post_stdout)
        or post_payload.get("stderr_sha256") != _sha(post_stderr)
    ):
        raise ContractError("Rich Receipt Postcondition-Bindung falsch")
    _provenance_shape(
        post_record.get("checker"), receipt["tooling_commit"], "Postcondition",
        repo=repo, expected_executor=expected_executor,
        expected_source_path=row["postcondition"]["argv"][1],
    )

    scenario_inputs = row.get("inputs")
    inputs = receipt.get("inputs")
    if (
        not isinstance(scenario_inputs, list)
        or not isinstance(inputs, list)
        or len(inputs) != len(scenario_inputs)
    ):
        raise ContractError("Rich Receipt Inputs falsch")
    expected_inputs: dict[str, dict[str, Any]] = {}
    expected_input_refs: dict[str, str] = {}
    for index, expected in enumerate(scenario_inputs):
        if not isinstance(expected, dict):
            raise ContractError(f"Rich Receipt Scenario-Input {index} falsch")
        name = expected.get("name")
        source_ref = expected.get("ref")
        if (
            not isinstance(name, str) or not ID_RE.fullmatch(name)
            or name in expected_inputs or not isinstance(source_ref, str)
        ):
            raise ContractError(f"Rich Receipt Scenario-Input {index} Name/Ref falsch")
        expected_inputs[name] = expected
        expected_input_refs[name] = (
            f"runs/{run_dir.name}/sealed/inputs/{name}{Path(source_ref).suffix}"
        )
    seen_input_names: set[str] = set()
    for item in inputs:
        if not isinstance(item, dict) or set(item) != {"name", "source_ref", "ref", "sha256"}:
            raise ContractError("Rich Receipt Input-Record falsch")
        item_name = item.get("name")
        if not isinstance(item_name, str) or not ID_RE.fullmatch(item_name):
            raise ContractError("Rich Receipt Input-Name ungueltig")
        expected = expected_inputs.get(item_name)
        if item_name in seen_input_names:
            raise ContractError("Rich Receipt Input-Name doppelt")
        seen_input_names.add(item_name)
        path = _run_ref_file(run_dir, item.get("ref"), f"Runtime Input {item_name}")
        if (
            expected is None
            or item.get("source_ref") != expected.get("ref")
            or item.get("ref") != expected_input_refs[item_name]
            or item.get("sha256") != expected.get("sha256")
            or _sha(path) != item.get("sha256")
        ):
            raise ContractError("Rich Receipt Input-Bindung falsch")
    aggregate = receipt.get("input")
    expected_aggregate = (
        {"ref": inputs[0]["ref"], "sha256": inputs[0]["sha256"]}
        if len(inputs) == 1 else {"ref": "multiple", "sha256": canonical_sha256(inputs)}
    )
    if aggregate != expected_aggregate:
        raise ContractError("Rich Receipt Input-Aggregat falsch")

    harness = receipt.get("harness")
    if not isinstance(harness, dict) or set(harness) != {"argv", "cwd", "timeout_seconds", "commit", "executor", "source"}:
        raise ContractError("Rich Receipt Harness Exact-Fields falsch")
    if harness.get("argv") != row["harness"].get("argv") or harness.get("cwd") != row["harness"].get("cwd"):
        raise ContractError("Rich Receipt Harness Scenario-Bindung falsch")
    expected_harness_timeout = float(row["harness"].get("timeout_seconds", row["timeout_seconds"]))
    if harness.get("timeout_seconds") != expected_harness_timeout:
        raise ContractError("Rich Receipt Harness Timeout-Bindung falsch")
    _provenance_shape(
        {key: harness[key] for key in ("commit", "executor", "source")},
        receipt["tooling_commit"], "Harness", repo=repo,
        expected_executor=expected_executor,
        expected_source_path=row["harness"]["argv"][1],
    )

    descriptor_path = run_dir / "target_descriptor.json"
    if not descriptor_path.is_file():
        raise ContractError("Rich Receipt Target-Descriptor fehlt")
    descriptor_bytes = descriptor_path.read_bytes()
    descriptor = _parse_json(descriptor_bytes, "Target-Descriptor")
    target = receipt.get("target")
    if not isinstance(target, dict) or set(target) != {"descriptor_sha256", "report", "source"}:
        raise ContractError("Rich Receipt Target Exact-Fields falsch")
    report_path = run_dir / "harness_report.json"
    if not report_path.is_file():
        raise ContractError("Rich Receipt Harness-Report fehlt")
    report = _parse_json(report_path.read_bytes(), "Harness-Report")
    if set(descriptor) != {
        "schema_version", "audited_commit", "target_path", "target_ref",
        "target_git_blob", "target_sha256", "argv", "feature_target", "inputs",
    } or descriptor.get("schema_version") != 1:
        raise ContractError("Rich Receipt Target-Descriptor Exact-Fields falsch")
    if set(report) != {
        "schema_version", "descriptor_sha256", "target_exit_code",
        "started_ns", "ended_ns", "loaded_modules",
    } or report.get("schema_version") != 1 or report.get("target_exit_code") != 0:
        raise ContractError("Rich Receipt Harness-Report Exact-Fields/Status falsch")
    if (
        not isinstance(report.get("loaded_modules"), list)
        or any(type(report.get(field)) is not int for field in ("started_ns", "ended_ns"))
        or report["started_ns"] > report["ended_ns"]
    ):
        raise ContractError("Rich Receipt Harness-Report Zeiten/Module falsch")
    _validate_harness_report_payload(report, descriptor_bytes, dependencies, row)
    descriptor_inputs = descriptor.get("inputs")
    if not isinstance(descriptor_inputs, dict):
        raise ContractError("Rich Receipt Target-Descriptor Inputs falsch")
    if target.get("descriptor_sha256") != _sha_bytes(descriptor_bytes) or target.get("report") != report:
        raise ContractError("Rich Receipt Target Descriptor/Report falsch")
    source = target.get("source")
    source_path = row["target"].get("path")
    posix_target_path = PurePosixPath(source_path) if isinstance(source_path, str) else None
    expected_descriptor_inputs = expected_input_refs
    if (
        not isinstance(source, dict) or set(source) != {"commit", "path", "git_blob", "sha256"}
        or source.get("commit") != receipt["audited_commit"]
        or not SHA_RE.fullmatch(str(source.get("git_blob", "")))
        or not HASH_RE.fullmatch(str(source.get("sha256", "")))
        or not isinstance(source_path, str)
        or "\\" in source_path or ":" in source_path
        or posix_target_path is None or posix_target_path.is_absolute()
        or any(part in {"", ".", ".."} for part in posix_target_path.parts)
        or source.get("path") != source_path
        or descriptor.get("audited_commit") != receipt["audited_commit"]
        or descriptor.get("target_path") != source_path
        or descriptor.get("target_ref") != source.get("path")
        or descriptor.get("target_git_blob") != source.get("git_blob")
        or descriptor.get("target_sha256") != source.get("sha256")
        or descriptor.get("argv") != row["target"].get("argv")
        or descriptor.get("feature_target") != row.get("feature_target")
        or descriptor_inputs != expected_descriptor_inputs
        or report.get("descriptor_sha256") != target.get("descriptor_sha256")
        or any(
            event.get("descriptor_sha256") != target.get("descriptor_sha256")
            for event in events if event.get("axis") == "executed"
        )
    ):
        raise ContractError("Rich Receipt Target Source-Bindung falsch")
    target_blob = _git(repo, "rev-parse", f"{receipt['audited_commit']}:{source_path}", check=False)
    target_raw = _git(repo, "show", f"{receipt['audited_commit']}:{source_path}", check=False)
    if (
        target_blob.returncode != 0 or target_raw.returncode != 0
        or target_blob.stdout.decode().strip() != source["git_blob"]
        or _sha_bytes(target_raw.stdout) != source["sha256"]
    ):
        raise ContractError("Rich Receipt Target replacement-freie Gitbytes falsch")

    artifact_rows = receipt.get("artifacts")
    if not isinstance(artifact_rows, list) or len(artifact_rows) != len(row.get("artifacts", [])):
        raise ContractError("Rich Receipt Artifacts falsch")
    expected_artifacts = {item.get("name"): item for item in row["artifacts"]}
    seen_artifact_names: set[str] = set()
    for item in artifact_rows:
        if not isinstance(item, dict) or set(item) != {"name", "ref", "bytes", "sha256"}:
            raise ContractError("Rich Receipt Artifact-Record falsch")
        expected = expected_artifacts.get(item.get("name"))
        if item.get("name") in seen_artifact_names:
            raise ContractError("Rich Receipt Artifact-Name doppelt")
        seen_artifact_names.add(item.get("name"))
        _file_binding(run_dir, item, {"name", "ref", "bytes", "sha256"}, f"Runtime Artifact {item.get('name')}")
        if expected is None or item.get("ref") != f"runs/{run_dir.name}/{expected.get('ref')}":
            raise ContractError("Rich Receipt Artifact-Scenario-Bindung falsch")


def build_runtime_projection(
    receipt: dict[str, Any], receipt_bytes: bytes, run_dir: Path, *,
    repo_root: Path, expected_contract_sha256: str, expected_authority_commit: str,
) -> dict[str, Any]:
    """Build exact compact runtime-evidence row from one canonical rich receipt."""
    _validate_receipt_for_projection(
        receipt, receipt_bytes, run_dir, repo_root=repo_root,
        expected_contract_sha256=expected_contract_sha256,
        expected_authority_commit=expected_authority_commit,
    )
    runtime_run_id = receipt["runtime_run_id"]
    projection: dict[str, Any] = {
        "evidence_id": receipt["evidence_id"],
        "evidence_kind": "runtime",
        "runtime_run_id": runtime_run_id,
        "covered_feature_paths": list(receipt["covered_feature_paths"]),
        "covered_symbol_ids": list(receipt["covered_symbol_ids"]),
        "covered_axes": list(receipt["covered_axes"]),
        "proof_ref": f"runs/{runtime_run_id}/receipt.json",
        "proof_sha256": _sha_bytes(receipt_bytes),
        "run_id": receipt["run_id"],
        "audited_commit": receipt["audited_commit"],
        "tooling_commit": receipt["tooling_commit"],
        "snapshot_id": receipt["snapshot_id"],
        "timestamp": receipt["timestamp"],
    }
    projection["record_sha256"] = canonical_sha256(projection)
    return projection


def validate_runtime_projection(
    projection: dict[str, Any], receipt: dict[str, Any], receipt_bytes: bytes,
    run_dir: Path, *, repo_root: Path, expected_contract_sha256: str,
    expected_authority_commit: str,
) -> None:
    """Fail closed unless projection exactly represents supplied rich receipt bytes."""
    if not isinstance(projection, dict) or set(projection) != PROJECTION_FIELDS:
        raise ContractError("Runtime-Projection Exact-Fields falsch")
    seal = projection.get("record_sha256")
    if not isinstance(seal, str) or not HASH_RE.fullmatch(seal):
        raise ContractError("Runtime-Projection record_sha256 ungueltig")
    if seal != canonical_sha256(projection, omit={"record_sha256"}):
        raise ContractError("Runtime-Projection record_sha256 stimmt nicht")
    expected = build_runtime_projection(
        receipt, receipt_bytes, run_dir, repo_root=repo_root,
        expected_contract_sha256=expected_contract_sha256,
        expected_authority_commit=expected_authority_commit,
    )
    if projection != expected:
        raise ContractError("Runtime-Projection stimmt nicht exakt mit Rich Receipt ueberein")


def _read_projection_pair(
    run_dir: Path, *, repo_root: Path, expected_contract_sha256: str,
    expected_authority_commit: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt_path = run_dir / "receipt.json"
    projection_path = run_dir / "projection.json"
    if not receipt_path.is_file() or not projection_path.is_file():
        raise ContractError(f"Runtime-Run {run_dir.name}: Receipt/Projection fehlt")
    receipt_bytes = receipt_path.read_bytes()
    receipt = _parse_json(receipt_bytes, f"Runtime-Run {run_dir.name} Receipt")
    if receipt.get("runtime_run_id") != run_dir.name:
        raise ContractError(f"Runtime-Run {run_dir.name}: Verzeichnis/Receipt-ID falsch")
    projection_bytes = projection_path.read_bytes()
    projection = _parse_json(projection_bytes, f"Runtime-Run {run_dir.name} Projection")
    validate_runtime_projection(
        projection, receipt, receipt_bytes, run_dir, repo_root=repo_root,
        expected_contract_sha256=expected_contract_sha256,
        expected_authority_commit=expected_authority_commit,
    )
    if projection_bytes != _canonical_bytes(projection) + b"\n":
        raise ContractError(f"Runtime-Run {run_dir.name}: Projection nicht kanonisch serialisiert")
    return receipt, projection


def _replace_bytes_atomic(path: Path, data: bytes, prefix: str) -> None:
    descriptor, name = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=path.parent)
    os.close(descriptor)
    temp_path = Path(name)
    try:
        _durable_write(temp_path, data)
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    finally:
        temp_path.unlink(missing_ok=True)


def _export_runtime_evidence_locked(
    evidence: Path, *, repo_root: Path, expected_contract_sha256: str,
    expected_authority_commit: str,
) -> list[dict[str, Any]]:
    runs_root = evidence / "runs"
    ledger = evidence / "runtime_runs.jsonl"
    if not runs_root.is_dir() or not ledger.is_file():
        raise ContractError("Runtime-Export braucht runs/ und runtime_runs.jsonl")
    ledger_bytes = ledger.read_bytes()
    ledger_rows = _parse_jsonl(ledger_bytes, "runtime_runs.jsonl")
    if ledger_bytes != b"".join(_canonical_bytes(row) + b"\n" for row in ledger_rows):
        raise ContractError("runtime_runs.jsonl ist nicht kanonisch serialisiert")
    ledger_by_id: dict[str, dict[str, Any]] = {}
    evidence_ids: set[str] = set()
    for row in ledger_rows:
        runtime_run_id = row.get("runtime_run_id")
        evidence_id = row.get("evidence_id")
        if (
            not isinstance(runtime_run_id, str)
            or not ID_RE.fullmatch(runtime_run_id)
            or runtime_run_id in ledger_by_id
        ):
            raise ContractError("runtime_runs.jsonl hat fehlende/doppelte runtime_run_id")
        if not isinstance(evidence_id, str) or evidence_id in evidence_ids:
            raise ContractError("runtime_runs.jsonl hat fehlende/doppelte evidence_id")
        ledger_by_id[runtime_run_id] = row
        evidence_ids.add(evidence_id)
    run_dirs: dict[str, Path] = {}
    for child in runs_root.iterdir():
        lock_id = child.name[1:-5] if child.name.startswith(".") and child.name.endswith(".lock") else ""
        if child.is_file() and ID_RE.fullmatch(lock_id):
            continue
        if child.is_symlink() or not child.is_dir() or not ID_RE.fullmatch(child.name) or child.name in run_dirs:
            raise ContractError(f"Runtime-Run-Pfad ungueltig: {child.name}")
        run_dirs[child.name] = child
    if set(run_dirs) != set(ledger_by_id):
        raise ContractError("Runtime-Run-Verzeichnisse und Rich Ledger sind keine Exact-Set-Menge")
    projections: list[dict[str, Any]] = []
    for runtime_run_id in sorted(run_dirs):
        receipt, projection = _read_projection_pair(
            run_dirs[runtime_run_id], repo_root=repo_root,
            expected_contract_sha256=expected_contract_sha256,
            expected_authority_commit=expected_authority_commit,
        )
        if receipt != ledger_by_id[runtime_run_id]:
            raise ContractError(f"Runtime-Run {runtime_run_id}: Receipt und Rich Ledger unterscheiden sich")
        projections.append(projection)
    payload = b"".join(_canonical_bytes(row) + b"\n" for row in projections)
    _replace_bytes_atomic(evidence / "runtime-evidence.jsonl", payload, "runtime-evidence-")
    return projections


def export_runtime_evidence(
    evidence_root: Path, *, repo_root: Path, expected_contract_sha256: str,
    expected_authority_commit: str,
) -> list[dict[str, Any]]:
    """Atomically reconstruct static projection shard from immutable run dirs."""
    evidence = evidence_root.resolve()
    if not evidence.is_dir():
        raise ContractError("evidence_root fehlt")
    lock = evidence / ".runtime_runs.lock"
    lock_payload = _create_ledger_lock(lock)
    try:
        return _export_runtime_evidence_locked(
            evidence, repo_root=repo_root,
            expected_contract_sha256=expected_contract_sha256,
            expected_authority_commit=expected_authority_commit,
        )
    finally:
        _release_lock(lock, lock_payload)


def _existing_runtime_ids(ledger: Path) -> tuple[set[str], set[str]]:
    if not ledger.exists():
        return set(), set()
    rows = _parse_jsonl(ledger.read_bytes(), "runtime_runs.jsonl")
    runtime_ids: set[str] = set()
    evidence_ids: set[str] = set()
    for row in rows:
        runtime_id, evidence_id = row.get("runtime_run_id"), row.get("evidence_id")
        if not isinstance(runtime_id, str) or runtime_id in runtime_ids:
            raise ContractError("runtime_runs.jsonl hat fehlende/doppelte runtime_run_id")
        if not isinstance(evidence_id, str) or evidence_id in evidence_ids:
            raise ContractError("runtime_runs.jsonl hat fehlende/doppelte evidence_id")
        runtime_ids.add(runtime_id)
        evidence_ids.add(evidence_id)
    return runtime_ids, evidence_ids


def _scenario_already_recorded(ledger: Path, scenario_id: str) -> bool:
    if not ledger.exists():
        return False
    return any(row.get("scenario_id") == scenario_id for row in _parse_jsonl(ledger.read_bytes(), "runtime_runs.jsonl"))


def _create_lock(path: Path, label: str) -> bytes:
    payload = _canonical_bytes({"pid": os.getpid(), "created_ns": time.time_ns(), "nonce": uuid.uuid4().hex}) + b"\n"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except (FileExistsError, PermissionError) as exc:
        raise ContractError(f"{label}-Lock existiert; auch stale Lock muss manuell untersucht werden") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)
    return payload


def _release_lock(path: Path, payload: bytes) -> None:
    deadline = time.monotonic() + 5
    while True:
        try:
            if path.read_bytes() != payload:
                raise ContractError(f"Lock-Ownership geaendert: {path.name}")
            path.unlink()
            _fsync_directory(path.parent)
            return
        except PermissionError:
            if time.monotonic() >= deadline:
                raise ContractError(f"Lock konnte nicht freigegeben werden: {path.name}")
            time.sleep(0.02)


def _pid_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if pid <= 0:
        return False
    if os.name == "nt":
        output = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
        return f'"{pid}"' in output
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _create_ledger_lock(path: Path) -> bytes:
    deadline = time.monotonic() + 15
    while True:
        try:
            return _create_lock(path, "Ledger")
        except ContractError:
            try:
                existing = _parse_json(path.read_bytes(), "Ledger-Lock")
                pid = int(existing.get("pid", -1))
            except (OSError, ValueError, ContractError):
                raise ContractError("Ledger-Lock existiert; stale/ungueltig muss manuell untersucht werden")
            if not _pid_alive(pid):
                raise ContractError("Ledger-Lock existiert; stale Lock muss manuell untersucht werden")
            if time.monotonic() >= deadline:
                raise ContractError("Ledger-Lock durch aktiven Prozess blockiert")
            time.sleep(0.02)


def _publish_run_and_ledgers(
    stage_run: Path, final_run: Path, ledger: Path, receipt: dict[str, Any],
    *, repo_root: Path, expected_contract_sha256: str, expected_authority_commit: str,
    ownership_token: str,
) -> None:
    """Serialize run-dir publication and per-file atomic ledger replacements.

    Run directory is published before ledgers because projections point into it.
    Rich and compact ledgers are each atomic files, but deliberately not claimed
    as one impossible cross-file atomic transaction. If compact export fails
    after rich-ledger commit, immutable run + rich ledger remain recoverable by
    ``export_runtime_evidence``.
    """
    lock = ledger.parent / ".runtime_runs.lock"
    lock_payload = _create_ledger_lock(lock)
    temp_path: Path | None = None
    published = False
    ledger_committed = False
    try:
        if not _owns_published_run(
            stage_run, receipt["runtime_run_id"], ownership_token,
        ):
            raise ContractError("Runtime-Run Ownership-Marker fehlt/falsch")
        runtime_ids, evidence_ids = _existing_runtime_ids(ledger)
        if receipt["runtime_run_id"] in runtime_ids or receipt["evidence_id"] in evidence_ids:
            raise ContractError("Runtime-Receipt bereits im Ledger vorhanden")
        if _scenario_already_recorded(ledger, receipt["scenario_id"]):
            raise ContractError("Scenario wurde bereits ausgefuehrt; Evidence-Reuse verboten")
        if final_run.exists():
            raise ContractError(f"runtime_run_id {receipt['runtime_run_id']!r} bereits vorhanden")
        existing = ledger.read_bytes() if ledger.exists() else b""
        if existing and not existing.endswith(b"\n"):
            raise ContractError("runtime_runs.jsonl endet nicht mit Newline")
        os.replace(stage_run, final_run)
        _fsync_directory(final_run.parent)
        published = True
        descriptor, name = tempfile.mkstemp(prefix="runtime-runs-", suffix=".tmp", dir=ledger.parent)
        os.close(descriptor)
        temp_path = Path(name)
        _durable_write(temp_path, existing + _canonical_bytes(receipt) + b"\n")
        os.replace(temp_path, ledger)
        _fsync_directory(ledger.parent)
        ledger_committed = True
        _export_runtime_evidence_locked(
            ledger.parent, repo_root=repo_root,
            expected_contract_sha256=expected_contract_sha256,
            expected_authority_commit=expected_authority_commit,
        )
    except Exception:
        if (
            published and not ledger_committed
            and _owns_published_run(final_run, receipt["runtime_run_id"], ownership_token)
        ):
            _remove_tree(final_run)
        raise
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        _release_lock(lock, lock_payload)


def _remove_tree(path: Path) -> None:
    def repair(function: Any, target: str, _: Any) -> None:
        os.chmod(target, 0o700)
        function(target)
    if path.exists():
        shutil.rmtree(path, onerror=repair)


def _write_run_ownership(path: Path, runtime_run_id: str, token: str) -> None:
    payload = {"runtime_run_id": runtime_run_id, "token": token}
    _durable_write(path / RUN_OWNERSHIP_FILE, _canonical_bytes(payload) + b"\n")
    os.chmod(path / RUN_OWNERSHIP_FILE, 0o444)


def _owns_published_run(path: Path, runtime_run_id: str, token: str) -> bool:
    marker = path / RUN_OWNERSHIP_FILE
    expected = _canonical_bytes({"runtime_run_id": runtime_run_id, "token": token}) + b"\n"
    try:
        return marker.is_file() and marker.read_bytes() == expected
    except OSError:
        return False


def run_scenario(
    *, repo_root: Path, evidence_root: Path, contract_path: Path,
    expected_contract_sha256: str, authority_commit: str, expected_authority_commit: str,
    authority_policy_path: str,
    scenario_id: str, runtime_run_id: str,
) -> dict[str, Any]:
    """Run one bound scenario.

    ``expected_authority_commit`` is a trust input attested by the external
    readiness/authority caller. This runner detects substitution against that
    pin; it cannot detect compromise of the caller or of the pin supplied by it.
    """
    repo = repo_root.resolve()
    evidence = evidence_root.resolve()
    contract_path = contract_path.resolve()
    if not (repo / ".git").exists():
        raise ContractError("repo_root ist kein Git-Worktree")
    if not evidence.is_dir() or _is_relative_to(evidence, repo) or _is_relative_to(repo, evidence):
        raise ContractError("evidence_root muss existieren und ausserhalb Produkt-Worktree liegen")
    if not ID_RE.fullmatch(runtime_run_id):
        raise ContractError("runtime_run_id ungueltig")
    contract, contract_bytes, refs = _load_contract(evidence, contract_path)
    authority, authority_bytes, authority_blob = _load_authority_policy(
        repo, authority_commit, expected_authority_commit,
        contract["tooling_commit"], authority_policy_path,
        expected_contract_sha256, contract,
    )
    catalog_path, catalog_bytes = refs["scenario_catalog"]
    catalog = _load_catalog(catalog_bytes)
    if scenario_id not in catalog:
        raise ContractError(f"Scenario {scenario_id!r} unbekannt")
    row = catalog[scenario_id]
    features, symbols = _feature_and_symbol_sets(refs["feature_universe"][1], refs["symbol_universe"][1])
    _validate_catalog_exact_set(catalog, features, symbols)
    for catalog_row in catalog.values():
        _validate_contract_bindings(catalog_row, contract)
        _validate_target_sets(catalog_row, features, symbols)
    executors, dependencies = _validate_executor_and_dependencies(
        refs["executor_manifest"][1], refs["dependency_manifest"][1], row,
    )
    runner_sha = _verify_tool_identity(repo, contract["tooling_commit"])

    timeout = row.get("timeout_seconds")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0 or timeout > 86400:
        raise ContractError("Scenario.timeout_seconds ungueltig")
    harness, harness_timeout = _validate_command(row.get("harness"), "harness", float(timeout), "tooling")
    post, post_timeout = _validate_command(row.get("postcondition"), "postcondition", float(timeout), "tooling")
    axes = row.get("allowed_axes")
    if not isinstance(axes, list) or not axes or len(axes) != len(set(axes)) or not set(axes).issubset(KNOWN_AXES):
        raise ContractError("Scenario.allowed_axes fehlt/doppelt/unbekannt")

    runs_root = evidence / "runs"
    staging_root = evidence / ".staging"
    runs_root.mkdir(exist_ok=True)
    staging_root.mkdir(exist_ok=True)
    final_run = runs_root / runtime_run_id
    ledger = evidence / "runtime_runs.jsonl"
    runtime_ids, evidence_ids = _existing_runtime_ids(ledger)
    if runtime_run_id in runtime_ids or final_run.exists():
        raise ContractError(f"runtime_run_id {runtime_run_id!r} bereits vorhanden")
    if _scenario_already_recorded(ledger, scenario_id):
        raise ContractError(f"Scenario {scenario_id!r} bereits ausgefuehrt; Evidence-Reuse verboten")
    run_lock = runs_root / f".{runtime_run_id}.lock"
    run_lock_payload = _create_lock(run_lock, "Runtime-Run")

    staging = staging_root / f"{runtime_run_id}-{uuid.uuid4().hex}"
    audited_root = staging / "audited"
    tooling_root = staging / "tooling"
    sealed_root = staging / "sealed"
    stage_run = staging / runtime_run_id
    stage_run.mkdir(parents=True)
    sealed_root.mkdir()
    success = False
    publish_owner_token: str | None = None
    try:
        audited_materialization = _materialize_commit(repo, contract["audited_commit"], audited_root)
        tooling_materialization = _materialize_commit(repo, contract["tooling_commit"], tooling_root)
        audited_integrity = _snapshot_files(audited_root)
        tooling_integrity = _snapshot_files(tooling_root)

        sealed_records: list[dict[str, Any]] = []
        runner_path = Path(__file__).resolve()
        runner_bytes = runner_path.read_bytes()
        if _sha_bytes(runner_bytes) != runner_sha:
            raise ContractError("Runner wurde nach Tooling-Identity-Pruefung veraendert")
        source_hashes: dict[Path, str] = {
            contract_path: _sha_bytes(contract_bytes), runner_path: runner_sha,
        }
        contract_copy = sealed_root / "audit_contract.json"
        _durable_write(contract_copy, contract_bytes)
        os.chmod(contract_copy, 0o444)
        sealed_records.append({"name": "audit_contract", "ref": f"runs/{runtime_run_id}/sealed/audit_contract.json", "sha256": _sha(contract_copy)})
        authority_copy = sealed_root / "authority.json"
        _durable_write(authority_copy, authority_bytes)
        os.chmod(authority_copy, 0o444)
        sealed_records.append({"name": "authority", "ref": f"runs/{runtime_run_id}/sealed/authority.json", "sha256": _sha(authority_copy), "git_blob": authority_blob})
        runner_copy = sealed_root / "runner.py"
        _durable_write(runner_copy, runner_bytes)
        os.chmod(runner_copy, 0o444)
        sealed_records.append({"name": "runner", "ref": f"runs/{runtime_run_id}/sealed/runner.py", "sha256": _sha(runner_copy)})
        for name, (source, data) in refs.items():
            source_hashes[source] = _sha_bytes(data)
            target = sealed_root / f"{name}{source.suffix or '.bin'}"
            _durable_write(target, data)
            os.chmod(target, 0o444)
            sealed_records.append({"name": name, "ref": f"runs/{runtime_run_id}/sealed/{target.name}", "sha256": _sha(target)})

        input_rows = row.get("inputs")
        if not isinstance(input_rows, list):
            raise ContractError("Scenario.inputs muss Liste sein")
        sealed_inputs_dir = sealed_root / "inputs"
        sealed_inputs_dir.mkdir()
        input_paths: dict[str, Path] = {}
        input_receipts: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for index, item in enumerate(input_rows):
            if not isinstance(item, dict):
                raise ContractError(f"Scenario.inputs[{index}]: Objekt erwartet")
            name = item.get("name")
            if not isinstance(name, str) or not ID_RE.fullmatch(name) or name in seen_names:
                raise ContractError(f"Scenario.inputs[{index}]: name fehlt/doppelt")
            seen_names.add(name)
            source = _relative_ref(evidence, item.get("ref"), f"Scenario.inputs[{index}]")
            if not source.is_file():
                raise ContractError(f"Input fehlt: {item.get('ref')}")
            data = source.read_bytes()
            expected = item.get("sha256")
            if not isinstance(expected, str) or not HASH_RE.fullmatch(expected) or _sha_bytes(data) != expected:
                raise ContractError(f"Input-Hash stimmt nicht: {item.get('ref')}")
            source_hashes[source] = expected
            target = sealed_inputs_dir / f"{name}{source.suffix}"
            _durable_write(target, data)
            os.chmod(target, 0o444)
            input_paths[name] = target
            input_receipts.append({"name": name, "source_ref": item["ref"], "ref": f"runs/{runtime_run_id}/sealed/inputs/{target.name}", "sha256": expected})

        sealed_integrity = _snapshot_files(sealed_root)

        target = row.get("target")
        if not isinstance(target, dict) or set(target) != {"path", "argv"}:
            raise ContractError("Scenario.target braucht exakt path + argv")
        target_ref = target.get("path")
        target_args = target.get("argv")
        if not isinstance(target_ref, str) or Path(target_ref).is_absolute() or ".." in Path(target_ref).parts:
            raise ContractError("Scenario.target.path ungueltig/Pfad-Escape")
        if not isinstance(target_args, list) or not all(isinstance(arg, str) for arg in target_args):
            raise ContractError("Scenario.target.argv ungueltig")
        target_path = _contained(audited_root, audited_root / target_ref, "Scenario.target.path")
        if not target_path.is_file():
            raise ContractError("Scenario.target fehlt im audited_commit")
        target_blob = _git(repo, "rev-parse", f"{contract['audited_commit']}:{target_ref}", check=False)
        if target_blob.returncode != 0:
            raise ContractError("Scenario.target ist kein gebundener audited_commit-Blob")
        descriptor = {
            "schema_version": 1, "audited_commit": contract["audited_commit"],
            "target_path": target_ref, "target_ref": target_ref,
            "target_git_blob": target_blob.stdout.decode().strip(), "target_sha256": _sha(target_path),
            "argv": target_args, "feature_target": row["feature_target"],
            "inputs": {item["name"]: item["ref"] for item in input_receipts},
        }
        descriptor_bytes = _canonical_bytes(descriptor) + b"\n"
        descriptor_path = stage_run / "target_descriptor.json"
        report_path = stage_run / "harness_report.json"
        _durable_write(descriptor_path, descriptor_bytes)
        harness_argv, harness_cwd, harness_provenance = _resolve_command(
            harness, root=tooling_root, run_dir=stage_run, inputs=input_paths,
            executors=executors, label="harness", commit=contract["tooling_commit"],
            special_paths={"target_descriptor": descriptor_path, "harness_report": report_path},
        )
        environment = _sanitized_environment(audited_root, stage_run)
        exit_code, stdout, stderr, process_pid, start_ns, end_ns = _execute(
            harness_argv, cwd=harness_cwd, timeout=harness_timeout, environment=environment,
            label="harness",
        )
        _assert_sources_unchanged(source_hashes)
        _assert_snapshot(sealed_root, sealed_integrity, "Versiegelte Inputs nach Command")
        _assert_snapshot(audited_root, audited_integrity, "Auditcommit-Materialisierung nach Command")
        _assert_snapshot(tooling_root, tooling_integrity, "Toolingcommit-Materialisierung nach Command")
        if (stage_run / "trace.jsonl").exists():
            raise ContractError("trace.jsonl ist runner-reserviert; Scenario darf Trace nicht selbst schreiben")
        expected_exit_codes = row.get("expected_exit_codes", [0])
        if not isinstance(expected_exit_codes, list) or exit_code not in expected_exit_codes:
            raise ContractError(f"harness: Exit {exit_code} nicht erwartet")
        harness_report = _validate_harness_report(report_path, descriptor_bytes, dependencies, row)
        covered_symbols: list[str] = []
        unsupported = set(row["allowed_axes"]) - {"executed", "result", "live_evidence"}
        if unsupported:
            raise ContractError(f"Achsen brauchen trusted externen Spezialobserver: {sorted(unsupported)}")
        covered_axes = ["executed"] if "executed" in row["allowed_axes"] else []
        observations = [{
            "observer": "trusted-tooling-harness", "source": "harness-controlled",
            "event": "target-completed", "feature_path": row["feature_target"],
            "axis": "executed", "pid": process_pid, "start_ns": start_ns, "end_ns": end_ns,
            "descriptor_sha256": _sha_bytes(descriptor_bytes),
        }]
        trace_bytes = b"".join(_canonical_bytes(event) + b"\n" for event in observations)
        trace_info = _write(stage_run / "trace.jsonl", trace_bytes)
        stdout_info = _write(stage_run / "stdout.bin", stdout)
        stderr_info = _write(stage_run / "stderr.bin", stderr)
        exit_info = _write(stage_run / "command.log", b"STDOUT\n" + stdout + b"\nSTDERR\n" + stderr)

        before_checker = _snapshot_files(stage_run)
        post_argv, post_cwd, post_provenance = _resolve_command(
            post, root=tooling_root, run_dir=stage_run, inputs=input_paths,
            executors=executors, label="postcondition", commit=contract["tooling_commit"],
        )
        post_environment = _sanitized_environment(tooling_root, stage_run)
        post_code, post_stdout, post_stderr, _, _, _ = _execute(
            post_argv, cwd=post_cwd, timeout=post_timeout, environment=post_environment,
            label="postcondition",
        )
        _assert_sources_unchanged(source_hashes)
        _assert_snapshot(sealed_root, sealed_integrity, "Versiegelte Inputs nach Postcondition")
        _assert_snapshot(audited_root, audited_integrity, "Auditcommit-Materialisierung nach Postcondition")
        _assert_snapshot(tooling_root, tooling_integrity, "Toolingcommit-Materialisierung nach Postcondition")
        _assert_snapshot(stage_run, before_checker, "Postcondition")
        if post_code != 0:
            raise ContractError(f"postcondition: Exit {post_code}")
        for axis in ("result", "live_evidence"):
            if axis in row["allowed_axes"]:
                covered_axes.append(axis)
                observations.append({
                    "observer": "runner-postcondition", "event": "pass",
                    "feature_path": row["feature_target"], "axis": axis,
                    "pid": os.getpid(), "time_ns": time.time_ns(),
                })
        covered_axes = sorted(set(covered_axes))
        if set(covered_axes) != set(row["allowed_axes"]):
            raise ContractError("Runner-Observer deckt allowed_axes nicht exakt")
        trace_bytes = b"".join(_canonical_bytes(event) + b"\n" for event in observations)
        trace_info = _write(stage_run / "trace.jsonl", trace_bytes)
        post_stdout_info = _write(stage_run / "postcondition.stdout.bin", post_stdout)
        post_stderr_info = _write(stage_run / "postcondition.stderr.bin", post_stderr)
        post_payload = {
            "exit_code": post_code,
            "stdout_sha256": post_stdout_info["sha256"],
            "stderr_sha256": post_stderr_info["sha256"],
            "result": "pass",
        }
        post_info = _write(stage_run / "postcondition.json", _canonical_bytes(post_payload) + b"\n")

        artifacts = row.get("artifacts")
        if not isinstance(artifacts, list):
            raise ContractError("Scenario.artifacts muss Liste sein")
        artifact_receipts: list[dict[str, Any]] = []
        seen_artifacts: set[str] = set()
        for index, item in enumerate(artifacts):
            if not isinstance(item, dict) or item.get("required") is not True:
                raise ContractError(f"Scenario.artifacts[{index}] ungueltig")
            name = item.get("name")
            if not isinstance(name, str) or name in seen_artifacts:
                raise ContractError(f"Scenario.artifacts[{index}].name fehlt/doppelt")
            seen_artifacts.add(name)
            path = _relative_ref(stage_run, item.get("ref"), f"Artefakt {name}")
            if not path.is_file():
                raise ContractError(f"Artefakt fehlt: {item.get('ref')}")
            artifact_receipts.append({"name": name, "ref": f"runs/{runtime_run_id}/{item['ref']}", "bytes": path.stat().st_size, "sha256": _sha(path)})

        _assert_sources_unchanged(source_hashes)
        _assert_snapshot(sealed_root, sealed_integrity, "Versiegelte Inputs vor Publish")
        _assert_snapshot(audited_root, audited_integrity, "Auditcommit-Materialisierung vor Publish")
        _assert_snapshot(tooling_root, tooling_integrity, "Toolingcommit-Materialisierung vor Publish")
        os.replace(sealed_root, stage_run / "sealed")
        publish_owner_token = uuid.uuid4().hex
        _write_run_ownership(stage_run, runtime_run_id, publish_owner_token)
        _fsync_tree(stage_run)
        _fsync_directory(stage_run)
        final_integrity = _snapshot_files(stage_run)
        timestamp = datetime.now(timezone.utc).isoformat()
        receipt: dict[str, Any] = {
            "plan_id": contract["plan_id"], "run_id": contract["run_id"], "runtime_run_id": runtime_run_id,
            "audited_commit": contract["audited_commit"], "tooling_commit": contract["tooling_commit"],
            "snapshot_id": contract["snapshot_id"], "scenario_id": row["scenario_id"],
            "scenario_sha256": row["scenario_sha256"], "timestamp": timestamp,
            "authority": {"git_blob": authority_blob, "path": authority_policy_path,
                          "authority_commit": authority_commit,
                          "expected_authority_commit": expected_authority_commit,
                          "sha256": _sha_bytes(authority_bytes), "policy": authority,
                          "expected_contract_sha256": expected_contract_sha256,
                          "trust_boundary": "trusted-external-authority-pin-required; compromised-external-pin-not-detected"},
            "audit_contract": {"ref": f"runs/{runtime_run_id}/sealed/audit_contract.json",
                               "sha256": _sha_bytes(contract_bytes), "contract_sha256": contract["contract_sha256"]},
            "scenario_catalog": {"ref": f"runs/{runtime_run_id}/sealed/scenario_catalog.jsonl", "sha256": _sha_bytes(catalog_bytes)},
            "sealed_contract_inputs": sealed_records,
            "materialization": {
                "method": "git-cat-file", "audited": audited_materialization,
                "tooling": tooling_materialization,
            },
            "runner": {"path": "tools/audit_runtime_evidence.py",
                       "ref": f"runs/{runtime_run_id}/sealed/runner.py",
                       "tooling_commit": contract["tooling_commit"],
                       "sha256": runner_sha, "shell": False},
            "environment": {
                "python_no_user_site": True, "python_safe_path": True,
                "python_flags": ["-I", "-S"], "path": str(Path(sys.executable).resolve().parent),
                "executor_manifest_sha256": _sha_bytes(refs["executor_manifest"][1]),
                "dependency_manifest_sha256": _sha_bytes(refs["dependency_manifest"][1]),
                "required_modules": row["required_modules"], "dependency_manifest": dependencies,
            },
            "observer": {
                "source": "harness-controlled", "pid": process_pid, "start_ns": start_ns,
                "end_ns": end_ns, "events": len(observations),
                "threat_boundary": "shared-interpreter-no-cryptographic-anti-tamper",
                "cryptographic_anti_tamper": False,
            },
            "input": {"ref": input_receipts[0]["ref"], "sha256": input_receipts[0]["sha256"]} if len(input_receipts) == 1 else {"ref": "multiple", "sha256": canonical_sha256(input_receipts)},
            "inputs": input_receipts,
            "harness": {"argv": harness["argv"], "cwd": harness["cwd"], "timeout_seconds": harness_timeout, **harness_provenance},
            "target": {"descriptor_sha256": _sha_bytes(descriptor_bytes), "report": harness_report,
                       "source": {"commit": contract["audited_commit"], "path": target_ref,
                                  "git_blob": descriptor["target_git_blob"], "sha256": descriptor["target_sha256"]}},
            "stdout": {"ref": f"runs/{runtime_run_id}/stdout.bin", **stdout_info},
            "stderr": {"ref": f"runs/{runtime_run_id}/stderr.bin", **stderr_info},
            "exit": {"code": exit_code, "ref": f"runs/{runtime_run_id}/command.log", **exit_info},
            "trace": {"ref": f"runs/{runtime_run_id}/trace.jsonl", **trace_info, "owner": "runner-from-trusted-harness-report"},
            "postcondition": {"ref": f"runs/{runtime_run_id}/postcondition.json", **post_info, "result": "pass", "checker_exit_code": post_code, "checker": post_provenance},
            "artifacts": artifact_receipts,
            "covered_feature_paths": [row["feature_target"]],
            "covered_symbol_ids": covered_symbols, "covered_axes": covered_axes,
            "final_integrity_sha256": canonical_sha256(final_integrity),
        }
        forced_axes = sorted({"error", "cancel", "retry"} & set(covered_axes))
        if len(forced_axes) > 1:
            raise ContractError("ein Runtime-Run darf nur einen erzwungenen Zustand belegen")
        if forced_axes:
            receipt["forced_state"] = forced_axes[0]
        surfaces = sorted(set(SURFACE_OBSERVERS) & set(covered_axes))
        if surfaces:
            receipt["observed_surfaces"] = surfaces
        if "restart_safe" in covered_axes:
            receipt["restart"] = True
            receipt["reopen"] = True
        receipt["evidence_id"] = canonical_evidence_id(receipt)
        if receipt["evidence_id"] in evidence_ids:
            raise ContractError("evidence_id bereits vorhanden")
        receipt_bytes = _canonical_bytes(receipt) + b"\n"
        _durable_write(stage_run / "receipt.json", receipt_bytes)
        projection = build_runtime_projection(
            receipt, receipt_bytes, stage_run, repo_root=repo,
            expected_contract_sha256=expected_contract_sha256,
            expected_authority_commit=expected_authority_commit,
        )
        _durable_write(stage_run / "projection.json", _canonical_bytes(projection) + b"\n")
        os.chmod(stage_run / "receipt.json", 0o444)
        os.chmod(stage_run / "projection.json", 0o444)
        _assert_sources_unchanged(source_hashes)
        _assert_snapshot(
            stage_run,
            {
                **final_integrity,
                "receipt.json": _sha(stage_run / "receipt.json"),
                "projection.json": _sha(stage_run / "projection.json"),
            },
            "Finale Rehash",
        )
        _fsync_tree(stage_run)

        _remove_tree(audited_root)
        _remove_tree(tooling_root)
        _publish_run_and_ledgers(
            stage_run, final_run, ledger, receipt, repo_root=repo,
            expected_contract_sha256=expected_contract_sha256,
            expected_authority_commit=expected_authority_commit,
            ownership_token=publish_owner_token,
        )
        success = True
        return receipt
    finally:
        if staging.exists():
            _remove_tree(staging)
        _release_lock(run_lock, run_lock_payload)
        if (
            not success and publish_owner_token is not None
            and runtime_run_id not in _existing_runtime_ids(ledger)[0]
            and _owns_published_run(final_run, runtime_run_id, publish_owner_token)
        ):
            _remove_tree(final_run)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--audit-contract", type=Path, required=True)
    parser.add_argument("--expected-contract-sha256", required=True)
    parser.add_argument("--authority-commit", required=True)
    parser.add_argument(
        "--expected-authority-commit", required=True,
        help="Vom vertrauenswuerdigen uebergeordneten Caller attestierter Authority-Commit",
    )
    parser.add_argument("--authority-policy-path", default=AUTHORITY_POLICY_PATH)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--runtime-run-id", required=True)
    args = parser.parse_args()
    try:
        receipt = run_scenario(
            repo_root=args.root, evidence_root=args.evidence_root,
            contract_path=args.audit_contract, expected_contract_sha256=args.expected_contract_sha256,
            authority_commit=args.authority_commit,
            expected_authority_commit=args.expected_authority_commit,
            authority_policy_path=args.authority_policy_path,
            scenario_id=args.scenario_id,
            runtime_run_id=args.runtime_run_id,
        )
    except ContractError as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
