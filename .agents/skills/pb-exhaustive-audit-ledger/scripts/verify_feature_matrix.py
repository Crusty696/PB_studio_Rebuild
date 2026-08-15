from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

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


def _canonical_bytes(value: dict[str, Any], *, omit: str | None = None) -> bytes:
    payload = {key: item for key, item in value.items() if key != omit}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_id(value: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value, omit="evidence_id")).hexdigest()


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _verify_ref_hash(root: Path, item: object, label: str) -> list[str]:
    if not isinstance(item, dict):
        return [f"{label}: Objekt fehlt"]
    ref = item.get("ref")
    expected = item.get("sha256")
    if not isinstance(ref, str) or not ref.strip():
        return [f"{label}: ref fehlt"]
    if not isinstance(expected, str) or len(expected) != 64:
        return [f"{label}: SHA256 fehlt/ungueltig"]
    candidate = (root / ref).resolve() if not Path(ref).is_absolute() else Path(ref).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return [f"{label}: ref liegt ausserhalb evidence_root: {ref}"]
    if not candidate.is_file():
        return [f"{label}: Artefakt fehlt: {ref}"]
    actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
    return [] if actual == expected else [f"{label}: SHA256 stimmt nicht fuer {ref}"]


def verify_runtime_runs(
    rows: list[dict[str, Any]], *, evidence_root: Path, audited_commit: str, snapshot_id: str,
    run_id: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    indexed: dict[str, dict[str, Any]] = {}
    seen_runtime_run_ids: set[str] = set()
    for number, row in enumerate(rows, 1):
        label = f"Runtime-Run Zeile {number}"
        evidence_id = row.get("evidence_id")
        if evidence_id != canonical_id(row):
            errors.append(f"{label}: evidence_id ist nicht content-addressed")
        if not isinstance(evidence_id, str) or evidence_id in indexed:
            errors.append(f"{label}: evidence_id fehlt/doppelt")
        else:
            indexed[evidence_id] = row
        if row.get("run_id") != run_id:
            errors.append(f"{label}: run_id weicht vom Auditlauf ab")
        if row.get("audited_commit") != audited_commit:
            errors.append(f"{label}: audited_commit weicht vom Zielcommit ab")
        if row.get("snapshot_id") != snapshot_id:
            errors.append(f"{label}: snapshot_id weicht vom Audit-Snapshot ab")
        runtime_run_id = str(row.get("runtime_run_id", "")).strip()
        if not runtime_run_id:
            errors.append(f"{label}: runtime_run_id fehlt")
        elif runtime_run_id in seen_runtime_run_ids:
            errors.append(f"{label}: runtime_run_id doppelt")
        else:
            seen_runtime_run_ids.add(runtime_run_id)
        if not _valid_timestamp(row.get("timestamp")):
            errors.append(f"{label}: timestamp fehlt/ist nicht timezone-aware ISO-8601")
        errors.extend(_verify_ref_hash(evidence_root, row.get("input"), f"{label}/input"))
        command = row.get("command")
        if not isinstance(command, dict) or not isinstance(command.get("argv"), list) or not command.get("argv"):
            errors.append(f"{label}: command.argv fehlt/leer")
        elif not all(isinstance(arg, str) and arg for arg in command["argv"]):
            errors.append(f"{label}: command.argv enthaelt ungueltigen Wert")
        if not isinstance(command, dict) or not isinstance(command.get("cwd"), str) or not command.get("cwd"):
            errors.append(f"{label}: command.cwd fehlt")
        exit_record = row.get("exit")
        if not isinstance(exit_record, dict) or type(exit_record.get("code")) is not int:
            errors.append(f"{label}: exit.code fehlt/ist nicht Integer")
        errors.extend(_verify_ref_hash(evidence_root, exit_record, f"{label}/exit"))
        postcondition = row.get("postcondition")
        errors.extend(_verify_ref_hash(evidence_root, postcondition, f"{label}/postcondition"))
        if not isinstance(postcondition, dict) or postcondition.get("result") not in {"pass", "fail"}:
            errors.append(f"{label}: postcondition.result muss pass/fail sein")
        artifacts = row.get("artifacts")
        if not isinstance(artifacts, list):
            errors.append(f"{label}: artifacts muss Liste sein")
        else:
            for index, artifact in enumerate(artifacts):
                errors.extend(_verify_ref_hash(evidence_root, artifact, f"{label}/artifacts[{index}]"))
        for field in ("covered_feature_paths", "covered_symbol_ids", "covered_axes"):
            values = row.get(field)
            if not isinstance(values, list) or not values or len(values) != len(set(values)):
                errors.append(f"{label}: {field} fehlt/leer/enthaelt Duplikate")
            elif not all(isinstance(item, str) and item for item in values):
                errors.append(f"{label}: {field} enthaelt ungueltigen Wert")
        if isinstance(row.get("covered_feature_paths"), list) and len(row["covered_feature_paths"]) != 1:
            errors.append(f"{label}: covered_feature_paths muss exakt einen Featurepfad enthalten")
        covered_axes = row.get("covered_axes")
        if isinstance(covered_axes, list) and any(axis not in AXES for axis in covered_axes):
            errors.append(f"{label}: covered_axes enthaelt unbekannte Achse")
    if not rows:
        errors.append("Runtime-Runs-Manifest ist leer")
    else:
        errors.append("Runtime-Runner-Harness fehlt; Dateimanifest allein ist keine Ausfuehrungsattestierung")
    return indexed, errors


def _runtime_evidence(
    cell: dict[str, Any], commit_sha: str, run_id: str,
    runtime_runs: dict[str, dict[str, Any]], label: str, feature_path: str,
    axis: str, errors: list[str],
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for item in cell.get("evidence", []):
        if not isinstance(item, dict) or item.get("kind") != "runtime":
            continue
        evidence_id = item.get("evidence_id")
        runtime = runtime_runs.get(evidence_id)
        if runtime is None:
            errors.append(f"{label}: unbekannte Runtime-evidence_id {evidence_id!r}")
            continue
        if item.get("commit_sha") != commit_sha or runtime.get("audited_commit") != commit_sha:
            errors.append(f"{label}: Runtimebeleg weicht vom Featurecommit ab")
            continue
        if item.get("run_id") != run_id or runtime.get("run_id") != run_id:
            errors.append(f"{label}: Runtimebeleg weicht vom Auditlauf ab")
            continue
        if item.get("timestamp") != runtime.get("timestamp"):
            errors.append(f"{label}: Runtime-Timestamp stimmt nicht mit Manifest")
            continue
        if feature_path not in (runtime.get("covered_feature_paths") or []):
            errors.append(f"{label}: Runtimebeleg deckt Featurepfad nicht")
            continue
        if axis not in (runtime.get("covered_axes") or []):
            errors.append(f"{label}: Runtimebeleg deckt Achse nicht")
            continue
        resolved.append(runtime)
    return resolved


def _derived_overall(values: list[object]) -> str:
    if any(value == "UNKNOWN" for value in values):
        return "not-checked"
    if any(value == "NO" for value in values):
        return "failed"
    if any(value == "PARTIAL" for value in values):
        return "partial"
    return "verified"


def verify_feature_contract(
    matrix: list[dict[str, Any]], requirements: list[dict[str, Any]],
    runtime_rows: list[dict[str, Any]], *, evidence_root: Path,
    audited_commit: str, snapshot_id: str, run_id: str,
) -> list[str]:
    errors: list[str] = []
    runtime_runs, runtime_errors = verify_runtime_runs(
        runtime_rows, evidence_root=evidence_root, audited_commit=audited_commit,
        snapshot_id=snapshot_id, run_id=run_id,
    )
    errors.extend(runtime_errors)

    required: dict[tuple[str, str], dict[str, Any]] = {}
    for number, row in enumerate(requirements, 1):
        key = (str(row.get("feature_id", "")).strip(), str(row.get("path_id", "")).strip())
        if not all(key) or key in required:
            errors.append(f"Requirements Zeile {number}: fehlender/doppelter Featurepfad {key!r}")
        else:
            required[key] = row
        if row.get("run_id") != run_id or row.get("snapshot_id") != snapshot_id:
            errors.append(f"Requirements {key!r}: Auditbindung stimmt nicht")
        if row.get("audited_commit") != audited_commit:
            errors.append(f"Requirements {key!r}: audited_commit stimmt nicht")
        for field in ("source_kind", "source_ref"):
            if not str(row.get(field, "")).strip():
                errors.append(f"Requirements {key!r}: {field} fehlt")
        axes = row.get("required_runtime_axes")
        if not isinstance(axes, list) or not axes:
            errors.append(f"Requirements {key!r}: required_runtime_axes fehlt/leer")
        elif len(set(axes)) != len(axes) or any(axis not in AXES for axis in axes):
            errors.append(f"Requirements {key!r}: required_runtime_axes ungueltig/doppelt")

    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for number, row in enumerate(matrix, 1):
        missing = [key for key in REQUIRED_FIELDS if key not in row]
        if missing:
            errors.append(f"Feature Zeile {number}: Pflichtfelder fehlen: {', '.join(missing)}")
        feature_id = str(row.get("feature_id", "")).strip()
        path_id = str(row.get("path_id", "")).strip()
        key = (feature_id, path_id)
        if not feature_id or not path_id or key in seen:
            errors.append(f"Feature Zeile {number}: fehlender/doppelter Featurepfad {key!r}")
        else:
            seen[key] = row
        commit_sha = str(row.get("commit_sha", ""))
        if commit_sha != audited_commit:
            errors.append(f"{feature_id}/{path_id}: Commit ist nicht audited_commit")
        if row.get("snapshot_id") != snapshot_id or row.get("run_id") != run_id:
            errors.append(f"{feature_id}/{path_id}: Snapshot-/Run-Bindung stimmt nicht")
        for field in ("name", "expected_result", "evidence_age", "verdict", "reviewer_id", "signed_at"):
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
        unknown_axes: set[str] = set()
        values: list[object] = []
        required_runtime_axes = set(required.get(key, {}).get("required_runtime_axes") or [])
        for axis in AXES:
            cell = states.get(axis)
            label = f"{feature_id}/{path_id}:{axis}"
            if not isinstance(cell, dict):
                errors.append(f"{label}: Zelle fehlt")
                values.append(None)
                continue
            value = cell.get("value")
            values.append(value)
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
                if not all(item.get(field) for field in ("kind", "ref", "commit_sha", "timestamp", "run_id")):
                    errors.append(f"{label}: Evidenzobjekt unvollstaendig")
                if item.get("commit_sha") != commit_sha or item.get("run_id") != run_id:
                    errors.append(f"{label}: Evidenzbindung weicht von Feature ab")
                if not _valid_timestamp(item.get("timestamp")):
                    errors.append(f"{label}: Evidenztimestamp ungueltig")
            if value == "N-A" and not any(
                isinstance(item, dict) and item.get("kind") == "n-a" and str(item.get("reason", "")).strip()
                for item in evidence
            ):
                errors.append(f"{label}: N-A ohne explizite Begruendung")
            if value == "UNKNOWN":
                unknown_axes.add(axis)
                if not any(
                    isinstance(item, dict) and item.get("kind") == "not-checked" and str(item.get("reason", "")).strip()
                    for item in evidence
                ):
                    errors.append(f"{label}: UNKNOWN ohne not-checked-Grund")
                if axis in required_runtime_axes:
                    errors.append(f"{feature_id}/{path_id}: Pflicht-Runtimeachse {axis} ist UNKNOWN")
            if value == "N-A" and axis in required_runtime_axes:
                errors.append(f"{feature_id}/{path_id}: Pflicht-Runtimeachse {axis} darf nicht N-A sein")
            runtime = _runtime_evidence(
                cell, commit_sha, run_id, runtime_runs, label, f"{feature_id}/{path_id}", axis, errors,
            )
            if value == "YES" and axis in required_runtime_axes and not runtime:
                errors.append(f"{label}: YES-Pflichtachse ohne validierten Runtimebeleg")
            if value == "YES" and axis in required_runtime_axes and runtime and not any(
                item.get("exit", {}).get("code") == 0
                and item.get("postcondition", {}).get("result") == "pass"
                for item in runtime
            ):
                errors.append(f"{label}: kein erfolgreicher Runtimebeleg fuer YES")
            if value == "YES" and axis == "restart_safe" and axis in required_runtime_axes and not any(
                item.get("restart") is True and item.get("reopen") is True for item in runtime
            ):
                errors.append(f"{label}: YES ohne echten Restart/Reopen-Beleg")
            if value == "YES" and axis in {"error", "cancel", "retry"} and axis in required_runtime_axes and not any(
                item.get("forced_state") == axis for item in runtime
            ):
                errors.append(f"{label}: YES ohne erzwungenen {axis}-Runtimepfad")
            if value == "YES" and axis in {"GPU", "DB", "UI"} and axis in required_runtime_axes and not any(
                item.get("observed_surfaces") and axis in item.get("observed_surfaces") for item in runtime
            ):
                errors.append(f"{label}: YES ohne beobachteten {axis}-Runtimebeleg")
        not_checked = set(row.get("not_checked") or [])
        if unknown_axes != not_checked:
            errors.append(f"{feature_id}/{path_id}: not_checked stimmt nicht mit UNKNOWN-Achsen")
        derived = _derived_overall(values)
        if row.get("overall_state") != derived:
            errors.append(f"{feature_id}/{path_id}: overall_state muss abgeleitet {derived!r} sein")

    required_keys = set(required)
    matrix_keys = set(seen)
    if required_keys != matrix_keys:
        errors.append(
            "Feature-Mengengleichheit verletzt: "
            f"fehlend={sorted(required_keys - matrix_keys)!r}, unerwartet={sorted(matrix_keys - required_keys)!r}"
        )
    if not required:
        errors.append("Requirements-/Trigger-Manifest ist leer")
    return errors


def verify(path: Path, current_head: str, snapshot_id: str, run_id: str) -> list[str]:
    """Legacy Python-test adapter; production CLI always uses full manifest contract."""
    rows, errors = _load_jsonl(path, "Featurematrix")
    seen: set[tuple[str, str]] = set()
    for number, row in enumerate(rows, 1):
        missing = [field for field in REQUIRED_FIELDS if field not in row]
        if missing:
            errors.append(f"Zeile {number}: Pflichtfelder fehlen: {', '.join(missing)}")
        feature_id = str(row.get("feature_id", "")).strip()
        path_id = str(row.get("path_id", "")).strip()
        key = (feature_id, path_id)
        if not feature_id or not path_id or key in seen:
            errors.append(f"Zeile {number}: fehlender/doppelter Featurepfad {key!r}")
        seen.add(key)
        if row.get("commit_sha") != current_head:
            errors.append(f"{feature_id}/{path_id}: Commit ist nicht Current HEAD")
        if row.get("snapshot_id") != snapshot_id:
            errors.append(f"{feature_id}/{path_id}: snapshot_id stimmt nicht mit Audit-Snapshot")
        if row.get("run_id") != run_id:
            errors.append(f"{feature_id}/{path_id}: run_id stimmt nicht mit Audit-Snapshot")
        states = row.get("states") or {}
        for axis in AXES:
            cell = states.get(axis)
            label = f"{feature_id}/{path_id}:{axis}"
            if not isinstance(cell, dict):
                errors.append(f"{label}: Zelle fehlt")
                continue
            value, evidence = cell.get("value"), cell.get("evidence")
            if value not in VALUES:
                errors.append(f"{label}: ungueltiger Wert {value!r}")
            if not isinstance(evidence, list) or not evidence:
                errors.append(f"{label}: Evidenz/Begruendung fehlt")
                continue
            runtime = [
                item for item in evidence
                if isinstance(item, dict) and item.get("kind") == "runtime"
                and item.get("commit_sha") == current_head and item.get("run_id") == run_id
                and item.get("timestamp") and item.get("ref")
            ]
            if value == "YES" and axis in {"executed", "result", "live_evidence"} and not runtime:
                errors.append(f"{label}: YES ohne Current-HEAD-Runtimebeleg")
    if not seen:
        errors.append("Matrix enthaelt keine Featurepfade")
    return errors


def verify_snapshot(
    snapshot: dict[str, Any], inventory: list[dict[str, Any]],
    workspace_units: list[dict[str, Any]], audited_commit: str,
) -> list[str]:
    rows_without_snapshot = [{key: value for key, value in row.items() if key != "snapshot_id"} for row in inventory]
    computed_snapshot_id = _snapshot_basis(rows_without_snapshot, workspace_units)
    errors = []
    if not snapshot.get("run_id"):
        errors.append("Snapshot-run_id fehlt")
    if snapshot.get("commit_sha") != audited_commit:
        errors.append("Snapshot-Commit ist nicht audited_commit")
    if snapshot.get("audited_commit") not in (None, audited_commit):
        errors.append("Snapshot-audited_commit widerspricht commit_sha")
    if snapshot.get("snapshot_id") != computed_snapshot_id:
        errors.append("Snapshot stimmt nicht mit Inventory/Workspace-Scope")
    return errors


def _load_jsonl(path: Path, label: str) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{label} Zeile {number}: invalides JSON: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{label} Zeile {number}: Objekt erwartet")
            continue
        rows.append(value)
    return rows, errors


def _verify_bound_file(snapshot: dict[str, Any], path: Path, prefix: str, rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if snapshot.get(f"{prefix}_sha256") != actual:
        errors.append(f"Snapshot-{prefix}_sha256 stimmt nicht")
    if snapshot.get(f"{prefix}_count") != len(rows):
        errors.append(f"Snapshot-{prefix}_count stimmt nicht")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--workspace-units", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--requirements-triggers", type=Path, required=True)
    parser.add_argument("--runtime-runs", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    audited_commit = str(snapshot.get("audited_commit") or snapshot.get("commit_sha") or "")
    inventory, inventory_errors = _load_jsonl(args.inventory, "Inventory")
    workspace_units, workspace_errors = _load_jsonl(args.workspace_units, "Workspace")
    matrix, matrix_errors = _load_jsonl(args.matrix, "Featurematrix")
    requirements, requirement_errors = _load_jsonl(args.requirements_triggers, "Requirements")
    runtime_rows, runtime_errors = _load_jsonl(args.runtime_runs, "Runtime-Runs")
    errors = inventory_errors + workspace_errors + matrix_errors + requirement_errors + runtime_errors
    try:
        resolved = subprocess.check_output(
            ["git", "rev-parse", "--verify", f"{audited_commit}^{{commit}}"], cwd=root,
            stderr=subprocess.STDOUT,
        ).decode().strip()
        if resolved != audited_commit:
            errors.append("audited_commit ist nicht kanonischer Gitcommit")
    except subprocess.CalledProcessError:
        errors.append("audited_commit existiert nicht als Gitcommit")
    errors.extend(verify_snapshot(snapshot, inventory, workspace_units, audited_commit))
    errors.extend(_verify_bound_file(snapshot, args.requirements_triggers, "requirements_triggers", requirements))
    errors.extend(_verify_bound_file(snapshot, args.runtime_runs, "runtime_runs", runtime_rows))
    errors.extend(verify_feature_contract(
        matrix, requirements, runtime_rows, evidence_root=args.evidence_root.resolve(),
        audited_commit=str(snapshot.get("commit_sha", "")),
        snapshot_id=str(snapshot.get("snapshot_id", "")), run_id=str(snapshot.get("run_id", "")),
    ))
    print(json.dumps({"ok": not errors, "error_count": len(errors), "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
