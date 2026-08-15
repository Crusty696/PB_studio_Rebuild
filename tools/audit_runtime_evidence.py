#!/usr/bin/env python3
"""Execute externally pinned audit scenarios and emit content-addressed evidence."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.metadata
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
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
    "snapshot_id", "scenario_sha256", "feature_target", "command",
    "timeout_seconds", "inputs", "allowed_symbol_ids", "allowed_axes",
    "symbol_probes", "required_modules", "postcondition", "artifacts",
}
CONTRACT_REFS = (
    "scenario_catalog", "feature_universe", "symbol_universe",
    "executor_manifest", "dependency_manifest",
)
ALLOWED_EXECUTORS = {"python"}


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
    return subprocess.run(
        ["git", *args], cwd=repo, input=input_data, check=check,
        capture_output=True, shell=False,
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


def _parse_jsonl(data: bytes, label: str) -> list[dict[str, Any]]:
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
    if not rows:
        raise ContractError(f"{label} ist leer")
    return rows


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
    return path, data


def _load_contract(evidence: Path, contract_path: Path) -> tuple[dict[str, Any], bytes, dict[str, tuple[Path, bytes]]]:
    contract_path = _contained(evidence, contract_path, "audit_contract")
    if not contract_path.is_file():
        raise ContractError("audit_contract fehlt")
    data = contract_path.read_bytes()
    contract = _parse_json(data, "audit_contract")
    if contract.get("schema_version") != 1:
        raise ContractError("audit_contract.schema_version muss 1 sein")
    for field in ("run_id", "snapshot_id"):
        if not isinstance(contract.get(field), str) or not contract[field]:
            raise ContractError(f"audit_contract.{field} fehlt")
    for field in ("audited_commit", "tooling_commit"):
        if not isinstance(contract.get(field), str) or not SHA_RE.fullmatch(contract[field]):
            raise ContractError(f"audit_contract.{field} muss voller SHA sein")
    refs = {name: _read_bound_ref(evidence, contract.get(name), name) for name in CONTRACT_REFS}
    return contract, data, refs


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
        if row.get("scenario_sha256") != canonical_sha256(row, omit={"scenario_sha256"}):
            raise ContractError(f"Scenario {scenario_id}: scenario_sha256 stimmt nicht")
        axes = row.get("allowed_axes")
        if not isinstance(axes, list) or not all(isinstance(axis, str) for axis in axes):
            raise ContractError(f"Scenario {scenario_id}: allowed_axes ungueltig")
        feature_target = row.get("feature_target")
        symbols = row.get("allowed_symbol_ids")
        if not isinstance(feature_target, str) or not feature_target:
            raise ContractError(f"Scenario {scenario_id}: feature_target fehlt")
        if (
            not isinstance(symbols, list) or not symbols
            or not all(isinstance(symbol, str) and symbol for symbol in symbols)
            or len(symbols) != len(set(symbols))
        ):
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
    for number, row in enumerate(_parse_jsonl(symbol_data, "Symbol-Universum"), 1):
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
    if not isinstance(values, list) or not values or not all(isinstance(item, str) and item for item in values):
        raise ContractError(f"Scenario {row.get('scenario_id')}: allowed_symbol_ids fehlt/ungueltig")
    if len(values) != len(set(values)):
        raise ContractError(f"Scenario {row.get('scenario_id')}: allowed_symbol_ids doppelt")
    for symbol in values:
        if symbol not in symbols:
            raise ContractError(f"Scenario {row.get('scenario_id')}: fremdes Symbol {symbol}")
        if target not in symbols[symbol]:
            raise ContractError(f"Symbol {symbol} ist nicht an Featuretarget {target} gebunden")
    probes = row.get("symbol_probes")
    if not isinstance(probes, list) or not probes:
        raise ContractError("Scenario.symbol_probes fehlt")
    probe_ids: list[str] = []
    for index, probe in enumerate(probes):
        if not isinstance(probe, dict):
            raise ContractError(f"Scenario.symbol_probes[{index}] ungueltig")
        symbol_id, path, function = probe.get("symbol_id"), probe.get("path"), probe.get("function")
        if not all(isinstance(item, str) and item for item in (symbol_id, path, function)):
            raise ContractError(f"Scenario.symbol_probes[{index}] unvollstaendig")
        if Path(path).is_absolute() or ".." in Path(path).parts:
            raise ContractError(f"Scenario.symbol_probes[{index}].path entkommt Auditbaum")
        probe_ids.append(symbol_id)
    if len(probe_ids) != len(set(probe_ids)) or set(probe_ids) != set(values):
        raise ContractError("Scenario.symbol_probes muss allowed_symbol_ids exakt abbilden")


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
) -> str:
    expanded = arg.replace("{run_dir}", str(run_dir))
    for name, path in inputs.items():
        expanded = expanded.replace(f"{{input:{name}}}", str(path))
    if "{" in expanded or "}" in expanded:
        raise ContractError(f"{label}: unbekannter Placeholder")
    pathish = Path(expanded)
    if ".." in pathish.parts:
        raise ContractError(f"{label}: Pfad-Escape verboten")
    if pathish.is_absolute():
        resolved = pathish.resolve()
        allowed = [root.resolve(), run_dir.resolve(), *[path.resolve() for path in inputs.values()]]
        if not any(resolved == base or (base.is_dir() and _is_relative_to(resolved, base)) for base in allowed):
            raise ContractError(f"{label}: absoluter Pfad ausserhalb erlaubter Wurzeln")
    return expanded


def _resolve_command(
    command: dict[str, Any], *, root: Path, run_dir: Path, inputs: dict[str, Path],
    executors: dict[str, dict[str, str]], label: str, commit: str,
) -> tuple[list[str], Path, dict[str, Any]]:
    cwd = _contained(root, root / command["cwd"], f"{label}.cwd")
    if not cwd.is_dir():
        raise ContractError(f"{label}.cwd fehlt")
    executable_key = command["argv"][0].lower().removesuffix(".exe")
    if executable_key not in executors:
        raise ContractError(f"{label}: Executable {command['argv'][0]!r} ist nicht erlaubt")
    resolved = [executors[executable_key]["path"]]
    for index, arg in enumerate(command["argv"][1:], 1):
        resolved.append(_expand_arg(arg, root=root, run_dir=run_dir, inputs=inputs, label=f"{label}.argv[{index}]"))
    if executable_key == "python":
        if len(resolved) < 2 or resolved[1].startswith("-") or Path(resolved[1]).suffix.lower() != ".py":
            raise ContractError(f"{label}: Python braucht gebundenes .py-Script")
        source = Path(resolved[1])
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


def _sanitized_environment(root: Path, run_dir: Path, observer_dir: Path | None) -> dict[str, str]:
    keep = ("SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP")
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env.update({
        "PB_AUDIT_ROOT": str(root), "PB_AUDIT_RUN_DIR": str(run_dir),
        "PYTHONPATH": os.pathsep.join([str(observer_dir), str(root)]) if observer_dir else str(root),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1", "PYTHONSAFEPATH": "1",
    })
    return env


class ObservationSink:
    def __init__(self) -> None:
        self.nonce = uuid.uuid4().hex
        self.secret = os.urandom(32)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.bind(("127.0.0.1", 0))
        self.socket.listen(4)
        self.socket.settimeout(0.1)
        self.host, self.port = self.socket.getsockname()
        self.events: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def write_bootstrap(self, destination: Path, probes: list[dict[str, str]], audited_root: Path) -> Path:
        destination.mkdir(parents=True)
        bound: dict[str, dict[str, str]] = {}
        for probe in probes:
            source = _contained(audited_root, audited_root / probe["path"], "symbol_probe.path")
            if not source.is_file():
                raise ContractError(f"symbol_probe.path fehlt im Auditcommit: {probe['path']}")
            key = f"{os.path.normcase(str(source.resolve()))}|{probe['function']}"
            if key in bound:
                raise ContractError("symbol_probe-Ziel doppelt")
            bound[key] = {"symbol_id": probe["symbol_id"], "path": probe["path"], "function": probe["function"]}
        bootstrap = destination / "sitecustomize.py"
        source = (
            "import hashlib,hmac,json,os,socket,sys,time\n"
            f"_HOST={self.host!r};_PORT={self.port!r};_NONCE={self.nonce!r};_SECRET={self.secret.hex()!r}\n"
            f"_PROBES={bound!r}\n"
            "_SENT=set()\n"
            "def _trace(frame,event,arg):\n"
            " if event!='call': return _trace\n"
            " key=os.path.normcase(os.path.abspath(frame.f_code.co_filename))+'|'+frame.f_code.co_name\n"
            " probe=_PROBES.get(key)\n"
            " if probe is None or key in _SENT: return _trace\n"
            " _SENT.add(key)\n"
            " row={'nonce':_NONCE,'pid':os.getpid(),'time_ns':time.time_ns(),'observer':'runner-python-trace','event':'call','source_path':probe['path'],'function':probe['function'],'symbol_id':probe['symbol_id']}\n"
            " payload=json.dumps(row,sort_keys=True,separators=(',',':')).encode()\n"
            " row['signature']=hmac.new(bytes.fromhex(_SECRET),payload,hashlib.sha256).hexdigest()\n"
            " try:\n"
            "  with socket.create_connection((_HOST,_PORT),timeout=2) as sock: sock.sendall(json.dumps(row,separators=(',',':')).encode()+b'\\n')\n"
            " except OSError: pass\n"
            " return _trace\n"
            "sys.settrace(_trace)\n"
        )
        bootstrap.write_text(source, encoding="utf-8")
        return bootstrap

    def start(self) -> None:
        self.thread.start()

    def _serve(self) -> None:
        while not self.stop_event.is_set():
            try:
                connection, _ = self.socket.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with connection:
                connection.settimeout(1)
                payload = b""
                try:
                    while True:
                        block = connection.recv(65536)
                        if not block:
                            break
                        payload += block
                        if len(payload) > 1024 * 1024:
                            raise ValueError("Observer-Payload zu gross")
                except (OSError, ValueError) as exc:
                    self.errors.append(str(exc))
                for line in payload.splitlines():
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        self.errors.append("Observer-Payload ist kein JSON")
                        continue
                    if not isinstance(row, dict):
                        self.errors.append("Observer-Payload ist kein Objekt")
                        continue
                    row["runner_received_time_ns"] = time.time_ns()
                    self.events.append(row)

    def stop(self) -> None:
        time.sleep(0.05)
        self.stop_event.set()
        self.socket.close()
        self.thread.join(timeout=2)


def _kill_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    tree_kill_error: str | None = None
    if os.name == "nt":
        result = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, check=False, shell=False,
        )
        if result.returncode != 0:
            tree_kill_error = result.stderr.decode(errors="replace").strip() or result.stdout.decode(errors="replace").strip()
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
    if tree_kill_error is not None:
        raise ContractError(f"Timeout: Prozessbaum-Kill nicht attestierbar: {tree_kill_error}")


def _execute(
    argv: list[str], *, cwd: Path, timeout: float, environment: dict[str, str],
    label: str, observer: ObservationSink | None = None,
) -> tuple[int, bytes, bytes, int, int, int]:
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    start_ns = time.time_ns()
    if observer is not None:
        observer.start()
    process = subprocess.Popen(
        argv, cwd=cwd, env=environment, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
        creationflags=flags, start_new_session=(os.name != "nt"),
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _kill_process_tree(process)
        raise ContractError(f"{label}: Timeout nach {timeout:g}s") from exc
    finally:
        if observer is not None:
            observer.stop()
    end_ns = time.time_ns()
    return process.returncode, stdout, stderr, process.pid, start_ns, end_ns


def _validate_observations(
    sink: ObservationSink, *, process_pid: int, start_ns: int, end_ns: int,
    feature: str, allowed_symbols: list[str], allowed_axes: list[str],
    probes: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    if sink.errors:
        raise ContractError(f"Observer-Sink-Fehler: {sink.errors}")
    if not sink.events:
        raise ContractError("Runner-Observer erhielt keine Events")
    symbols: set[str] = set()
    axes: set[str] = set()
    probe_map = {probe["symbol_id"]: probe for probe in probes}
    cleaned: list[dict[str, Any]] = []
    for number, row in enumerate(sink.events, 1):
        signature = row.pop("signature", None)
        signed_payload = _canonical_bytes({key: value for key, value in row.items() if key != "runner_received_time_ns"})
        if not isinstance(signature, str) or not hmac.compare_digest(signature, hmac.new(sink.secret, signed_payload, hashlib.sha256).hexdigest()):
            raise ContractError(f"Observer-Event {number}: Instrumentationssignatur falsch")
        if row.get("nonce") != sink.nonce:
            raise ContractError(f"Observer-Event {number}: Nonce falsch")
        if row.get("pid") != process_pid:
            raise ContractError(f"Observer-Event {number}: PID nicht Hauptprozess")
        sent = row.get("time_ns")
        received = row.get("runner_received_time_ns")
        if type(sent) is not int or type(received) is not int or not (start_ns <= sent <= received <= end_ns + 2_000_000_000):
            raise ContractError(f"Observer-Event {number}: Zeitbindung ungueltig")
        symbol = row.get("symbol_id")
        event, observer_type = row.get("event"), row.get("observer")
        if symbol not in allowed_symbols:
            raise ContractError(f"Observer-Event {number}: fremdes Symbol")
        probe = probe_map[symbol]
        if row.get("source_path") != probe["path"] or row.get("function") != probe["function"]:
            raise ContractError(f"Observer-Event {number}: Probe-Bindung falsch")
        if event != "call" or observer_type != "runner-python-trace":
            raise ContractError(f"Observer-Event {number}: event/observer fehlt")
        symbols.add(symbol)
        cleaned.append({
            **{key: value for key, value in row.items() if key != "nonce"},
            "feature_path": feature,
            "axis": "executed",
        })
    if symbols != set(allowed_symbols):
        raise ContractError("Observer deckt nicht exakt alle gebundenen Symbole")
    if "executed" in allowed_axes:
        axes.add("executed")
    unsupported = set(allowed_axes) - {"executed", "result", "live_evidence"}
    if unsupported:
        named = sorted(unsupported)
        surface = next((axis for axis in named if axis in SURFACE_OBSERVERS), None)
        if surface:
            raise ContractError(f"Achse {surface} braucht spezifischen Observer; generischer Trace reicht nicht")
        raise ContractError(f"Achsen brauchen noch runner-eigenen Spezialobserver: {named}")
    return cleaned, sorted(symbols), sorted(axes)


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


def _write(path: Path, data: bytes) -> dict[str, Any]:
    path.write_bytes(data)
    return {"bytes": len(data), "sha256": _sha_bytes(data)}


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


def _create_lock(path: Path, label: str) -> None:
    payload = _canonical_bytes({"pid": os.getpid(), "created_ns": time.time_ns(), "nonce": uuid.uuid4().hex}) + b"\n"
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ContractError(f"{label}-Lock existiert; auch stale Lock muss manuell untersucht werden") from exc
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)


def _append_ledger_atomic(ledger: Path, receipt: dict[str, Any]) -> None:
    lock = ledger.parent / ".runtime_runs.lock"
    _create_lock(lock, "Ledger")
    temp_path: Path | None = None
    try:
        runtime_ids, evidence_ids = _existing_runtime_ids(ledger)
        if receipt["runtime_run_id"] in runtime_ids or receipt["evidence_id"] in evidence_ids:
            raise ContractError("Runtime-Receipt bereits im Ledger vorhanden")
        if _scenario_already_recorded(ledger, receipt["scenario_id"]):
            raise ContractError("Scenario wurde bereits ausgefuehrt; Evidence-Reuse verboten")
        existing = ledger.read_bytes() if ledger.exists() else b""
        if existing and not existing.endswith(b"\n"):
            raise ContractError("runtime_runs.jsonl endet nicht mit Newline")
        descriptor, name = tempfile.mkstemp(prefix="runtime-runs-", suffix=".tmp", dir=ledger.parent)
        os.close(descriptor)
        temp_path = Path(name)
        temp_path.write_bytes(existing + _canonical_bytes(receipt) + b"\n")
        os.replace(temp_path, ledger)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)


def _remove_tree(path: Path) -> None:
    def repair(function: Any, target: str, _: Any) -> None:
        os.chmod(target, 0o700)
        function(target)
    if path.exists():
        shutil.rmtree(path, onerror=repair)


def run_scenario(
    *, repo_root: Path, evidence_root: Path, contract_path: Path,
    scenario_id: str, runtime_run_id: str,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    evidence = evidence_root.resolve()
    contract_path = contract_path.resolve()
    if not (repo / ".git").exists():
        raise ContractError("repo_root ist kein Git-Worktree")
    if not evidence.is_dir() or _is_relative_to(evidence, repo) or _is_relative_to(repo, evidence):
        raise ContractError("evidence_root muss existieren und ausserhalb Produkt-Worktree liegen")
    if not ID_RE.fullmatch(runtime_run_id):
        raise ContractError("runtime_run_id ungueltig")
    if (evidence / ".runtime_runs.lock").exists():
        raise ContractError("Ledger-Lock existiert; auch stale Lock muss manuell untersucht werden")

    contract, contract_bytes, refs = _load_contract(evidence, contract_path)
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
    command, command_timeout = _validate_command(row.get("command"), "command", float(timeout), "audited")
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
    _create_lock(run_lock, "Runtime-Run")

    staging = staging_root / f"{runtime_run_id}-{uuid.uuid4().hex}"
    audited_root = staging / "audited"
    tooling_root = staging / "tooling"
    sealed_root = staging / "sealed"
    stage_run = staging / "run"
    stage_run.mkdir(parents=True)
    sealed_root.mkdir()
    success = False
    try:
        audited_materialization = _materialize_commit(repo, contract["audited_commit"], audited_root)
        tooling_materialization = _materialize_commit(repo, contract["tooling_commit"], tooling_root)
        audited_integrity = _snapshot_files(audited_root)
        tooling_integrity = _snapshot_files(tooling_root)

        sealed_records: list[dict[str, Any]] = []
        source_hashes: dict[Path, str] = {contract_path: _sha_bytes(contract_bytes)}
        contract_copy = sealed_root / "audit_contract.json"
        contract_copy.write_bytes(contract_bytes)
        os.chmod(contract_copy, 0o444)
        sealed_records.append({"name": "audit_contract", "ref": f"runs/{runtime_run_id}/sealed/audit_contract.json", "sha256": _sha(contract_copy)})
        for name, (source, data) in refs.items():
            source_hashes[source] = _sha_bytes(data)
            target = sealed_root / f"{name}{source.suffix or '.bin'}"
            target.write_bytes(data)
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
            target.write_bytes(data)
            os.chmod(target, 0o444)
            input_paths[name] = target
            input_receipts.append({"name": name, "source_ref": item["ref"], "ref": f"runs/{runtime_run_id}/sealed/inputs/{target.name}", "sha256": expected})

        sealed_integrity = _snapshot_files(sealed_root)

        argv, cwd, command_provenance = _resolve_command(
            command, root=audited_root, run_dir=stage_run, inputs=input_paths,
            executors=executors, label="command", commit=contract["audited_commit"],
        )
        observer = ObservationSink()
        observer_dir = staging / "observer-bootstrap"
        observer.write_bootstrap(observer_dir, row["symbol_probes"], audited_root)
        observer_integrity = _snapshot_files(observer_dir)
        environment = _sanitized_environment(audited_root, stage_run, observer_dir)
        exit_code, stdout, stderr, process_pid, start_ns, end_ns = _execute(
            argv, cwd=cwd, timeout=command_timeout, environment=environment,
            label="command", observer=observer,
        )
        _assert_sources_unchanged(source_hashes)
        _assert_snapshot(sealed_root, sealed_integrity, "Versiegelte Inputs nach Command")
        _assert_snapshot(audited_root, audited_integrity, "Auditcommit-Materialisierung nach Command")
        _assert_snapshot(tooling_root, tooling_integrity, "Toolingcommit-Materialisierung nach Command")
        _assert_snapshot(observer_dir, observer_integrity, "Runner-Instrumentation nach Command")
        if (stage_run / "trace.jsonl").exists():
            raise ContractError("trace.jsonl ist runner-reserviert; Scenario darf Trace nicht selbst schreiben")
        expected_exit_codes = row.get("expected_exit_codes", [0])
        if not isinstance(expected_exit_codes, list) or exit_code not in expected_exit_codes:
            raise ContractError(f"command: Exit {exit_code} nicht erwartet")
        observations, covered_symbols, covered_axes = _validate_observations(
            observer, process_pid=process_pid, start_ns=start_ns, end_ns=end_ns,
            feature=row["feature_target"], allowed_symbols=row["allowed_symbol_ids"],
            allowed_axes=row["allowed_axes"], probes=row["symbol_probes"],
        )
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
        post_environment = _sanitized_environment(tooling_root, stage_run, None)
        post_code, post_stdout, post_stderr, _, _, _ = _execute(
            post_argv, cwd=post_cwd, timeout=post_timeout, environment=post_environment,
            label="postcondition", observer=None,
        )
        _assert_sources_unchanged(source_hashes)
        _assert_snapshot(sealed_root, sealed_integrity, "Versiegelte Inputs nach Postcondition")
        _assert_snapshot(audited_root, audited_integrity, "Auditcommit-Materialisierung nach Postcondition")
        _assert_snapshot(tooling_root, tooling_integrity, "Toolingcommit-Materialisierung nach Postcondition")
        _assert_snapshot(observer_dir, observer_integrity, "Runner-Instrumentation nach Postcondition")
        _assert_snapshot(stage_run, before_checker, "Postcondition")
        if post_code != 0:
            raise ContractError(f"postcondition: Exit {post_code}")
        for axis in ("result", "live_evidence"):
            if axis in row["allowed_axes"]:
                covered_axes.append(axis)
                observations.append({
                    "observer": "runner-postcondition", "event": "pass",
                    "feature_path": row["feature_target"], "axis": axis,
                    "symbol_id": row["allowed_symbol_ids"][0],
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
        _assert_snapshot(observer_dir, observer_integrity, "Runner-Instrumentation vor Publish")
        os.replace(sealed_root, stage_run / "sealed")
        final_integrity = _snapshot_files(stage_run)
        timestamp = datetime.now(timezone.utc).isoformat()
        receipt: dict[str, Any] = {
            "run_id": contract["run_id"], "runtime_run_id": runtime_run_id,
            "audited_commit": contract["audited_commit"], "tooling_commit": contract["tooling_commit"],
            "snapshot_id": contract["snapshot_id"], "scenario_id": row["scenario_id"],
            "scenario_sha256": row["scenario_sha256"], "timestamp": timestamp,
            "audit_contract": {"ref": f"runs/{runtime_run_id}/sealed/audit_contract.json", "sha256": _sha_bytes(contract_bytes)},
            "scenario_catalog": {"ref": f"runs/{runtime_run_id}/sealed/scenario_catalog.jsonl", "sha256": _sha_bytes(catalog_bytes)},
            "sealed_contract_inputs": sealed_records,
            "materialization": {
                "method": "git-cat-file", "audited": audited_materialization,
                "tooling": tooling_materialization,
            },
            "runner": {"path": "tools/audit_runtime_evidence.py", "tooling_commit": contract["tooling_commit"], "sha256": runner_sha, "shell": False},
            "environment": {
                "python_no_user_site": True, "python_safe_path": True,
                "executor_manifest_sha256": _sha_bytes(refs["executor_manifest"][1]),
                "dependency_manifest_sha256": _sha_bytes(refs["dependency_manifest"][1]),
                "required_modules": row["required_modules"], "dependency_manifest": dependencies,
            },
            "observer": {"nonce_bound": True, "pid": process_pid, "start_ns": start_ns, "end_ns": end_ns, "events": len(observations)},
            "input": {"ref": input_receipts[0]["ref"], "sha256": input_receipts[0]["sha256"]} if len(input_receipts) == 1 else {"ref": "multiple", "sha256": canonical_sha256(input_receipts)},
            "inputs": input_receipts,
            "command": {"argv": command["argv"], "cwd": command["cwd"], "timeout_seconds": command_timeout, **command_provenance},
            "stdout": {"ref": f"runs/{runtime_run_id}/stdout.bin", **stdout_info},
            "stderr": {"ref": f"runs/{runtime_run_id}/stderr.bin", **stderr_info},
            "exit": {"code": exit_code, "ref": f"runs/{runtime_run_id}/command.log", **exit_info},
            "trace": {"ref": f"runs/{runtime_run_id}/trace.jsonl", **trace_info, "owner": "runner-observer-sink"},
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
        (stage_run / "receipt.json").write_bytes(_canonical_bytes(receipt) + b"\n")
        _assert_sources_unchanged(source_hashes)
        _assert_snapshot(stage_run, {**final_integrity, "receipt.json": _sha(stage_run / "receipt.json")}, "Finale Rehash")

        _remove_tree(audited_root)
        _remove_tree(tooling_root)
        if final_run.exists():
            raise ContractError(f"runtime_run_id {runtime_run_id!r} bereits vorhanden")
        os.replace(stage_run, final_run)
        try:
            _append_ledger_atomic(ledger, receipt)
        except Exception:
            _remove_tree(final_run)
            raise
        success = True
        return receipt
    finally:
        if staging.exists():
            _remove_tree(staging)
        run_lock.unlink(missing_ok=True)
        if not success and final_run.exists() and runtime_run_id not in _existing_runtime_ids(ledger)[0]:
            _remove_tree(final_run)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--audit-contract", type=Path, required=True)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--runtime-run-id", required=True)
    args = parser.parse_args()
    try:
        receipt = run_scenario(
            repo_root=args.root, evidence_root=args.evidence_root,
            contract_path=args.audit_contract, scenario_id=args.scenario_id,
            runtime_run_id=args.runtime_run_id,
        )
    except ContractError as exc:
        print(f"FEHLER: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
