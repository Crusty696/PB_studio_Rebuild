from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any


PLAN_ID = "PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15"
REQUIRED_GATES = {
    "feature_inventory", "symbol_contracts", "runtime_evidence",
    "reviewer_roster", "delta_ttl", "completion",
}
ATOMIC_CONTRACT_FIELDS = {
    "schema_version", "import_id", "run_id", "audited_commit", "snapshot_id",
    "tooling_commit", "audit_contract_sha256", "evidence_contract_sha256",
    "qualification", "required_gate_results", "shards",
}
AUDIT_CONTRACT_FIELDS = {
    "schema_version", "plan_id", "run_id", "audited_commit", "tooling_commit",
    "snapshot_id", "frozen_at", "expires_at", "artifacts", "contract_sha256",
}
EVIDENCE_CONTRACT_FIELDS = {
    "schema_version", "plan_id", "run_id", "audited_commit", "tooling_commit",
    "snapshot_id", "audit_contract_sha256", "completed_at", "artifacts",
    "evidence_contract_sha256",
}
AUDIT_ARTIFACT_KEYS = {
    "requirements-universe", "trigger-universe", "feature-catalog",
    "symbol-catalog", "edge-catalog", "runtime-scenario-catalog",
    "runtime-feature-universe", "runtime-symbol-universe",
    "runtime-executor-manifest", "runtime-dependency-manifest",
    "reviewer-trust-policy", "reviewer-contract",
    "reviewer-readiness-binding", "reviewer-spawn-journal",
}
EVIDENCE_STATIC_KEYS = {
    "feature-state", "feature-state-evidence", "symbol-state", "edge-state",
    "symbol-state-evidence", "reviewer-roster", "runtime-evidence", "delta-ledger",
}
DELTA_RECORD_FIELDS = {
    "run_id", "base_commit", "head_commit", "path", "change",
    "product_relevant", "disposition", "reviewer_id", "signed_at",
}
DELTA_DISPOSITIONS = {"report-only", "reaudit-required", "explicit-user-exclusion"}
DESCRIPTOR_FIELDS = {"artifact_id", "ref", "sha256", "bytes", "record_count"}
SHARD_SPEC_FIELDS = {
    "artifact_key", "name", "path", "sha256", "record_count", "primary_key",
    "foreign_keys",
}
SAFE_IMPORT_ID = re.compile(r"IMPORT-[A-Za-z0-9][A-Za-z0-9._-]{0,119}")
FULL_SHA256 = re.compile(r"[0-9a-f]{64}")
FULL_COMMIT = re.compile(r"[0-9a-f]{40}")
ATTACHMENT_KEY = re.compile(
    r"(?:feature-proof|symbol-proof|runtime-proof):[^\s]+"
    r"|reviewer-enrollment-(?:receipt|signature):[^:\s]+"
    r"|reviewer-signoff(?:-signature)?:[^:\s]+:[^:\s]+"
)


class CompletionError(ValueError):
    pass


def _canonical_key(values: list[Any]) -> str:
    return json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
        return _read_json_bytes(payload, str(path))
    except OSError as exc:
        raise CompletionError(f"JSON unlesbar: {path}: {exc}") from exc


