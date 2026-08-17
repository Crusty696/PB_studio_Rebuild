#!/usr/bin/env python3
"""Validate Global Contract V1 TTL and exact Git delta disposition."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PLAN_ID = "PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15"
FULL_SHA = re.compile(r"[0-9a-f]{40}")
FULL_SHA256 = re.compile(r"[0-9a-f]{64}")
AUDIT_FIELDS = {
    "schema_version", "plan_id", "run_id", "audited_commit", "tooling_commit",
    "snapshot_id", "frozen_at", "expires_at", "artifacts", "contract_sha256",
}
AUDIT_ARTIFACT_KEYS = {
    "requirements-universe", "trigger-universe", "feature-catalog",
    "symbol-catalog", "edge-catalog", "runtime-scenario-catalog",
    "runtime-feature-universe", "runtime-symbol-universe",
    "runtime-executor-manifest", "runtime-dependency-manifest",
    "reviewer-trust-policy", "reviewer-contract",
    "reviewer-readiness-binding", "reviewer-spawn-journal",
}
DELTA_FIELDS = {
    "run_id", "base_commit", "head_commit", "path", "change",
    "product_relevant", "disposition", "reviewer_id", "signed_at",
}
DISPOSITIONS = {"report-only", "reaudit-required", "explicit-user-exclusion"}
STATUS_CHANGES = {
    "A": "added", "M": "modified", "D": "deleted", "T": "type-changed",
    "R": "renamed", "C": "copied", "U": "unmerged",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _git(root: Path, *args: str) -> bytes:
    environment = os.environ.copy()
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, env=environment,
    ).stdout


def _resolve_commit(root: Path, value: object, label: str, errors: list[str]) -> str:
    text = str(value or "")
    if not FULL_SHA.fullmatch(text):
        errors.append(f"{label} muss volle lowercase 40-Zeichen-SHA sein")
        return ""
    try:
        resolved = _git(root, "rev-parse", "--verify", f"{text}^{{commit}}").decode().strip()
    except subprocess.CalledProcessError:
        errors.append(f"{label} existiert nicht als Gitcommit")
        return ""
    if resolved != text:
        errors.append(f"{label} ist nicht kanonisch")
        return ""
    return text


def expected_delta(
    root: Path, base: str, head: str, *, run_id: str,
) -> list[dict[str, Any]]:
    raw = _git(root, "diff", "--name-status", "-z", "--find-renames", base, head)
    fields = raw.decode("utf-8", "surrogateescape").split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    rows: list[dict[str, Any]] = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        if not status:
            raise ValueError("Git-Diff enthaelt leeren Status")
        if status.startswith(("R", "C")):
            if index + 1 >= len(fields):
                raise ValueError("Git-Diff Rename/Copy unvollstaendig")
            _old_path, path = fields[index], fields[index + 1]
            index += 2
        else:
            if index >= len(fields):
                raise ValueError("Git-Diff Pfad fehlt")
            path = fields[index]
            index += 1
        if status[0] not in STATUS_CHANGES:
            raise ValueError(f"Git-Diff Status unbekannt: {status}")
        change = STATUS_CHANGES[status[0]]
        row: dict[str, Any] = {
            "run_id": run_id, "base_commit": base, "head_commit": head,
            "path": path, "change": change,
        }
        rows.append(row)
    return rows


def _key(row: dict[str, Any]) -> tuple[str, str]:
    return (str(row.get("change", "")), str(row.get("path", "")))


def _time(value: Any, label: str, errors: list[str]) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone fehlt")
        return parsed
    except ValueError as exc:
        errors.append(f"{label} ungueltig: {exc}")
        return None


def verify_delta_ttl(
    root: Path,
    audit_contract: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    integration_head: str,
    expected_audit_contract_sha256: str,
    now: datetime | None = None,
) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    if not isinstance(audit_contract, dict):
        return ["Auditcontract muss Objekt sein"]
    if set(audit_contract) != AUDIT_FIELDS:
        errors.append("Auditcontract-Feldmenge ist nicht Global Contract V1")
    if audit_contract.get("schema_version") != 1 or audit_contract.get("plan_id") != PLAN_ID:
        errors.append("Auditcontract Schema/plan_id falsch")
    artifacts = audit_contract.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != AUDIT_ARTIFACT_KEYS:
        errors.append("Auditcontract Artifactmenge ist nicht exakte 14er-Union")
    expected_pin = expected_audit_contract_sha256
    body = {key: value for key, value in audit_contract.items() if key != "contract_sha256"}
    body_sha = hashlib.sha256(_canonical(body)).hexdigest()
    if not isinstance(expected_pin, str) or not FULL_SHA256.fullmatch(expected_pin):
        errors.append("Externer Auditcontract-Body-SHA muss lowercase SHA256 sein")
    elif audit_contract.get("contract_sha256") != expected_pin or body_sha != expected_pin:
        errors.append("Auditcontract-Body-SHA stimmt nicht mit externem Pin")

    run_id = audit_contract.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        errors.append("run_id fehlt/leer")
        run_id = ""
    base = _resolve_commit(root, audit_contract.get("audited_commit"), "audited_commit", errors)
    head = _resolve_commit(root, integration_head, "integration_head", errors)
    if head:
        try:
            current_head = _git(root, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
        except subprocess.CalledProcessError:
            current_head = ""
            errors.append("Current HEAD ist nicht als Commit aufloesbar")
        if current_head != head:
            errors.append("integration_head ist nicht exakt kanonischer Current HEAD")

    frozen = _time(audit_contract.get("frozen_at"), "frozen_at", errors)
    expires = _time(audit_contract.get("expires_at"), "expires_at", errors)
    checked_at = now or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        errors.append("now muss timezone-aware sein")
    elif frozen is not None and expires is not None:
        if expires <= frozen:
            errors.append("expires_at muss nach frozen_at liegen")
        if checked_at < frozen:
            errors.append("Audit-Zeitpunkt liegt vor frozen_at")
        if checked_at > expires:
            errors.append("Audit-TTL ist abgelaufen")

    expected: list[dict[str, Any]] = []
    if base and head:
        try:
            expected = expected_delta(root, base, head, run_id=run_id)
        except (subprocess.CalledProcessError, UnicodeError, ValueError) as exc:
            errors.append(f"Git-Diff unlesbar: {exc}")
    if not isinstance(rows, list):
        errors.append("Delta-Ledger muss Liste sein")
        rows = []
    seen: set[tuple[str, str]] = set()
    for number, row in enumerate(rows, 1):
        label = f"Delta Zeile {number}"
        if not isinstance(row, dict):
            errors.append(f"{label}: Objekt erwartet")
            continue
        if set(row) != DELTA_FIELDS:
            errors.append(f"{label}: Feldmenge ungueltig")
        key = _key(row)
        if key in seen:
            errors.append(f"{label}: Delta-ID/Pfad doppelt {key!r}")
        seen.add(key)
        if row.get("run_id") != run_id:
            errors.append(f"{label}: Runbindung falsch")
        if row.get("base_commit") != base or row.get("head_commit") != head:
            errors.append(f"{label}: Commitbindung falsch")
        if not isinstance(row.get("path"), str) or not row.get("path"):
            errors.append(f"{label}: path fehlt/ungueltig")
        if not isinstance(row.get("change"), str) or not row.get("change"):
            errors.append(f"{label}: change fehlt/ungueltig")
        if type(row.get("product_relevant")) is not bool:
            errors.append(f"{label}: product_relevant muss Boolean sein")
        disposition = row.get("disposition")
        if not isinstance(disposition, str) or disposition not in DISPOSITIONS:
            errors.append(f"{label}: disposition ungueltig")
        if not isinstance(row.get("reviewer_id"), str) or not row["reviewer_id"].strip():
            errors.append(f"{label}: reviewer_id fehlt")
        _time(row.get("signed_at"), f"{label} signed_at", errors)
        if row.get("product_relevant") is True:
            errors.append(f"{label}: produktrelevantes Delta blockiert Abschluss")
    expected_keys = {_key(row) for row in expected}
    actual_keys = {_key(row) for row in rows if isinstance(row, dict)}
    if expected_keys != actual_keys:
        errors.append(
            "Delta-Mengengleichheit verletzt: "
            f"fehlend={sorted(expected_keys - actual_keys)!r}, fremd={sorted(actual_keys - expected_keys)!r}"
        )
    return errors


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            raise ValueError(f"Zeile {number}: Leerzeile unzulaessig")
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Zeile {number}: Objekt erwartet")
        rows.append(value)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--audit-contract", type=Path, required=True)
    parser.add_argument("--audit-contract-sha256", required=True)
    parser.add_argument("--integration-head", required=True)
    parser.add_argument("--delta-ledger", type=Path, required=True)
    args = parser.parse_args()
    try:
        contract = json.loads(args.audit_contract.read_text(encoding="utf-8"))
        if not isinstance(contract, dict):
            raise ValueError("Auditcontract muss Objekt sein")
        rows = _load_jsonl(args.delta_ledger)
        errors = verify_delta_ttl(
            args.root, contract, rows, integration_head=args.integration_head,
            expected_audit_contract_sha256=args.audit_contract_sha256,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors = [f"Eingabe unlesbar: {exc}"]
    print(json.dumps({"ok": not errors, "error_count": len(errors), "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
