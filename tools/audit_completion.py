from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any


REQUIRED_GATES = {
    "feature_inventory",
    "symbol_contracts",
    "runtime_evidence",
    "reviewer_roster",
    "delta_ttl",
    "completion",
}
REQUIRED_CONTRACT_FIELDS = {
    "schema_version",
    "import_id",
    "run_id",
    "audited_commit",
    "snapshot_id",
    "qualification",
    "required_gate_results",
    "shards",
}


class CompletionError(ValueError):
    pass


def _canonical_key(values: list[Any]) -> str:
    return json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CompletionError(f"JSON unlesbar: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CompletionError(f"JSON-Wurzel muss Objekt sein: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise CompletionError(f"Shard unlesbar: {path}: {exc}") from exc
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


def _safe_source(bundle: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise CompletionError(f"Shardpfad ungueltig: {relative!r}")
    candidate = (bundle / relative).resolve()
    try:
        candidate.relative_to(bundle.resolve())
    except ValueError as exc:
        raise CompletionError(f"Shardpfad verlaesst Bundle: {relative}") from exc
    if not candidate.is_file():
        raise CompletionError(f"Shard fehlt: {relative}")
    return candidate


def _validate_bundle(bundle: Path, contract: dict[str, Any]) -> list[tuple[dict[str, Any], Path, bytes]]:
    missing = sorted(REQUIRED_CONTRACT_FIELDS - contract.keys())
    if missing:
        raise CompletionError(f"Pflichtfelder fehlen: {', '.join(missing)}")
    if contract["schema_version"] != 1:
        raise CompletionError("schema_version muss 1 sein")
    for field in ("import_id", "run_id", "snapshot_id"):
        if not isinstance(contract[field], str) or not contract[field].strip():
            raise CompletionError(f"{field} muss nichtleerer String sein")
    commit = contract["audited_commit"]
    if not isinstance(commit, str) or len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise CompletionError("audited_commit muss kanonischer 40-stelliger SHA sein")
    qualification = contract["qualification"]
    if qualification not in {"unqualified", "qualified-partial"}:
        raise CompletionError("qualification ungueltig")
    gates = contract["required_gate_results"]
    if not isinstance(gates, dict) or set(gates) != REQUIRED_GATES or any(gates[name] is not True for name in REQUIRED_GATES):
        raise CompletionError("required_gate_results muss exakte Sechsermenge mit True sein")
    specs = contract["shards"]
    if not isinstance(specs, list) or not specs:
        raise CompletionError("shards muss nichtleere Liste sein")

    validated: list[tuple[dict[str, Any], Path, bytes]] = []
    rows_by_name: dict[str, list[dict[str, Any]]] = {}
    keys_by_name: dict[str, set[str]] = {}
    names: set[str] = set()
    for index, spec in enumerate(specs, 1):
        if not isinstance(spec, dict):
            raise CompletionError(f"Shard-Spezifikation {index} ist kein Objekt")
        required = {"name", "path", "sha256", "record_count", "primary_key", "foreign_keys"}
        absent = sorted(required - spec.keys())
        if absent:
            raise CompletionError(f"Shard {index}: Pflichtfelder fehlen: {', '.join(absent)}")
        name = spec["name"]
        if not isinstance(name, str) or not name or name in names:
            raise CompletionError(f"Doppelte oder ungueltige Shard-ID: {name!r}")
        names.add(name)
        source = _safe_source(bundle, spec["path"])
        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != spec["sha256"]:
            raise CompletionError(f"SHA256 stimmt nicht: {name}")
        rows = _read_jsonl(source)
        if spec["record_count"] != len(rows):
            raise CompletionError(f"record_count stimmt nicht: {name}")
        primary_key = spec["primary_key"]
        if not isinstance(primary_key, list) or not primary_key or not all(isinstance(field, str) and field for field in primary_key):
            raise CompletionError(f"primary_key ungueltig: {name}")
        shard_keys: set[str] = set()
        for row_number, row in enumerate(rows, 1):
            for binding in ("run_id", "audited_commit", "snapshot_id"):
                if row.get(binding) != contract[binding]:
                    raise CompletionError(f"Bindung {binding} falsch: {name}:{row_number}")
            if any(field not in row for field in primary_key):
                raise CompletionError(f"Primaerschluessel unvollstaendig: {name}:{row_number}")
            key = _canonical_key([row[field] for field in primary_key])
            if key in shard_keys:
                raise CompletionError(f"Doppelte ID: {name}:{row_number}")
            shard_keys.add(key)
            if qualification == "unqualified" and _contains_unknown(row):
                raise CompletionError(f"UNKNOWN blockiert unqualifizierte Completion: {name}:{row_number}")
        rows_by_name[name] = rows
        keys_by_name[name] = shard_keys
        validated.append((spec, source, payload))

    for spec, _source, _payload in validated:
        foreign_keys = spec["foreign_keys"]
        if not isinstance(foreign_keys, list):
            raise CompletionError(f"foreign_keys muss Liste sein: {spec['name']}")
        for relation in foreign_keys:
            if not isinstance(relation, dict) or set(relation) != {"field", "target_shard", "target_fields"}:
                raise CompletionError(f"Fremdschluesselvertrag ungueltig: {spec['name']}")
            field = relation["field"]
            target = relation["target_shard"]
            target_fields = relation["target_fields"]
            if target not in rows_by_name or not isinstance(field, str) or not isinstance(target_fields, list) or not target_fields:
                raise CompletionError(f"Fremdschluesselziel ungueltig: {spec['name']}")
            target_spec = next(item for item, _p, _b in validated if item["name"] == target)
            if target_fields != target_spec["primary_key"]:
                raise CompletionError(f"Fremdschluesselfelder entsprechen nicht Zielschluessel: {spec['name']}")
            for row_number, row in enumerate(rows_by_name[spec["name"]], 1):
                value = row.get(field)
                parts = value if isinstance(value, list) else [value]
                if len(parts) != len(target_fields) or _canonical_key(parts) not in keys_by_name[target]:
                    raise CompletionError(f"Fremdschluessel nicht aufloesbar: {spec['name']}:{row_number}")
    return validated


def import_bundle(bundle_dir: Path | str, contract_path: Path | str, master_root: Path | str) -> dict[str, Any]:
    bundle = Path(bundle_dir).resolve()
    contract_file = Path(contract_path).resolve()
    master = Path(master_root).resolve()
    if not bundle.is_dir():
        raise CompletionError(f"Bundle fehlt: {bundle}")
    contract = _read_json(contract_file)
    validated = _validate_bundle(bundle, contract)

    versions = master / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    import_id = contract["import_id"]
    version = versions / import_id
    if version.exists():
        raise CompletionError(f"Import-ID existiert bereits: {import_id}")
    staging = master / f".staging-{uuid.uuid4().hex}"
    pointer_tmp = master / f".CURRENT-{uuid.uuid4().hex}.tmp"
    try:
        staging.mkdir()
        for spec, _source, payload in validated:
            (staging / Path(spec["path"]).name).write_bytes(payload)
        (staging / "atomic_import.json").write_bytes(contract_file.read_bytes())
        staging.rename(version)
        pointer_tmp.write_text(f"{import_id}\n", encoding="utf-8", newline="\n")
        try:
            os.replace(pointer_tmp, master / "CURRENT")
        except OSError as exc:
            raise CompletionError(f"Atomarer Pointerwechsel fehlgeschlagen: {exc}") from exc
    except Exception:
        if pointer_tmp.exists():
            pointer_tmp.unlink()
        if staging.exists():
            shutil.rmtree(staging)
        if version.exists() and not (master / "CURRENT").exists():
            shutil.rmtree(version)
        elif version.exists() and (master / "CURRENT").read_text(encoding="utf-8") != f"{import_id}\n":
            shutil.rmtree(version)
        raise
    return {
        "status": "imported",
        "import_id": import_id,
        "run_id": contract["run_id"],
        "audited_commit": contract["audited_commit"],
        "snapshot_id": contract["snapshot_id"],
        "shard_count": len(validated),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validiert Shardbundle und schaltet Masterledger atomar um.")
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--master", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = import_bundle(args.bundle, args.contract, args.master)
    except CompletionError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