def _read_json_bytes(payload: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CompletionError(f"JSON unlesbar: {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise CompletionError(f"JSON-Wurzel muss Objekt sein: {label}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise CompletionError(f"Shard unlesbar: {path}: {exc}") from exc
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            raise CompletionError(f"Leere JSONL-Zeile: {path}:{number}")
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CompletionError(f"JSONL ungueltig: {path}:{number}: {exc}") from exc
        if not isinstance(row, dict):
            raise CompletionError(f"JSONL-Zeile muss Objekt sein: {path}:{number}")
        rows.append(row)
    return rows


def _contains_unknown(value: Any) -> bool:
    if value == "UNKNOWN":
        return True
    if isinstance(value, dict):
        return any(_contains_unknown(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_unknown(item) for item in value)
    return False


def _aware_time(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise CompletionError(f"{label} ungueltig: {exc}") from exc
    if parsed.tzinfo is None:
        raise CompletionError(f"{label} braucht Zeitzone")
    return parsed


def _safe_ref(relative: Any) -> PurePosixPath:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise CompletionError(f"Artifact-Ref ungueltig: {relative!r}")
    ref = PurePosixPath(relative)
    if ref.is_absolute() or any(part in {"", ".", ".."} for part in ref.parts):
        raise CompletionError(f"Artifact-Ref ungueltig: {relative!r}")
    if relative != ref.as_posix() or ":" in ref.parts[0]:
        raise CompletionError(f"Artifact-Ref nicht kanonisch: {relative!r}")
    return ref


def _safe_source(bundle: Path, relative: Any) -> Path:
    ref = _safe_ref(relative)
    candidate = bundle.joinpath(*ref.parts)
    current = bundle
    for part in ref.parts:
        current /= part
        if current.is_symlink():
            raise CompletionError(f"Artifact-Ref darf keinen Symlink enthalten: {relative}")
    try:
        candidate.resolve(strict=True).relative_to(bundle.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise CompletionError(f"Artifact-Ref verlaesst Bundle: {relative}") from exc
    if not candidate.is_file():
        raise CompletionError(f"Artifact fehlt oder ist keine regulaere Datei: {relative}")
    return candidate


def _bundle_file_ref(bundle: Path, path: Path, label: str) -> PurePosixPath:
    try:
        match = next(
            candidate
            for candidate in bundle.rglob("*")
            if candidate.is_file() and os.path.samefile(candidate, path)
        )
    except (OSError, StopIteration) as exc:
        raise CompletionError(f"{label} muss innerhalb Bundle liegen") from exc
    ref = _safe_ref(match.relative_to(bundle).as_posix())
    _safe_source(bundle, ref.as_posix())
    return ref


def _record_count(path: Path, payload: bytes) -> int:
    if path.suffix.lower() == ".jsonl":
        count = 0
        try:
            for number, line in enumerate(payload.decode().splitlines(), 1):
                if not line.strip():
                    raise CompletionError(f"Leere JSONL-Zeile in Artifact {path}:{number}")
                if not isinstance(json.loads(line), dict):
                    raise CompletionError(f"JSONL-Zeile muss Objekt sein: {path}:{number}")
                count += 1
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CompletionError(f"Artifact-JSONL ungueltig: {path}: {exc}") from exc
        return count
    if path.suffix.lower() == ".json":
        try:
            value = json.loads(payload.decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CompletionError(f"Artifact-JSON ungueltig: {path}: {exc}") from exc
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict) and isinstance(value.get("records"), list):
            return len(value["records"])
    return 1


def _validate_artifacts(bundle: Path, artifacts: Any, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(artifacts, dict) or not artifacts:
        raise CompletionError(f"{label}.artifacts muss nichtleeres Objekt sein")
    validated: dict[str, dict[str, Any]] = {}
    refs: set[str] = set()
    for key, descriptor in artifacts.items():
        if not isinstance(key, str) or not key or not isinstance(descriptor, dict):
            raise CompletionError(f"{label} Artifactdeskriptor ungueltig: {key!r}")
        if set(descriptor) != DESCRIPTOR_FIELDS:
            raise CompletionError(f"{label} Artifactdeskriptor-Feldmenge ungueltig: {key}")
        ref = _safe_ref(descriptor["ref"]).as_posix()
        if ref.casefold() in refs:
            raise CompletionError(f"{label} Artifact-Ref doppelt: {ref}")
        refs.add(ref.casefold())
        source = _safe_source(bundle, ref)
        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if descriptor["sha256"] != digest or not FULL_SHA256.fullmatch(str(descriptor["sha256"])):
            raise CompletionError(f"{label} Artifact-SHA256 falsch: {key}")
        if descriptor["artifact_id"] != f"sha256:{digest}":
            raise CompletionError(f"{label} artifact_id falsch: {key}")
        if type(descriptor["bytes"]) is not int or descriptor["bytes"] != len(payload):
            raise CompletionError(f"{label} Artifact-Bytes falsch: {key}")
        if type(descriptor["record_count"]) is not int or descriptor["record_count"] != _record_count(source, payload):
            raise CompletionError(f"{label} Artifact-record_count falsch: {key}")
        validated[key] = descriptor
    return validated


def _validate_external_contracts(
    bundle: Path, audit: dict[str, Any], evidence: dict[str, Any],
    expected_audit_sha: str, expected_evidence_sha: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    for expected, label in ((expected_audit_sha, "Auditcontract-SHA"), (expected_evidence_sha, "Evidence-Contract-SHA")):
        if not isinstance(expected, str) or not FULL_SHA256.fullmatch(expected):
            raise CompletionError(f"{label} muss externe lowercase SHA256 sein")
    if set(audit) != AUDIT_CONTRACT_FIELDS:
        raise CompletionError("Auditcontract-Feldmenge ungueltig")
    if set(evidence) != EVIDENCE_CONTRACT_FIELDS:
        raise CompletionError("Evidence-Contract-Feldmenge ungueltig")
    if not isinstance(audit.get("artifacts"), dict) or set(audit["artifacts"]) != AUDIT_ARTIFACT_KEYS:
        raise CompletionError("Auditcontract-Artifactmenge muss exakte 14er-Union sein")
    if not isinstance(evidence.get("artifacts"), dict):
        raise CompletionError("Evidence-Contract artifacts muss Objekt sein")
    evidence_keys = set(evidence["artifacts"])
    dynamic_keys = evidence_keys - EVIDENCE_STATIC_KEYS
    if not EVIDENCE_STATIC_KEYS <= evidence_keys or any(not ATTACHMENT_KEY.fullmatch(key) for key in dynamic_keys):
        raise CompletionError("Evidence-Contract Artifactmenge enthaelt fehlende oder fremde Keys")
    audit_body = {key: value for key, value in audit.items() if key != "contract_sha256"}
    evidence_body = {key: value for key, value in evidence.items() if key != "evidence_contract_sha256"}
    calculated_audit = hashlib.sha256(_canonical_bytes(audit_body)).hexdigest()
    calculated_evidence = hashlib.sha256(_canonical_bytes(evidence_body)).hexdigest()
    if audit.get("contract_sha256") != expected_audit_sha or calculated_audit != expected_audit_sha:
        raise CompletionError("Auditcontract-Body-SHA stimmt nicht mit externem Pin")
    if evidence.get("evidence_contract_sha256") != expected_evidence_sha or calculated_evidence != expected_evidence_sha:
        raise CompletionError("Evidence-Contract-Body-SHA stimmt nicht mit externem Pin")
    common = ("plan_id", "run_id", "audited_commit", "tooling_commit", "snapshot_id")
    if audit.get("schema_version") != 1 or evidence.get("schema_version") != 1:
        raise CompletionError("Contract schema_version muss 1 sein")
    if audit.get("plan_id") != PLAN_ID or any(evidence.get(field) != audit.get(field) for field in common):
        raise CompletionError("Audit-/Evidence-Contract Bindung falsch")
    if not FULL_COMMIT.fullmatch(str(audit.get("audited_commit"))) or not FULL_COMMIT.fullmatch(str(audit.get("tooling_commit"))):
        raise CompletionError("Auditcontract Commitbindung ungueltig")
    if evidence.get("audit_contract_sha256") != expected_audit_sha:
        raise CompletionError("Evidence-Contract referenziert falschen Auditcontract")
    frozen = _aware_time(audit.get("frozen_at"), "frozen_at")
    expires = _aware_time(audit.get("expires_at"), "expires_at")
    completed = _aware_time(evidence.get("completed_at"), "completed_at")
    if not frozen <= completed <= expires:
        raise CompletionError("Evidence completed_at liegt ausserhalb Freeze-/TTL-Fenster")
    audit_artifacts = _validate_artifacts(bundle, audit["artifacts"], "Auditcontract")
    evidence_artifacts = _validate_artifacts(bundle, evidence["artifacts"], "Evidence-Contract")
    refs = [item["ref"].casefold() for item in [*audit_artifacts.values(), *evidence_artifacts.values()]]
    if len(refs) != len(set(refs)):
        raise CompletionError("Audit-/Evidence-Artifact-Ref mehrfach konsumiert")
    return audit_artifacts, evidence_artifacts


def _proof_attachment(
    row: dict[str, Any], prefix: str, evidence_artifacts: dict[str, dict[str, Any]],
    expected: set[str], label: str,
) -> None:
    evidence_id, proof_ref, proof_sha = row.get("evidence_id"), row.get("proof_ref"), row.get("proof_sha256")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise CompletionError(f"{label}: evidence_id fehlt/ungueltig")
    if not isinstance(proof_ref, str) or not proof_ref or not FULL_SHA256.fullmatch(str(proof_sha)):
        raise CompletionError(f"{label}: proof_ref/proof_sha256 fehlt/ungueltig")
    key = f"{prefix}:{evidence_id}"
    if key in expected:
        raise CompletionError(f"{label}: Proof mehrfach konsumiert: {key}")
    descriptor = evidence_artifacts.get(key)
    if descriptor is None or descriptor["ref"] != proof_ref or descriptor["sha256"] != proof_sha:
        raise CompletionError(f"{label}: Proof-Descriptor/FK falsch: {key}")
    expected.add(key)


def _validate_attachment_closure(
    bundle: Path, audit_artifacts: dict[str, dict[str, Any]],
    evidence_artifacts: dict[str, dict[str, Any]], rows_by_key: dict[str, list[dict[str, Any]]],
) -> None:
    expected = set(EVIDENCE_STATIC_KEYS)
    for number, row in enumerate(rows_by_key["feature-state-evidence"], 1):
        _proof_attachment(row, "feature-proof", evidence_artifacts, expected, f"Feature-Evidence {number}")
    for number, row in enumerate(rows_by_key["symbol-state-evidence"], 1):
        kind = row.get("evidence_kind")
        if not isinstance(kind, str) or kind not in {"symbol-review", "edge-review"}:
            raise CompletionError(
                f"Symbol-Evidence {number}: nur non-runtime symbol-review/edge-review erlaubt"
            )
        _proof_attachment(row, "symbol-proof", evidence_artifacts, expected, f"Symbol-Evidence {number}")
    for number, row in enumerate(rows_by_key["runtime-evidence"], 1):
        _proof_attachment(row, "runtime-proof", evidence_artifacts, expected, f"Runtime-Evidence {number}")

    roster_by_reviewer: dict[str, dict[str, Any]] = {}
    sessions: set[str] = set()
    for number, row in enumerate(rows_by_key["reviewer-roster"], 1):
        session_id, reviewer_id = row.get("session_id"), row.get("reviewer_id")
        if not isinstance(session_id, str) or not session_id or session_id in sessions:
            raise CompletionError(f"Reviewer-Roster {number}: session_id fehlt/doppelt")
        if not isinstance(reviewer_id, str) or not reviewer_id or reviewer_id in roster_by_reviewer:
            raise CompletionError(f"Reviewer-Roster {number}: reviewer_id fehlt/doppelt")
        receipt_ref, receipt_sha = row.get("session_receipt_ref"), row.get("session_receipt_sha256")
        signature_ref = row.get("session_receipt_signature_ref")
        if not isinstance(receipt_ref, str) or not FULL_SHA256.fullmatch(str(receipt_sha)) or not isinstance(signature_ref, str):
            raise CompletionError(f"Reviewer-Roster {number}: Enrollment-FKs fehlen/ungueltig")
        receipt_key = f"reviewer-enrollment-receipt:{session_id}"
        signature_key = f"reviewer-enrollment-signature:{session_id}"
        receipt_descriptor = evidence_artifacts.get(receipt_key)
        signature_descriptor = evidence_artifacts.get(signature_key)
        if receipt_descriptor is None or receipt_descriptor["ref"] != receipt_ref or receipt_descriptor["sha256"] != receipt_sha:
            raise CompletionError(f"Reviewer-Roster {number}: Enrollment-Receipt-FK falsch")
        if signature_descriptor is None or signature_descriptor["ref"] != signature_ref:
            raise CompletionError(f"Reviewer-Roster {number}: Enrollment-Signature-FK falsch")
        expected |= {receipt_key, signature_key}
        sessions.add(session_id)
        roster_by_reviewer[reviewer_id] = row

    reviewer_descriptor = audit_artifacts["reviewer-contract"]
    reviewer_payload = _safe_source(bundle, reviewer_descriptor["ref"]).read_bytes()
    if hashlib.sha256(reviewer_payload).hexdigest() != reviewer_descriptor["sha256"]:
        raise CompletionError("Reviewer-Contract wurde nach Artifactvalidierung veraendert")
    reviewer_contract = _read_json_bytes(reviewer_payload, "reviewer-contract")
    reviewers, required_signoffs = reviewer_contract.get("reviewers"), reviewer_contract.get("required_signoffs")
    if not isinstance(reviewers, list) or not isinstance(required_signoffs, list):
        raise CompletionError("Reviewer-Contract Reviewer/Signoff-Mengen fehlen")
    contract_sessions: dict[str, str] = {}
    for item in reviewers:
        if not isinstance(item, dict) or not isinstance(item.get("reviewer_id"), str) or not isinstance(item.get("session_id"), str):
            raise CompletionError("Reviewer-Contract Reviewer-FK ungueltig")
        if item["reviewer_id"] in contract_sessions:
            raise CompletionError("Reviewer-Contract Reviewer doppelt")
        contract_sessions[item["reviewer_id"]] = item["session_id"]
    seen_signoffs: set[tuple[str, str]] = set()
    for item in required_signoffs:
        if not isinstance(item, dict):
            raise CompletionError("Reviewer-Contract required_signoff ungueltig")
        reviewer_id, role = item.get("reviewer_id"), item.get("role")
        if not isinstance(reviewer_id, str) or not reviewer_id or not isinstance(role, str) or not role:
            raise CompletionError("Reviewer-Contract required_signoff Typ/Feld falsch")
        session_id = contract_sessions.get(reviewer_id)
        if not session_id or reviewer_id not in roster_by_reviewer or roster_by_reviewer[reviewer_id]["session_id"] != session_id:
            raise CompletionError("Reviewer-Contract Signoff-Roster-FK falsch")
        pair = (role, session_id)
        if pair in seen_signoffs:
            raise CompletionError("Reviewer-Contract required_signoff fehlt/doppelt")
        seen_signoffs.add(pair)
        expected |= {f"reviewer-signoff:{role}:{session_id}", f"reviewer-signoff-signature:{role}:{session_id}"}
    if set(evidence_artifacts) != expected:
        raise CompletionError(
            "Evidence-Attachment-Exact-Closure verletzt: "
            f"fehlend={sorted(expected - set(evidence_artifacts))!r}, "
            f"fremd={sorted(set(evidence_artifacts) - expected)!r}"
        )


def _validate_bundle(
    bundle: Path, contract: dict[str, Any], audit: dict[str, Any], evidence: dict[str, Any],
    expected_audit_sha: str, expected_evidence_sha: str,
) -> tuple[list[tuple[dict[str, Any], Path, bytes]], dict[str, dict[str, Any]]]:
    audit_artifacts, evidence_artifacts = _validate_external_contracts(
        bundle, audit, evidence, expected_audit_sha, expected_evidence_sha
    )
    if set(contract) != ATOMIC_CONTRACT_FIELDS:
        raise CompletionError("Atomic-Import-Feldmenge ungueltig")
    if contract["schema_version"] != 1:
        raise CompletionError("schema_version muss 1 sein")
    for field in ("import_id", "run_id", "snapshot_id"):
        if not isinstance(contract[field], str) or not contract[field].strip():
            raise CompletionError(f"{field} muss nichtleerer String sein")
    if not SAFE_IMPORT_ID.fullmatch(contract["import_id"]):
        raise CompletionError("import_id muss sichere einzelne Komponente mit Praefix IMPORT- sein")
    if not FULL_COMMIT.fullmatch(str(contract["audited_commit"])) or not FULL_COMMIT.fullmatch(str(contract["tooling_commit"])):
        raise CompletionError("Atomic-Import Commitbindung ungueltig")
    for field in ("run_id", "audited_commit", "tooling_commit", "snapshot_id"):
        if contract[field] != audit[field]:
            raise CompletionError(f"Atomic-Import-Bindung {field} falsch")
    if contract["audit_contract_sha256"] != expected_audit_sha or contract["evidence_contract_sha256"] != expected_evidence_sha:
        raise CompletionError("Atomic-Import Contract-SHA-Bindung falsch")
    qualification = contract["qualification"]
    if not isinstance(qualification, str) or qualification not in {"unqualified", "qualified-partial"}:
        raise CompletionError("qualification ungueltig")
    gates = contract["required_gate_results"]
    if not isinstance(gates, dict) or set(gates) != REQUIRED_GATES or any(gates[name] is not True for name in REQUIRED_GATES):
        raise CompletionError("required_gate_results muss exakte Sechsermenge mit True sein")
    specs = contract["shards"]
    if not isinstance(specs, list) or len(specs) != len(EVIDENCE_STATIC_KEYS):
        raise CompletionError("shards muss exakte statische Achtermenge sein")

    validated: list[tuple[dict[str, Any], Path, bytes]] = []
    rows_by_name: dict[str, list[dict[str, Any]]] = {}
    rows_by_key: dict[str, list[dict[str, Any]]] = {}
    keys_by_name: dict[str, set[str]] = {}
    names: set[str] = set()
    paths: set[str] = set()
    for index, spec in enumerate(specs, 1):
        if not isinstance(spec, dict) or set(spec) != SHARD_SPEC_FIELDS:
            raise CompletionError(f"Shard {index}: Feldmenge ungueltig")
        name, artifact_key = spec["name"], spec["artifact_key"]
        if not isinstance(name, str) or not name or name in names:
            raise CompletionError(f"Doppelte oder ungueltige Shard-ID: {name!r}")
        if not isinstance(artifact_key, str) or artifact_key not in EVIDENCE_STATIC_KEYS or artifact_key in rows_by_key:
            raise CompletionError(f"Statische Evidence-Artifact-ID fehlt/doppelt: {artifact_key!r}")
        names.add(name)
        source = _safe_source(bundle, spec["path"])
        ref = _safe_ref(spec["path"]).as_posix()
        if ref.casefold() in paths:
            raise CompletionError(f"Staging-Zielpfad doppelt: {ref}")
        paths.add(ref.casefold())
        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if spec["sha256"] != digest:
            raise CompletionError(f"SHA256 stimmt nicht: {name}")
        descriptor = evidence_artifacts[artifact_key]
        if descriptor["ref"] != ref or descriptor["sha256"] != digest:
            raise CompletionError(f"Evidence-Artifact-Bindung falsch: {name}")
        rows = _read_jsonl(source)
        if type(spec["record_count"]) is not int or spec["record_count"] != len(rows):
            raise CompletionError(f"record_count stimmt nicht: {name}")
        primary_key = spec["primary_key"]
        if not isinstance(primary_key, list) or not primary_key or not all(isinstance(field, str) and field for field in primary_key):
            raise CompletionError(f"primary_key ungueltig: {name}")
        shard_keys: set[str] = set()
        for row_number, row in enumerate(rows, 1):
            bindings = ("run_id",) if artifact_key == "delta-ledger" else ("run_id", "snapshot_id")
            for binding in bindings:
                if row.get(binding) != contract[binding]:
                    raise CompletionError(f"Bindung {binding} falsch: {name}:{row_number}")
            commit_value = row.get("base_commit") if artifact_key == "delta-ledger" else row.get("audited_commit")
            if commit_value != contract["audited_commit"]:
                raise CompletionError(f"Bindung audited_commit falsch: {name}:{row_number}")
            if artifact_key == "delta-ledger":
                if set(row) != DELTA_RECORD_FIELDS:
                    raise CompletionError(f"Delta-Ledger Feldmenge falsch: {name}:{row_number}")
                if (
                    not FULL_COMMIT.fullmatch(str(row.get("head_commit")))
                    or not isinstance(row.get("path"), str) or not row["path"]
                    or not isinstance(row.get("change"), str) or not row["change"]
                    or type(row.get("product_relevant")) is not bool
                    or not isinstance(row.get("disposition"), str)
                    or row["disposition"] not in DELTA_DISPOSITIONS
                    or not isinstance(row.get("reviewer_id"), str) or not row["reviewer_id"].strip()
                ):
                    raise CompletionError(f"Delta-Ledger Typ/Disposition falsch: {name}:{row_number}")
                _aware_time(row.get("signed_at"), f"Delta-Ledger signed_at {name}:{row_number}")
                if row["product_relevant"] is True:
                    raise CompletionError(f"Produktrelevantes Delta blockiert Completion: {name}:{row_number}")
            if any(field not in row for field in primary_key):
                raise CompletionError(f"Primaerschluessel unvollstaendig: {name}:{row_number}")
            key = _canonical_key([row[field] for field in primary_key])
            if key in shard_keys:
                raise CompletionError(f"Doppelte ID: {name}:{row_number}")
            shard_keys.add(key)
            if qualification == "unqualified" and _contains_unknown(row):
                raise CompletionError(f"UNKNOWN blockiert unqualifizierte Completion: {name}:{row_number}")
        rows_by_name[name], rows_by_key[artifact_key], keys_by_name[name] = rows, rows, shard_keys
        validated.append((spec, source, payload))
    if set(rows_by_key) != EVIDENCE_STATIC_KEYS:
        raise CompletionError("Import-Shards entsprechen nicht exakter statischer Achtermenge")

    for spec, _source, _payload in validated:
        foreign_keys = spec["foreign_keys"]
        if not isinstance(foreign_keys, list):
            raise CompletionError(f"foreign_keys muss Liste sein: {spec['name']}")
        for relation in foreign_keys:
            if not isinstance(relation, dict) or set(relation) != {"field", "target_shard", "target_fields"}:
                raise CompletionError(f"Fremdschluesselvertrag ungueltig: {spec['name']}")
            field, target, target_fields = relation["field"], relation["target_shard"], relation["target_fields"]
            if (
                not isinstance(field, str) or not field
                or not isinstance(target, str) or not target
                or not isinstance(target_fields, list) or not target_fields
                or not all(isinstance(item, str) and item for item in target_fields)
                or target not in rows_by_name
            ):
                raise CompletionError(f"Fremdschluesselziel ungueltig: {spec['name']}")
            target_spec = next(item for item, _p, _b in validated if item["name"] == target)
            if target_fields != target_spec["primary_key"]:
                raise CompletionError(f"Fremdschluesselfelder entsprechen nicht Zielschluessel: {spec['name']}")
            for row_number, row in enumerate(rows_by_name[spec["name"]], 1):
                value = row.get(field)
                parts = value if isinstance(value, list) else [value]
                if len(parts) != len(target_fields) or _canonical_key(parts) not in keys_by_name[target]:
                    raise CompletionError(f"Fremdschluessel nicht aufloesbar: {spec['name']}:{row_number}")
    runtime_by_id: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(rows_by_key["runtime-evidence"], 1):
        evidence_id = row.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id or evidence_id in runtime_by_id:
            raise CompletionError(f"Runtime-Evidence {number}: evidence_id fehlt/doppelt")
        covered_symbols = row.get("covered_symbol_ids")
        if (
            not isinstance(covered_symbols, list) or not covered_symbols
            or any(not isinstance(value, str) or not value for value in covered_symbols)
            or len(covered_symbols) != len(set(covered_symbols))
        ):
            raise CompletionError(f"Runtime-Evidence {number}: covered_symbol_ids Typ/Menge ungueltig")
        runtime_by_id[evidence_id] = row
    consumers: dict[str, set[str]] = {evidence_id: set() for evidence_id in runtime_by_id}
    symbol_ids: set[str] = set()
    for number, row in enumerate(rows_by_key["symbol-state"], 1):
        symbol_id = row.get("symbol_id")
        if not isinstance(symbol_id, str) or not symbol_id or symbol_id in symbol_ids:
            raise CompletionError(f"Symbol-State {number}: symbol_id fehlt/doppelt")
        symbol_ids.add(symbol_id)
        runtime_ids = row.get("runtime_evidence_ids")
        if (
            not isinstance(runtime_ids, list)
            or any(not isinstance(value, str) or not value for value in runtime_ids)
            or len(runtime_ids) != len(set(runtime_ids))
        ):
            raise CompletionError(f"Symbol-State {number}: runtime_evidence_ids Typ/Menge ungueltig")
        foreign = set(runtime_ids) - set(runtime_by_id)
        if foreign:
            raise CompletionError(f"Symbol-State {number}: Runtime-Evidence-FK fremd: {sorted(foreign)!r}")
        for evidence_id in runtime_ids:
            if symbol_id not in runtime_by_id[evidence_id]["covered_symbol_ids"]:
                raise CompletionError(
                    f"Symbol-State {number}: Runtime-Evidence deckt Symbol nicht: {evidence_id}"
                )
            consumers[evidence_id].add(symbol_id)
    for evidence_id, runtime in runtime_by_id.items():
        expected_symbols = set(runtime["covered_symbol_ids"])
        if consumers[evidence_id] != expected_symbols:
            raise CompletionError(
                f"Runtime-Evidence Symbol-Closure falsch {evidence_id}: "
                f"fehlend={sorted(expected_symbols - consumers[evidence_id])!r}, "
                f"fremd={sorted(consumers[evidence_id] - expected_symbols)!r}"
            )
    _validate_attachment_closure(bundle, audit_artifacts, evidence_artifacts, rows_by_key)
    return validated, evidence_artifacts


def _buffer_artifacts(
    bundle: Path,
    artifacts: dict[str, dict[str, Any]],
    label: str,
    copies: dict[str, bytes],
) -> None:
    destinations = {value.casefold() for value in copies}
    for key, descriptor in artifacts.items():
        ref = _safe_ref(descriptor["ref"]).as_posix()
        if ref.casefold() in destinations:
            raise CompletionError(f"{label} Importziel doppelt: {ref}")
        source = _safe_source(bundle, ref)
        payload = source.read_bytes()
        if (
            hashlib.sha256(payload).hexdigest() != descriptor["sha256"]
            or len(payload) != descriptor["bytes"]
            or _record_count(source, payload) != descriptor["record_count"]
        ):
            raise CompletionError(f"{label} Artifact nach Validierung veraendert: {key}")
        copies[ref] = payload
        destinations.add(ref.casefold())


@contextmanager
def _import_lock(master: Path):
    master.mkdir(parents=True, exist_ok=True)
    path = master / ".atomic-import.lock"
    payload = _canonical_bytes({"token": uuid.uuid4().hex, "pid": os.getpid()})
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise CompletionError("Atomic-Import durch fremden Ownership-Lock blockiert") from exc
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        yield payload
    finally:
        try:
            current = path.read_bytes()
        except FileNotFoundError as exc:
            raise CompletionError("Atomic-Import Lock-Ownership verloren") from exc
        if current != payload:
            raise CompletionError("Atomic-Import fremden Lock nicht entfernt")
        try:
            path.unlink()
        except OSError as exc:
            raise CompletionError("Atomic-Import eigenen Lock nicht freigebbar") from exc


def import_bundle(
    bundle_dir: Path | str, contract_path: Path | str, master_root: Path | str, *,
    audit_contract_path: Path | str, evidence_contract_path: Path | str,
    expected_audit_contract_sha256: str, expected_evidence_contract_sha256: str,
) -> dict[str, Any]:
    bundle = Path(bundle_dir).resolve()
    contract_file, audit_file, evidence_file = (
        Path(contract_path).absolute(), Path(audit_contract_path).absolute(),
        Path(evidence_contract_path).absolute(),
    )
    master = Path(master_root).resolve()
    if not bundle.is_dir():
        raise CompletionError(f"Bundle fehlt: {bundle}")
    contract_ref = _bundle_file_ref(bundle, contract_file, "Atomic-Contract")
    audit_ref = _bundle_file_ref(bundle, audit_file, "Auditcontract")
    evidence_ref = _bundle_file_ref(bundle, evidence_file, "Evidence-Contract")
    try:
        contract_bytes = contract_file.read_bytes()
        audit_bytes = audit_file.read_bytes()
        evidence_bytes = evidence_file.read_bytes()
    except OSError as exc:
        raise CompletionError(f"Contractdatei unlesbar: {exc}") from exc
    contract = _read_json_bytes(contract_bytes, str(contract_file))
    audit = _read_json_bytes(audit_bytes, str(audit_file))
    evidence = _read_json_bytes(evidence_bytes, str(evidence_file))
    validated, evidence_artifacts = _validate_bundle(
        bundle, contract, audit, evidence, expected_audit_contract_sha256,
        expected_evidence_contract_sha256,
    )

    audit_artifacts = _validate_artifacts(bundle, audit["artifacts"], "Auditcontract")
    copies: dict[str, bytes] = {}
    _buffer_artifacts(bundle, audit_artifacts, "Auditcontract", copies)
    _buffer_artifacts(bundle, evidence_artifacts, "Evidence-Contract", copies)
    for ref, payload in (
        (contract_ref.as_posix(), contract_bytes),
        (audit_ref.as_posix(), audit_bytes),
        (evidence_ref.as_posix(), evidence_bytes),
    ):
        if ref.casefold() in {item.casefold() for item in copies}:
            raise CompletionError(f"Contract-Ziel kollidiert mit Artifact-Ref: {ref}")
        copies[ref] = payload
    if len(copies) != len(audit_artifacts) + len(evidence_artifacts) + 3:
        raise CompletionError("Import-Zielpfade kollidieren")

    import_id = contract["import_id"]
    with _import_lock(master):
        versions = master / "versions"
        versions.mkdir(parents=True, exist_ok=True)
        version = versions / import_id
        if version.exists():
            raise CompletionError(f"Import-ID existiert bereits: {import_id}")
        token = uuid.uuid4().hex
        owner_payload = token.encode("ascii")
        owner_name = ".atomic-import-owner"
        staging = master / f".staging-{token}"
        pointer_tmp = master / f".CURRENT-{token}.tmp"
        owned_version = False
        pointer_swapped = False
        try:
            staging.mkdir()
            (staging / owner_name).write_bytes(owner_payload)
            for ref, payload in sorted(copies.items()):
                target = staging.joinpath(*PurePosixPath(ref).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
            os.replace(staging, version)
            owned_version = True
            pointer_tmp.write_text(f"{import_id}\n", encoding="utf-8", newline="\n")
            try:
                os.replace(pointer_tmp, master / "CURRENT")
                pointer_swapped = True
            except OSError as exc:
                raise CompletionError(f"Atomarer Pointerwechsel fehlgeschlagen: {exc}") from exc
            try:
                (version / owner_name).unlink()
            except OSError as exc:
                raise CompletionError("Import-Ownership-Marker nicht entfernbar") from exc
        except Exception:
            if pointer_tmp.exists():
                pointer_tmp.unlink()
            if staging.exists():
                shutil.rmtree(staging)
            if owned_version and not pointer_swapped and version.exists():
                marker = version / owner_name
                try:
                    still_owned = marker.is_file() and marker.read_bytes() == owner_payload
                except OSError:
                    still_owned = False
                if still_owned:
                    shutil.rmtree(version)
            raise
    return {
        "status": "imported", "import_id": import_id, "run_id": contract["run_id"],
        "audited_commit": contract["audited_commit"], "snapshot_id": contract["snapshot_id"],
        "shard_count": len(validated),
        "attachment_count": len(evidence_artifacts) - len(EVIDENCE_STATIC_KEYS),
        "audit_artifact_count": len(audit_artifacts),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validiert Global Contract V1 und schaltet Masterledger atomar um.")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--master", required=True, type=Path)
    parser.add_argument("--audit-contract", required=True, type=Path)
    parser.add_argument("--evidence-contract", required=True, type=Path)
    parser.add_argument("--expected-audit-contract-sha256", required=True)
    parser.add_argument("--expected-evidence-contract-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = import_bundle(
            args.bundle, args.contract, args.master, audit_contract_path=args.audit_contract,
            evidence_contract_path=args.evidence_contract,
            expected_audit_contract_sha256=args.expected_audit_contract_sha256,
            expected_evidence_contract_sha256=args.expected_evidence_contract_sha256,
        )
    except CompletionError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
