#!/usr/bin/env python3
"""Validate frozen-audit TTL and exact Git delta disposition."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FULL_SHA = re.compile(r"[0-9a-f]{40}")
REQUIRED_CONTRACT = {
    "schema_version", "run_id", "audited_commit", "integration_head",
    "snapshot_id", "frozen_at", "max_age_seconds",
}


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True).stdout


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
    root: Path, base: str, head: str, *, run_id: str, snapshot_id: str,
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
            old_path, path = fields[index], fields[index + 1]
            index += 2
        else:
            if index >= len(fields):
                raise ValueError("Git-Diff Pfad fehlt")
            old_path, path = None, fields[index]
            index += 1
        row: dict[str, Any] = {
            "run_id": run_id, "snapshot_id": snapshot_id,
            "base_commit": base, "head_commit": head,
            "status": status, "path": path,
        }
        if old_path is not None:
            row["old_path"] = old_path
        rows.append(row)
    return rows


def _key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("status", "")), str(row.get("old_path", "")), str(row.get("path", "")))


def verify_delta_ttl(
    root: Path, contract: dict[str, Any], rows: list[dict[str, Any]], *,
    now: datetime | None = None,
) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    missing = sorted(REQUIRED_CONTRACT - set(contract))
    if missing:
        errors.append(f"Auditvertrag Pflichtfelder fehlen: {missing}")
    if contract.get("schema_version") != 1:
        errors.append("schema_version muss 1 sein")
    run_id = str(contract.get("run_id", "")).strip()
    snapshot_id = str(contract.get("snapshot_id", "")).strip()
    if not run_id:
        errors.append("run_id fehlt/leer")
    if not snapshot_id:
        errors.append("snapshot_id fehlt/leer")
    base = _resolve_commit(root, contract.get("audited_commit"), "audited_commit", errors)
    head = _resolve_commit(root, contract.get("integration_head"), "integration_head", errors)

    try:
        frozen = datetime.fromisoformat(str(contract.get("frozen_at", "")).replace("Z", "+00:00"))
        if frozen.tzinfo is None:
            raise ValueError("timezone fehlt")
    except ValueError as exc:
        frozen = None
        errors.append(f"frozen_at ungueltig: {exc}")
    max_age = contract.get("max_age_seconds")
    if type(max_age) is not int or max_age <= 0:
        errors.append("max_age_seconds muss positiver Integer sein")
    elif frozen is not None:
        checked_at = now or datetime.now(timezone.utc)
        if checked_at.tzinfo is None:
            errors.append("now muss timezone-aware sein")
        elif (checked_at - frozen).total_seconds() > max_age:
            errors.append("Audit-TTL ist abgelaufen")

    expected: list[dict[str, Any]] = []
    if base and head:
        try:
            expected = expected_delta(root, base, head, run_id=run_id, snapshot_id=snapshot_id)
        except (subprocess.CalledProcessError, UnicodeError, ValueError) as exc:
            errors.append(f"Git-Diff unlesbar: {exc}")
    seen: set[tuple[str, str, str]] = set()
    for number, row in enumerate(rows, 1):
        label = f"Delta Zeile {number}"
        if not isinstance(row, dict):
            errors.append(f"{label}: Objekt erwartet")
            continue
        key = _key(row)
        if key in seen:
            errors.append(f"{label}: Delta-ID/Pfad doppelt {key!r}")
        seen.add(key)
        if row.get("run_id") != run_id or row.get("snapshot_id") != snapshot_id:
            errors.append(f"{label}: Run-/Snapshotbindung falsch")
        if row.get("base_commit") != base or row.get("head_commit") != head:
            errors.append(f"{label}: Commitbindung falsch")
        if type(row.get("product_relevant")) is not bool:
            errors.append(f"{label}: product_relevant muss Boolean sein")
        if not str(row.get("decision_ref", "")).strip() or not str(row.get("reviewer_id", "")).strip():
            errors.append(f"{label}: decision_ref/reviewer_id fuer Disposition fehlen")
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
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Zeile {number}: Objekt erwartet")
        rows.append(value)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--delta-ledger", type=Path, required=True)
    parser.add_argument("--now", help="timezone-aware ISO-8601 fuer reproduzierbare Revalidierung")
    args = parser.parse_args()
    try:
        contract = json.loads(args.contract.read_text(encoding="utf-8"))
        rows = _load_jsonl(args.delta_ledger)
        checked_at = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else None
        errors = verify_delta_ttl(args.root, contract, rows, now=checked_at)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        errors = [f"Eingabe unlesbar: {exc}"]
    print(json.dumps({"ok": not errors, "error_count": len(errors), "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
