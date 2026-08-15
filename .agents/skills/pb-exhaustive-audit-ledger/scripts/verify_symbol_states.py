from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from verify_feature_matrix import verify_runtime_runs


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}: Zeile {number}: Objekt erwartet")
        rows.append(value)
    return rows


def verify_symbol_contract(
    states: list[dict[str, Any]], manifest: list[dict[str, Any]], *,
    runtime_symbol_coverage: dict[str, set[str]], known_feature_ids: set[str], audited_commit: str,
    snapshot_id: str, run_id: str,
) -> list[str]:
    errors: list[str] = []
    declared: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(manifest, 1):
        symbol_id = str(row.get("symbol_id", "")).strip()
        if not symbol_id or symbol_id in declared:
            errors.append(f"Symbolmanifest Zeile {number}: symbol_id fehlt/doppelt")
        else:
            declared[symbol_id] = row
        if row.get("run_id") != run_id or row.get("snapshot_id") != snapshot_id:
            errors.append(f"Symbolmanifest {symbol_id}: Auditbindung stimmt nicht")
        if row.get("audited_commit") != audited_commit:
            errors.append(f"Symbolmanifest {symbol_id}: audited_commit stimmt nicht")
        for field in ("path", "qualified_name", "kind"):
            if not str(row.get(field, "")).strip():
                errors.append(f"Symbolmanifest {symbol_id}: {field} fehlt")
        start, end = row.get("line_start"), row.get("line_end")
        if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
            errors.append(f"Symbolmanifest {symbol_id}: ungueltiger Zeilenbereich")

    seen: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(states, 1):
        symbol_id = str(row.get("symbol_id", "")).strip()
        if not symbol_id or symbol_id in seen:
            errors.append(f"Symbol-State Zeile {number}: symbol_id fehlt/doppelt")
        else:
            seen[symbol_id] = row
        source = declared.get(symbol_id)
        if source is not None:
            for field in ("run_id", "snapshot_id", "audited_commit", "path", "qualified_name", "kind", "line_start", "line_end"):
                if row.get(field) != source.get(field):
                    errors.append(f"Symbol-State {symbol_id}: {field} weicht vom Manifest ab")
        feature_ids = row.get("feature_ids")
        if (
            not isinstance(feature_ids, list) or not feature_ids
            or len(feature_ids) != len(set(feature_ids))
            or not all(isinstance(item, str) and item for item in feature_ids)
        ):
            errors.append(f"Symbol-State {symbol_id}: feature_ids fehlt/ungueltig")
        elif any(item not in known_feature_ids for item in feature_ids):
            errors.append(f"Symbol-State {symbol_id}: unbekannte feature_id")
        disposition = row.get("disposition")
        evidence_ids = row.get("runtime_evidence_ids")
        contract = row.get("non_runtime_contract")
        if disposition == "runtime":
            if not isinstance(evidence_ids, list) or not evidence_ids or len(evidence_ids) != len(set(evidence_ids)):
                errors.append(f"Symbol-State {symbol_id}: Runtime-Disposition ohne Runtimebeleg")
            elif any(item not in runtime_symbol_coverage for item in evidence_ids):
                errors.append(f"Symbol-State {symbol_id}: unbekannte Runtime-evidence_id")
            elif any(symbol_id not in runtime_symbol_coverage[item] for item in evidence_ids):
                errors.append(f"Symbol-State {symbol_id}: Runtimebeleg deckt Symbol nicht")
            if contract not in (None, {}):
                errors.append(f"Symbol-State {symbol_id}: Runtime-Disposition mit widerspruechlichem Non-Runtime-Vertrag")
        elif disposition == "non-runtime":
            if evidence_ids not in ([], None):
                errors.append(f"Symbol-State {symbol_id}: Non-Runtime-Disposition mit Runtimebeleg")
            if not isinstance(contract, dict) or not all(str(contract.get(field, "")).strip() for field in ("kind", "ref", "reason")):
                errors.append(f"Symbol-State {symbol_id}: begruendeter Non-Runtime-Vertrag fehlt")
        else:
            errors.append(f"Symbol-State {symbol_id}: disposition muss runtime/non-runtime sein")

    declared_ids, state_ids = set(declared), set(seen)
    if declared_ids != state_ids:
        errors.append(
            "Symbol-Mengengleichheit verletzt: "
            f"fehlend={sorted(declared_ids - state_ids)!r}, unerwartet={sorted(state_ids - declared_ids)!r}"
        )
    if not declared:
        errors.append("Symbolmanifest ist leer")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--symbols-manifest", type=Path, required=True)
    parser.add_argument("--symbol-states", type=Path, required=True)
    parser.add_argument("--runtime-runs", type=Path, required=True)
    parser.add_argument("--requirements-triggers", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    manifest = _load_jsonl(args.symbols_manifest)
    states = _load_jsonl(args.symbol_states)
    runtime = _load_jsonl(args.runtime_runs)
    requirements = _load_jsonl(args.requirements_triggers)
    errors: list[str] = []
    manifest_hash = hashlib.sha256(args.symbols_manifest.read_bytes()).hexdigest()
    if snapshot.get("symbols_manifest_sha256") != manifest_hash:
        errors.append("Snapshot-symbols_manifest_sha256 stimmt nicht")
    if snapshot.get("symbols_manifest_count") != len(manifest):
        errors.append("Snapshot-symbols_manifest_count stimmt nicht")
    for prefix, path, rows in (
        ("runtime_runs", args.runtime_runs, runtime),
        ("requirements_triggers", args.requirements_triggers, requirements),
    ):
        if snapshot.get(f"{prefix}_sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
            errors.append(f"Snapshot-{prefix}_sha256 stimmt nicht")
        if snapshot.get(f"{prefix}_count") != len(rows):
            errors.append(f"Snapshot-{prefix}_count stimmt nicht")
    runtime_index, runtime_errors = verify_runtime_runs(
        runtime, evidence_root=args.evidence_root.resolve(),
        audited_commit=str(snapshot.get("commit_sha", "")), snapshot_id=str(snapshot.get("snapshot_id", "")),
        run_id=str(snapshot.get("run_id", "")), trusted_execution_ids=None,
    )
    errors.extend(runtime_errors)
    errors.extend(verify_symbol_contract(
        states, manifest, runtime_symbol_coverage={
            evidence_id: set(row.get("covered_symbol_ids") or [])
            for evidence_id, row in runtime_index.items()
        },
        known_feature_ids={str(row.get("feature_id", "")) for row in requirements},
        audited_commit=str(snapshot.get("commit_sha", "")),
        snapshot_id=str(snapshot.get("snapshot_id", "")), run_id=str(snapshot.get("run_id", "")),
    ))
    print(json.dumps({"ok": not errors, "error_count": len(errors), "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
