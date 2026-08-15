#!/usr/bin/env python3
"""Execute immutable audit scenarios and emit content-addressed evidence.

Scenario rows are declarations. Coverage is derived only from trace rows emitted
by the executed process; callers cannot pass a trusted evidence-id set.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
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
REQUIRED_SCENARIO_FIELDS = {
    "schema_version", "run_id", "scenario_id", "audited_commit", "tooling_commit",
    "snapshot_id", "scenario_sha256", "feature_target", "command",
    "timeout_seconds", "inputs", "allowed_symbol_ids", "allowed_axes",
    "postcondition", "artifacts",
}


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


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args], cwd=repo, check=check, capture_output=True, shell=False,
    )


def _contained(root: Path, candidate: Path, label: str) -> Path:
    root = root.resolve()
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ContractError(f"{label} liegt ausserhalb erlaubter Wurzel") from exc
    return candidate


def _relative_ref(root: Path, ref: object, label: str) -> Path:
    if not isinstance(ref, str) or not ref.strip():
        raise ContractError(f"{label}: ref fehlt")
    path = Path(ref)
    if path.is_absolute():
        raise ContractError(f"{label}: absoluter Pfad verboten")
    return _contained(root, root / path, label)


def _load_catalog(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ContractError(f"Scenario-Katalog unlesbar: {exc}") from exc
    if not lines:
        raise ContractError("Scenario-Katalog ist leer")
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractError(f"Scenario-Katalog Zeile {number}: ungueltiges JSON") from exc
        if not isinstance(row, dict):
            raise ContractError(f"Scenario-Katalog Zeile {number}: Objekt erwartet")
        scenario_id = row.get("scenario_id")
        if not isinstance(scenario_id, str) or not ID_RE.fullmatch(scenario_id):
            raise ContractError(f"Scenario-Katalog Zeile {number}: scenario_id ungueltig")
        if scenario_id in rows:
            raise ContractError(f"Scenario-Katalog: scenario_id {scenario_id!r} doppelt")
        missing = sorted(REQUIRED_SCENARIO_FIELDS - row.keys())
        if missing:
            raise ContractError(f"Scenario {scenario_id}: Pflichtfelder fehlen: {', '.join(missing)}")
        expected = canonical_sha256(row, omit={"scenario_sha256"})
        if row.get("scenario_sha256") != expected:
            raise ContractError(f"Scenario {scenario_id}: scenario_sha256 stimmt nicht")
        rows[scenario_id] = row
    if not rows:
        raise ContractError("Scenario-Katalog enthaelt keine Records")
    return rows


def _validate_string_list(row: dict[str, Any], field: str) -> list[str]:
    value = row.get(field)
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise ContractError(f"Scenario {row.get('scenario_id')}: {field} fehlt/ungueltig")
    if len(value) != len(set(value)):
        raise ContractError(f"Scenario {row.get('scenario_id')}: {field} enthaelt Duplikate")
    return value


def _validate_command(command: object, label: str, fallback_timeout: float) -> tuple[dict[str, Any], float]:
    if not isinstance(command, dict):
        raise ContractError(f"{label}: Objekt fehlt")
    argv = command.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) and arg for arg in argv):
        raise ContractError(f"{label}.argv fehlt/ungueltig")
    cwd = command.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        raise ContractError(f"{label}.cwd fehlt")
    timeout = command.get("timeout_seconds", fallback_timeout)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0 or timeout > 86400:
        raise ContractError(f"{label}.timeout_seconds ungueltig")
    return command, float(timeout)


def _verify_tool_identity(repo: Path, tooling_commit: str) -> str:
    if not SHA_RE.fullmatch(tooling_commit):
        raise ContractError("tooling_commit muss voller 40-Zeichen-SHA sein")
    if _git(repo, "cat-file", "-e", f"{tooling_commit}^{{commit}}", check=False).returncode != 0:
        raise ContractError("tooling_commit existiert nicht im Repository")
    result = _git(repo, "show", f"{tooling_commit}:tools/audit_runtime_evidence.py", check=False)
    if result.returncode != 0:
        raise ContractError("Runner fehlt im tooling_commit")
    current = Path(__file__).read_bytes()
    if result.stdout != current:
        raise ContractError("ausgefuehrter Runner stimmt nicht mit tooling_commit ueberein")
    return hashlib.sha256(result.stdout).hexdigest()


def _validate_scenario(
    row: dict[str, Any], *, repo: Path, evidence: Path,
) -> tuple[list[dict[str, str]], list[str], list[str], list[int]]:
    scenario_id = row["scenario_id"]
    if row.get("schema_version") != 1:
        raise ContractError(f"Scenario {scenario_id}: schema_version muss 1 sein")
    for field in ("run_id", "snapshot_id", "feature_target"):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ContractError(f"Scenario {scenario_id}: {field} fehlt")
    for field in ("audited_commit", "tooling_commit"):
        value = row.get(field)
        if not isinstance(value, str) or not SHA_RE.fullmatch(value):
            raise ContractError(f"Scenario {scenario_id}: {field} muss voller SHA sein")
        if _git(repo, "cat-file", "-e", f"{value}^{{commit}}", check=False).returncode != 0:
            raise ContractError(f"Scenario {scenario_id}: {field} existiert nicht")
    timeout = row.get("timeout_seconds")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or timeout <= 0 or timeout > 86400:
        raise ContractError(f"Scenario {scenario_id}: timeout_seconds ungueltig")
    _validate_command(row.get("command"), f"Scenario {scenario_id}/command", float(timeout))
    _validate_command(row.get("postcondition"), f"Scenario {scenario_id}/postcondition", float(timeout))

    symbols = _validate_string_list(row, "allowed_symbol_ids")
    axes = _validate_string_list(row, "allowed_axes")
    unknown_axes = sorted(set(axes) - KNOWN_AXES)
    if unknown_axes:
        raise ContractError(f"Scenario {scenario_id}: unbekannte allowed_axes: {unknown_axes}")

    expected_exit_codes = row.get("expected_exit_codes", [0])
    if (
        not isinstance(expected_exit_codes, list) or not expected_exit_codes
        or not all(type(code) is int for code in expected_exit_codes)
        or len(expected_exit_codes) != len(set(expected_exit_codes))
    ):
        raise ContractError(f"Scenario {scenario_id}: expected_exit_codes ungueltig")

    inputs = row.get("inputs")
    if not isinstance(inputs, list):
        raise ContractError(f"Scenario {scenario_id}: inputs muss Liste sein")
    input_rows: list[dict[str, str]] = []
    input_names: set[str] = set()
    for index, item in enumerate(inputs):
        if not isinstance(item, dict):
            raise ContractError(f"Scenario {scenario_id}/inputs[{index}]: Objekt erwartet")
        name = item.get("name")
        if not isinstance(name, str) or not ID_RE.fullmatch(name) or name in input_names:
            raise ContractError(f"Scenario {scenario_id}/inputs[{index}]: name fehlt/doppelt")
        input_names.add(name)
        path = _relative_ref(evidence, item.get("ref"), f"Scenario {scenario_id}/inputs[{index}]")
        if not path.is_file():
            raise ContractError(f"Scenario {scenario_id}: Input fehlt: {item.get('ref')}")
        expected = item.get("sha256")
        if not isinstance(expected, str) or not HASH_RE.fullmatch(expected) or _sha(path) != expected:
            raise ContractError(f"Scenario {scenario_id}: Input-Hash stimmt nicht: {item.get('ref')}")
        input_rows.append({"name": name, "ref": str(item["ref"]), "sha256": expected})

    artifacts = row.get("artifacts")
    if not isinstance(artifacts, list):
        raise ContractError(f"Scenario {scenario_id}: artifacts muss Liste sein")
    artifact_names: set[str] = set()
    artifact_refs: set[str] = set()
    for index, item in enumerate(artifacts):
        if not isinstance(item, dict):
            raise ContractError(f"Scenario {scenario_id}/artifacts[{index}]: Objekt erwartet")
        name, ref = item.get("name"), item.get("ref")
        if not isinstance(name, str) or not ID_RE.fullmatch(name) or name in artifact_names:
            raise ContractError(f"Scenario {scenario_id}/artifacts[{index}]: name fehlt/doppelt")
        if not isinstance(ref, str) or not ref or ref in artifact_refs or Path(ref).is_absolute():
            raise ContractError(f"Scenario {scenario_id}/artifacts[{index}]: ref fehlt/doppelt/absolut")
        _contained(Path("C:/pb-audit-sentinel"), Path("C:/pb-audit-sentinel") / ref, f"Scenario {scenario_id}/artifact")
        if item.get("required") is not True:
            raise ContractError(f"Scenario {scenario_id}/artifacts[{index}]: required muss true sein")
        artifact_names.add(name)
        artifact_refs.add(ref)
    return input_rows, symbols, axes, expected_exit_codes


def _expand_arg(
    arg: str, *, audit_root: Path, cwd: Path, run_dir: Path,
    trace_path: Path, inputs: dict[str, Path], label: str,
) -> str:
    replacements = {"{run_dir}": str(run_dir), "{trace_path}": str(trace_path)}
    for name, path in inputs.items():
        replacements[f"{{input:{name}}}"] = str(path)
    expanded = arg
    for marker, value in replacements.items():
        expanded = expanded.replace(marker, value)
    if "{" in expanded or "}" in expanded:
        raise ContractError(f"{label}: unbekannter Placeholder in {arg!r}")
    pathish = Path(expanded)
    if ".." in pathish.parts:
        raise ContractError(f"{label}: Pfad-Escape verboten: {arg!r}")
    if pathish.is_absolute():
        resolved = pathish.resolve()
        allowed_roots = [audit_root.resolve(), run_dir.resolve(), *[p.resolve() for p in inputs.values()]]
        if not any(resolved == root or (root.is_dir() and _is_relative_to(resolved, root)) for root in allowed_roots):
            raise ContractError(f"{label}: absoluter Pfad ausserhalb erlaubter Wurzeln")
    return expanded


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_argv(
    command: dict[str, Any], *, audit_root: Path, cwd: Path, run_dir: Path,
    trace_path: Path, inputs: dict[str, Path], label: str,
) -> list[str]:
    raw = command["argv"]
    executable = raw[0]
    aliases = {"python", "python3", "python.exe", Path(sys.executable).name.lower(), sys.executable.lower()}
    if executable.lower() in aliases:
        resolved_executable = sys.executable
    elif executable.lower() in {"ffmpeg", "ffmpeg.exe", "ffprobe", "ffprobe.exe"}:
        filename = "ffprobe.exe" if "ffprobe" in executable.lower() else "ffmpeg.exe"
        candidate = audit_root / "bin" / filename
        if not candidate.is_file():
            raise ContractError(f"{label}: erlaubtes Executable fehlt im Auditcommit: {filename}")
        resolved_executable = str(candidate)
    else:
        raise ContractError(f"{label}: Executable {executable!r} ist nicht erlaubt")
    args = [resolved_executable]
    for index, arg in enumerate(raw[1:], 1):
        args.append(_expand_arg(
            arg, audit_root=audit_root, cwd=cwd, run_dir=run_dir,
            trace_path=trace_path, inputs=inputs, label=f"{label}.argv[{index}]",
        ))
    if resolved_executable == sys.executable:
        if len(args) < 2 or args[1].startswith("-") or Path(args[1]).suffix.lower() != ".py":
            raise ContractError(f"{label}: Python braucht gebundenes .py-Script aus Auditcommit")
        script = Path(args[1])
        script = script if script.is_absolute() else cwd / script
        script = _contained(audit_root, script, f"{label}.argv[1]")
        if not script.is_file():
            raise ContractError(f"{label}: Python-Script fehlt im Auditcommit: {raw[1]}")
    return args


def _command_provenance(
    *, audit_root: Path, cwd: Path, declared_argv: list[str], resolved_argv: list[str],
) -> dict[str, Any]:
    executor = Path(resolved_argv[0]).resolve()
    if not executor.is_file():
        raise ContractError("Command-Executor fehlt")
    if executor == Path(sys.executable).resolve():
        source = Path(resolved_argv[1])
        source = source if source.is_absolute() else cwd / source
    else:
        source = executor
    source = _contained(audit_root, source, "Command-Quelle")
    relative = source.relative_to(audit_root).as_posix()
    blob = _git(audit_root, "rev-parse", f"HEAD:{relative}", check=False)
    if blob.returncode != 0:
        raise ContractError(f"Command-Quelle ist kein Blob aus audited_commit: {relative}")
    return {
        "declared_executable": declared_argv[0],
        "executor": {"path": str(executor), "sha256": _sha(executor)},
        "source": {
            "path": relative,
            "git_blob": blob.stdout.decode().strip(),
            "sha256": _sha(source),
        },
    }


def _kill_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True, check=False, shell=False,
        )
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
        pass


def _execute(
    argv: list[str], *, cwd: Path, timeout: float, environment: dict[str, str], label: str,
) -> tuple[int, bytes, bytes]:
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
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
    return process.returncode, stdout, stderr


def _command_environment(*, audit_root: Path, run_dir: Path, trace_path: Path) -> dict[str, str]:
    keep = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL")
    environment = {key: os.environ[key] for key in keep if key in os.environ}
    environment.update({
        "PB_AUDIT_ROOT": str(audit_root),
        "PB_AUDIT_RUN_DIR": str(run_dir),
        "PB_AUDIT_TRACE_PATH": str(trace_path),
        "PYTHONPATH": str(audit_root),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    return environment


def _write(path: Path, data: bytes) -> dict[str, Any]:
    path.write_bytes(data)
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _trace_coverage(
    trace_path: Path, *, feature: str, allowed_symbols: list[str], allowed_axes: list[str],
) -> tuple[list[str], list[str]]:
    if not trace_path.is_file():
        raise ContractError("Trace fehlt; Coverage kann nicht abgeleitet werden")
    try:
        rows = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError("Trace ist kein gueltiges JSONL") from exc
    if not rows:
        raise ContractError("Trace ist leer")
    symbols: set[str] = set()
    axes: set[str] = set()
    events_by_axis: dict[str, set[str]] = {}
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ContractError(f"Trace Zeile {number}: Objekt erwartet")
        if row.get("feature_path") != feature:
            raise ContractError(f"Trace Zeile {number}: fremder Featurepfad")
        symbol, axis, event = row.get("symbol_id"), row.get("axis"), row.get("event")
        if symbol not in allowed_symbols:
            raise ContractError(f"Trace Zeile {number}: fremdes Symbol")
        if axis not in allowed_axes:
            raise ContractError(f"Trace Zeile {number}: fremde Achse")
        if not isinstance(event, str) or not event:
            raise ContractError(f"Trace Zeile {number}: event fehlt")
        symbols.add(symbol)
        axes.add(axis)
        events_by_axis.setdefault(axis, set()).add(event)
    if symbols != set(allowed_symbols):
        raise ContractError("Trace beobachtet nicht exakt alle gebundenen Symbole")
    if axes != set(allowed_axes):
        raise ContractError("Trace beobachtet nicht exakt alle gebundenen Achsen")
    for axis in {"error", "cancel", "retry"} & axes:
        if "forced" not in events_by_axis[axis]:
            raise ContractError(f"Trace-Achse {axis} braucht event=forced")
    if "restart_safe" in axes and not {"restart", "reopen"}.issubset(events_by_axis["restart_safe"]):
        raise ContractError("Trace-Achse restart_safe braucht restart- und reopen-Event")
    for axis in {"GPU", "DB", "UI"} & axes:
        if "observed" not in events_by_axis[axis]:
            raise ContractError(f"Trace-Achse {axis} braucht event=observed")
    return sorted(symbols), sorted(axes)


def _existing_runtime_ids(ledger: Path) -> tuple[set[str], set[str]]:
    if not ledger.exists():
        return set(), set()
    runtime_ids: set[str] = set()
    evidence_ids: set[str] = set()
    try:
        rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"bestehendes runtime_runs.jsonl unlesbar: {exc}") from exc
    for row in rows:
        if not isinstance(row, dict):
            raise ContractError("bestehendes runtime_runs.jsonl enthaelt Nicht-Objekt")
        runtime_id, evidence_id = row.get("runtime_run_id"), row.get("evidence_id")
        if not isinstance(runtime_id, str) or runtime_id in runtime_ids:
            raise ContractError("bestehendes runtime_runs.jsonl hat fehlende/doppelte runtime_run_id")
        if not isinstance(evidence_id, str) or evidence_id in evidence_ids:
            raise ContractError("bestehendes runtime_runs.jsonl hat fehlende/doppelte evidence_id")
        runtime_ids.add(runtime_id)
        evidence_ids.add(evidence_id)
    return runtime_ids, evidence_ids


def _append_ledger_atomic(ledger: Path, receipt: dict[str, Any]) -> None:
    lock_path = ledger.parent / ".runtime_runs.lock"
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ContractError("runtime_runs.jsonl wird bereits atomar aktualisiert") from exc
    os.close(lock_fd)
    temp_path: Path | None = None
    try:
        runtime_ids, evidence_ids = _existing_runtime_ids(ledger)
        if receipt["runtime_run_id"] in runtime_ids or receipt["evidence_id"] in evidence_ids:
            raise ContractError("Runtime-Receipt bereits im Ledger vorhanden")
        existing = ledger.read_bytes() if ledger.exists() else b""
        if existing and not existing.endswith(b"\n"):
            raise ContractError("runtime_runs.jsonl endet nicht mit Newline")
        payload = existing + _canonical_bytes(receipt) + b"\n"
        fd, temp_name = tempfile.mkstemp(prefix="runtime-runs-", suffix=".tmp", dir=ledger.parent)
        os.close(fd)
        temp_path = Path(temp_name)
        temp_path.write_bytes(payload)
        os.replace(temp_path, ledger)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        lock_path.unlink(missing_ok=True)


def run_scenario(
    *, repo_root: Path, evidence_root: Path, catalog_path: Path,
    scenario_id: str, runtime_run_id: str,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    evidence = evidence_root.resolve()
    catalog = catalog_path.resolve()
    if not (repo / ".git").exists():
        raise ContractError("repo_root ist kein Git-Worktree")
    if not evidence.is_dir():
        raise ContractError("evidence_root fehlt")
    if _is_relative_to(evidence, repo) or _is_relative_to(repo, evidence):
        raise ContractError("evidence_root muss ausserhalb Produkt-Worktree liegen")
    _contained(evidence, catalog, "scenario_catalog")
    if not catalog.is_file():
        raise ContractError("scenario_catalog fehlt")
    if not ID_RE.fullmatch(runtime_run_id):
        raise ContractError("runtime_run_id ungueltig")

    rows = _load_catalog(catalog)
    if scenario_id not in rows:
        raise ContractError(f"Scenario {scenario_id!r} unbekannt")
    row = rows[scenario_id]
    input_rows, allowed_symbols, allowed_axes, expected_exit_codes = _validate_scenario(
        row, repo=repo, evidence=evidence,
    )
    runner_sha = _verify_tool_identity(repo, row["tooling_commit"])

    runs_root = evidence / "runs"
    staging_root = evidence / ".staging"
    runs_root.mkdir(exist_ok=True)
    staging_root.mkdir(exist_ok=True)
    final_run = runs_root / runtime_run_id
    ledger = evidence / "runtime_runs.jsonl"
    runtime_ids, evidence_ids = _existing_runtime_ids(ledger)
    if runtime_run_id in runtime_ids or final_run.exists():
        raise ContractError(f"runtime_run_id {runtime_run_id!r} bereits vorhanden")

    lock_path = runs_root / f".{runtime_run_id}.lock"
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ContractError(f"runtime_run_id {runtime_run_id!r} bereits in Arbeit") from exc
    os.close(lock_fd)

    staging = staging_root / f"{runtime_run_id}-{uuid.uuid4().hex}"
    audit_root = staging / "audited-worktree"
    stage_run = staging / "run"
    stage_run.mkdir(parents=True)
    worktree_added = False
    success = False
    try:
        add = _git(repo, "worktree", "add", "--detach", "--quiet", str(audit_root), row["audited_commit"], check=False)
        if add.returncode != 0:
            raise ContractError(f"detached Auditworktree nicht erstellbar: {add.stderr.decode(errors='replace').strip()}")
        worktree_added = True
        actual_commit = _git(audit_root, "rev-parse", "HEAD").stdout.decode().strip()
        if actual_commit != row["audited_commit"]:
            raise ContractError("detached Auditworktree weicht von audited_commit ab")

        input_paths = {
            item["name"]: _relative_ref(evidence, item["ref"], f"Input {item['name']}")
            for item in input_rows
        }
        trace_path = stage_run / "trace.jsonl"
        command, command_timeout = _validate_command(row["command"], "command", float(row["timeout_seconds"]))
        cwd = _contained(audit_root, audit_root / command["cwd"], "command.cwd")
        if not cwd.is_dir():
            raise ContractError("command.cwd fehlt im Auditcommit")
        argv = _resolve_argv(
            command, audit_root=audit_root, cwd=cwd, run_dir=stage_run,
            trace_path=trace_path, inputs=input_paths, label="command",
        )
        command_provenance = _command_provenance(
            audit_root=audit_root, cwd=cwd, declared_argv=command["argv"], resolved_argv=argv,
        )
        environment = _command_environment(audit_root=audit_root, run_dir=stage_run, trace_path=trace_path)
        exit_code, stdout, stderr = _execute(
            argv, cwd=cwd, timeout=command_timeout, environment=environment, label="command",
        )
        stdout_info = _write(stage_run / "stdout.bin", stdout)
        stderr_info = _write(stage_run / "stderr.bin", stderr)
        combined = b"STDOUT\n" + stdout + b"\nSTDERR\n" + stderr
        exit_info = _write(stage_run / "command.log", combined)
        if exit_code not in expected_exit_codes:
            raise ContractError(f"command: Exit {exit_code} nicht in expected_exit_codes")

        symbols, axes = _trace_coverage(
            trace_path, feature=row["feature_target"],
            allowed_symbols=allowed_symbols, allowed_axes=allowed_axes,
        )
        trace_info = {"bytes": trace_path.stat().st_size, "sha256": _sha(trace_path)}

        input_manifest_bytes = _canonical_bytes(input_rows) + b"\n"
        input_manifest_info = _write(stage_run / "inputs.json", input_manifest_bytes)

        post, post_timeout = _validate_command(row["postcondition"], "postcondition", float(row["timeout_seconds"]))
        post_cwd = _contained(audit_root, audit_root / post["cwd"], "postcondition.cwd")
        if not post_cwd.is_dir():
            raise ContractError("postcondition.cwd fehlt im Auditcommit")
        post_argv = _resolve_argv(
            post, audit_root=audit_root, cwd=post_cwd, run_dir=stage_run,
            trace_path=trace_path, inputs=input_paths, label="postcondition",
        )
        post_provenance = _command_provenance(
            audit_root=audit_root, cwd=post_cwd,
            declared_argv=post["argv"], resolved_argv=post_argv,
        )
        post_code, post_stdout, post_stderr = _execute(
            post_argv, cwd=post_cwd, timeout=post_timeout, environment=environment,
            label="postcondition",
        )
        post_stdout_info = _write(stage_run / "postcondition.stdout.bin", post_stdout)
        post_stderr_info = _write(stage_run / "postcondition.stderr.bin", post_stderr)
        post_payload = {
            "checker_argv": post["argv"], "exit_code": post_code,
            "stdout_sha256": post_stdout_info["sha256"],
            "stderr_sha256": post_stderr_info["sha256"],
            "result": "pass" if post_code == 0 else "fail",
        }
        post_bytes = _canonical_bytes(post_payload) + b"\n"
        post_info = _write(stage_run / "postcondition.json", post_bytes)
        if post_code != 0:
            raise ContractError(f"postcondition: Exit {post_code}")

        artifact_records: list[dict[str, Any]] = []
        for item in row["artifacts"]:
            artifact_path = _relative_ref(stage_run, item["ref"], f"Artefakt {item['name']}")
            if not artifact_path.is_file():
                raise ContractError(f"Artefakt fehlt: {item['ref']}")
            artifact_records.append({
                "name": item["name"], "ref": f"runs/{runtime_run_id}/{item['ref']}",
                "bytes": artifact_path.stat().st_size, "sha256": _sha(artifact_path),
            })

        timestamp = datetime.now(timezone.utc).isoformat()
        receipt: dict[str, Any] = {
            "run_id": row["run_id"],
            "runtime_run_id": runtime_run_id,
            "audited_commit": row["audited_commit"],
            "tooling_commit": row["tooling_commit"],
            "snapshot_id": row["snapshot_id"],
            "scenario_id": row["scenario_id"],
            "scenario_sha256": row["scenario_sha256"],
            "scenario_catalog": {"ref": str(catalog.relative_to(evidence)), "sha256": _sha(catalog)},
            "timestamp": timestamp,
            "runner": {
                "path": "tools/audit_runtime_evidence.py",
                "tooling_commit": row["tooling_commit"],
                "sha256": runner_sha,
                "shell": False,
            },
            "input": {"ref": f"runs/{runtime_run_id}/inputs.json", **input_manifest_info},
            "inputs": input_rows,
            "command": {
                "argv": command["argv"], "cwd": command["cwd"],
                "timeout_seconds": command_timeout, **command_provenance,
            },
            "stdout": {"ref": f"runs/{runtime_run_id}/stdout.bin", **stdout_info},
            "stderr": {"ref": f"runs/{runtime_run_id}/stderr.bin", **stderr_info},
            "exit": {"code": exit_code, "ref": f"runs/{runtime_run_id}/command.log", **exit_info},
            "trace": {"ref": f"runs/{runtime_run_id}/trace.jsonl", **trace_info},
            "postcondition": {
                "ref": f"runs/{runtime_run_id}/postcondition.json", **post_info,
                "result": "pass", "checker_exit_code": post_code,
                "checker": post_provenance,
            },
            "artifacts": artifact_records,
            "covered_feature_paths": [row["feature_target"]],
            "covered_symbol_ids": symbols,
            "covered_axes": axes,
        }
        forced_axes = sorted({"error", "cancel", "retry"} & set(axes))
        if len(forced_axes) > 1:
            raise ContractError("ein Runtime-Run darf nur einen erzwungenen Zustand belegen")
        if forced_axes:
            receipt["forced_state"] = forced_axes[0]
        surfaces = sorted({"GPU", "DB", "UI"} & set(axes))
        if surfaces:
            receipt["observed_surfaces"] = surfaces
        if "restart_safe" in axes:
            receipt["restart"] = True
            receipt["reopen"] = True
        receipt["evidence_id"] = canonical_evidence_id(receipt)
        if receipt["evidence_id"] in evidence_ids:
            raise ContractError("evidence_id bereits vorhanden")
        (stage_run / "receipt.json").write_bytes(_canonical_bytes(receipt) + b"\n")

        if final_run.exists():
            raise ContractError(f"runtime_run_id {runtime_run_id!r} bereits vorhanden")
        os.replace(stage_run, final_run)
        try:
            _append_ledger_atomic(ledger, receipt)
        except Exception:
            shutil.rmtree(final_run, ignore_errors=True)
            raise
        success = True
        return receipt
    finally:
        if worktree_added:
            _git(repo, "worktree", "remove", "--force", str(audit_root), check=False)
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        lock_path.unlink(missing_ok=True)
        if not success and final_run.exists() and runtime_run_id not in _existing_runtime_ids(ledger)[0]:
            shutil.rmtree(final_run, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--scenario-catalog", type=Path, required=True)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--runtime-run-id", required=True)
    args = parser.parse_args()
    try:
        receipt = run_scenario(
            repo_root=args.root,
            evidence_root=args.evidence_root,
            catalog_path=args.scenario_catalog,
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
