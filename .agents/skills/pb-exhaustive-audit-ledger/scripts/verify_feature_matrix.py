from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from build_inventory import _snapshot_basis


AXES = (
    "declared", "configured", "wired", "reachable", "enabled", "executed",
    "result", "persisted", "restart_safe", "error", "cancel", "retry",
    "cleanup", "GPU", "DB", "UI", "live_evidence",
)
VALUES = {"YES", "PARTIAL", "NO", "N-A", "UNKNOWN"}
REQUIRED_FIELDS = (
    "run_id", "feature_id", "path_id", "name", "user_surface", "trigger", "handler",
    "service", "worker", "state_store", "config_keys", "expected_result",
    "evidence_age", "verdict", "blockers", "not_checked", "snapshot_id",
    "commit_sha", "reviewer_id", "signed_at", "states", "overall_state",
)


def _runtime_evidence(cell: dict, commit_sha: str, run_id: str) -> list[dict]:
    return [
        item for item in cell.get("evidence", [])
        if isinstance(item, dict)
        and item.get("kind") == "runtime"
        and item.get("commit_sha") == commit_sha
        and item.get("run_id") == run_id
        and item.get("run_id")
        and item.get("timestamp")
        and item.get("ref")
    ]


def verify_snapshot(
    snapshot: dict,
    inventory: list[dict],
    workspace_units: list[dict],
    current_head: str,
) -> list[str]:
    rows_without_snapshot = [
        {key: value for key, value in row.items() if key != "snapshot_id"}
        for row in inventory
    ]
    computed_snapshot_id = _snapshot_basis(rows_without_snapshot, workspace_units)
    errors = []
    if not snapshot.get("run_id"):
        errors.append("Snapshot-run_id fehlt")
    if snapshot.get("commit_sha") != current_head:
        errors.append("Snapshot-Commit ist nicht Current HEAD")
    if snapshot.get("snapshot_id") != computed_snapshot_id:
        errors.append("Snapshot stimmt nicht mit Inventory/Workspace-Scope")
    return errors


def verify(path: Path, current_head: str, snapshot_id: str, run_id: str) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"Zeile {number}: invalides JSON: {exc}")
            continue
        missing = [key for key in REQUIRED_FIELDS if key not in row]
        if missing:
            errors.append(f"Zeile {number}: Pflichtfelder fehlen: {', '.join(missing)}")
        feature_id = str(row.get("feature_id", "")).strip()
        path_id = str(row.get("path_id", "")).strip()
        key = (feature_id, path_id)
        if not feature_id or not path_id or key in seen:
            errors.append(f"Zeile {number}: fehlender/doppelter Featurepfad {key!r}")
        seen.add(key)
        commit_sha = str(row.get("commit_sha", ""))
        if commit_sha != current_head:
            errors.append(f"{feature_id}/{path_id}: Commit ist nicht Current HEAD")
        if row.get("snapshot_id") != snapshot_id:
            errors.append(f"{feature_id}/{path_id}: snapshot_id stimmt nicht mit Audit-Snapshot")
        if row.get("run_id") != run_id:
            errors.append(f"{feature_id}/{path_id}: run_id stimmt nicht mit Audit-Snapshot")
        for field in ("name", "expected_result", "evidence_age", "verdict", "snapshot_id", "reviewer_id", "signed_at"):
            if not str(row.get(field, "")).strip():
                errors.append(f"{feature_id}/{path_id}: {field} fehlt/leer")
        for field in ("config_keys", "blockers", "not_checked"):
            if not isinstance(row.get(field), list):
                errors.append(f"{feature_id}/{path_id}: {field} muss Liste sein")
        for field in ("user_surface", "trigger", "handler", "service", "worker", "state_store"):
            value = row.get(field)
            if not isinstance(value, (str, list)) or (isinstance(value, str) and not value.strip()):
                errors.append(f"{feature_id}/{path_id}: {field} fehlt oder hat falschen Typ")

        states = row.get("states") or {}
        unknown_axes = set()
        for axis in AXES:
            cell = states.get(axis)
            label = f"{feature_id}/{path_id}:{axis}"
            if not isinstance(cell, dict):
                errors.append(f"{label}: Zelle fehlt")
                continue
            value = cell.get("value")
            evidence = cell.get("evidence")
            if value not in VALUES:
                errors.append(f"{label}: ungueltiger Wert {value!r}")
            if not isinstance(evidence, list) or not evidence:
                errors.append(f"{label}: Evidenz/Begruendung fehlt")
                continue
            for item in evidence:
                if not isinstance(item, dict):
                    errors.append(f"{label}: Evidenz muss Objekt sein")
                    continue
                if not all(item.get(key) for key in ("kind", "ref", "commit_sha", "timestamp", "run_id")):
                    errors.append(f"{label}: Evidenzobjekt unvollstaendig")
                if item.get("commit_sha") != commit_sha:
                    errors.append(f"{label}: Evidenzcommit weicht vom Featurecommit ab")
                if item.get("run_id") != run_id:
                    errors.append(f"{label}: Evidenz-run_id weicht vom Featurelauf ab")
            if value == "N-A" and not any(
                isinstance(item, dict) and item.get("kind") == "n-a" and item.get("reason")
                for item in evidence
            ):
                errors.append(f"{label}: N-A ohne explizite Begruendung")
            if value == "UNKNOWN":
                unknown_axes.add(axis)
                if not any(
                    isinstance(item, dict) and item.get("kind") == "not-checked" and item.get("reason")
                    for item in evidence
                ):
                    errors.append(f"{label}: UNKNOWN ohne not-checked-Grund")
            runtime = _runtime_evidence(cell, commit_sha, run_id)
            if value == "YES" and axis in {"executed", "result", "live_evidence"}:
                if not runtime:
                    errors.append(f"{label}: YES ohne Current-HEAD-Runtimebeleg")
                elif axis in {"result", "live_evidence"} and not any(
                    item.get("input_ref") and item.get("postcondition_ref") for item in runtime
                ):
                    errors.append(f"{label}: Runtimebeleg ohne Input/Postcondition")
            if value == "YES" and axis == "restart_safe" and not any(
                item.get("restart") is True and item.get("reopen") is True for item in runtime
            ):
                errors.append(f"{label}: YES ohne echten Restart/Reopen-Beleg")
            if value == "YES" and axis in {"error", "cancel", "retry"} and not any(
                item.get("forced_state") == axis for item in runtime
            ):
                errors.append(f"{label}: YES ohne erzwungenen {axis}-Runtimepfad")
            if value == "YES" and axis in {"GPU", "DB", "UI"} and not any(
                item.get("observed_surface") == axis for item in runtime
            ):
                errors.append(f"{label}: YES ohne beobachteten {axis}-Runtimebeleg")
        not_checked = set(row.get("not_checked") or [])
        if unknown_axes != not_checked:
            errors.append(
                f"{feature_id}/{path_id}: not_checked {sorted(not_checked)} != UNKNOWN-Achsen {sorted(unknown_axes)}"
            )
    if not seen:
        errors.append("Matrix enthaelt keine Featurepfade")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--workspace-units", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    current_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    inventory = [
        json.loads(line) for line in args.inventory.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    workspace_units = [
        json.loads(line) for line in args.workspace_units.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    errors = verify_snapshot(snapshot, inventory, workspace_units, current_head)
    errors.extend(verify(
        args.matrix, current_head, str(snapshot.get("snapshot_id", "")),
        str(snapshot.get("run_id", "")),
    ))
    print(json.dumps({"ok": not errors, "error_count": len(errors), "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
