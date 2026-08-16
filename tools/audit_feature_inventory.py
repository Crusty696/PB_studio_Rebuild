#!/usr/bin/env python3
"""Deterministic requirements/trigger universe for a frozen Git commit.

This harness deliberately emits *candidates*.  It never claims that a
candidate is a working feature.  Exact-set validation makes every generated
candidate receive exactly one explicit feature/support/dead-candidate
disposition.
"""
from __future__ import annotations

import argparse
import ast
import configparser
import hashlib
import io
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tokenize
import tomllib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


DISPOSITIONS = {"feature", "support", "dead-candidate"}
PLAN_ID = "PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15"
AUDIT_ARTIFACT_KEYS = {
    "requirements-universe", "trigger-universe", "feature-catalog",
    "symbol-catalog", "edge-catalog", "runtime-scenario-catalog",
    "runtime-feature-universe", "runtime-symbol-universe",
    "runtime-executor-manifest", "runtime-dependency-manifest",
    "reviewer-trust-policy", "reviewer-contract", "reviewer-readiness-binding",
    "reviewer-spawn-journal",
}
EVIDENCE_ARTIFACT_KEYS = {
    "feature-state", "feature-state-evidence", "symbol-state", "edge-state",
    "symbol-state-evidence", "reviewer-roster", "runtime-evidence", "delta-ledger",
}
ATTACHMENT_KEY = re.compile(
    r"(?:feature-proof|symbol-proof|runtime-proof):[^\s]+"
    r"|reviewer-enrollment-(?:receipt|signature):[^:\s]+"
    r"|reviewer-signoff(?:-signature)?:[^:\s]+:[^:\s]+"
)
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
SUPPORTED_SQL_DIALECT = "sqlite"
NORMATIVE = re.compile(
    r"\b(muss|muessen|müssen|pflicht|required|must|shall|darf\s+nicht|forbidden)\b",
    re.IGNORECASE,
)
UI_TEXT_CALLS = {
    "QAction", "QPushButton", "QToolButton", "QCheckBox", "QRadioButton",
    "setText", "setTitle", "setWindowTitle", "addAction", "addButton",
    "addTab", "addMenu", "setPlaceholderText",
}
INTERACTIVE_UI_CALLS = {
    "QAction", "QPushButton", "QToolButton", "QCheckBox", "QRadioButton",
    "addAction", "addButton", "addTab", "addMenu",
}
CONFIG_ACCESS_CALLS = {"value", "setValue", "getenv", "getboolean", "getint", "getfloat"}
TRIGGER_CALLS = {
    "connect": "qt-connect",
    "addAction": "qt-action",
    "addButton": "qt-button",
    "setShortcut": "qt-shortcut",
    "singleShot": "timer",
    "startTimer": "timer",
    "add_argument": "cli",
    "register": "registry",
    "subscribe": "callback",
    "emit": "qt-signal-emit",
    "listen": "db-callback",
    "add_listener": "db-callback",
}
TRIGGER_SOURCE_KINDS = {
    "batch-entrypoint", "batch-label", "callback", "cli", "db-callback",
    "decorator-hook", "entrypoint", "main-guard", "powershell-entrypoint",
    "powershell-function", "powershell-parameter", "qt-action", "qt-button",
    "qt-connect", "qt-shortcut", "qt-signal-emit", "qt-ui-signal",
    "qt-ui-surface", "qt-ui-widget", "registry", "shutdown", "sql-trigger",
    "startup", "timer",
}
LIFECYCLE_NAMES = {
    "main": "entrypoint", "startup": "startup", "shutdown": "shutdown",
    "closeEvent": "shutdown", "showEvent": "startup", "timerEvent": "timer",
}
TEXT_SUFFIXES = {".md", ".rst", ".txt"}
CONFIG_SUFFIXES = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
SCRIPT_SUFFIXES = {".ps1", ".psm1", ".bat", ".cmd"}
RELEVANT_SUFFIXES = {".py", ".sql", ".ui", ".ts", *TEXT_SUFFIXES, *CONFIG_SUFFIXES, *SCRIPT_SUFFIXES}


class ContractError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _enum_value(value: Any, allowed: set[str]) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value in allowed


def _without(row: dict[str, Any], *fields: str) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key not in fields}


def seal_record(row: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(row)
    sealed["record_sha256"] = _sha(_canonical(_without(sealed, "record_sha256")))
    return sealed


def make_artifact_manifest(
    kind: str, records: list[dict[str, Any]], *, run_id: str,
    audited_commit: str, tooling_commit: str, snapshot_id: str,
) -> dict[str, Any]:
    records_sha = _sha(b"".join(_canonical(row) + b"\n" for row in records))
    manifest = {
        "schema_version": 1, "kind": kind, "run_id": run_id,
        "audited_commit": audited_commit, "tooling_commit": tooling_commit,
        "snapshot_id": snapshot_id, "record_count": len(records),
        "records_sha256": records_sha,
    }
    manifest["artifact_id"] = "sha256:" + records_sha
    return manifest


def _jsonl_bytes(records: list[dict[str, Any]]) -> bytes:
    return b"".join(_canonical(row) + b"\n" for row in records)


def artifact_contract_entry(records: list[dict[str, Any]], ref: str) -> dict[str, Any]:
    data = _jsonl_bytes(records)
    digest = _sha(data)
    return {
        "artifact_id": f"sha256:{digest}", "ref": ref, "sha256": digest,
        "bytes": len(data), "record_count": len(records),
    }


def file_contract_entry(data: bytes, ref: str, *, record_count: int = 1) -> dict[str, Any]:
    digest = _sha(data)
    return {
        "artifact_id": f"sha256:{digest}", "ref": ref, "sha256": digest,
        "bytes": len(data), "record_count": record_count,
    }


def seal_audit_contract(core: dict[str, Any]) -> dict[str, Any]:
    contract = dict(core)
    contract["contract_sha256"] = _sha(_canonical(_without(contract, "contract_sha256")))
    return contract


def seal_evidence_contract(core: dict[str, Any]) -> dict[str, Any]:
    contract = dict(core)
    contract["evidence_contract_sha256"] = _sha(
        _canonical(_without(contract, "evidence_contract_sha256"))
    )
    return contract


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _safe_ref(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    if (
        path == PurePosixPath(".") or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        return False
    windows_unsafe = any(
        ":" in part
        or part.endswith((".", " "))
        or part.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES
        for part in path.parts
    )
    return value == path.as_posix() and not windows_unsafe


def _proof_errors(
    row: dict[str, Any], contract: dict[str, Any], evidence_root: Path,
    *, prefix: str, expected: dict[str, Any], label: str,
) -> list[str]:
    errors: list[str] = []
    ref = row.get("proof_ref")
    key = f"{prefix}:{row.get('evidence_id', '')}"
    artifacts = contract.get("artifacts")
    descriptor = artifacts.get(key) if isinstance(artifacts, dict) else None
    if not isinstance(descriptor, dict):
        return [f"{label}: Proof-Descriptor {key} fehlt"]
    if descriptor.get("ref") != ref:
        errors.append(f"{label}: Proof-Descriptor ref weicht ab")
    if not _safe_ref(ref):
        return errors + [f"{label}: proof_ref ungueltig"]
    try:
        root = evidence_root.resolve(strict=True)
        target = (root / str(ref)).resolve(strict=False)
        target.relative_to(root)
    except (FileNotFoundError, OSError, ValueError):
        return errors + [f"{label}: Proof-Pfad ausserhalb Evidence-Root/Root fehlt"]
    if not target.exists():
        return errors + [f"{label}: Proof-Datei fehlt"]
    if not target.is_file():
        return errors + [f"{label}: Proof ist keine regulaere Datei"]
    try:
        data = target.read_bytes()
    except OSError as exc:
        return errors + [f"{label}: Proof nicht lesbar: {exc}"]
    digest = _sha(data)
    if row.get("proof_sha256") != digest:
        errors.append(f"{label}: proof_sha256 weicht von Proof-Datei ab")
    if descriptor.get("bytes") != len(data):
        errors.append(f"{label}: Proof bytes weichen ab")
    if descriptor.get("sha256") != digest or descriptor.get("artifact_id") != f"sha256:{digest}":
        errors.append(f"{label}: Proof SHA/artifact_id weicht ab")
    if descriptor.get("record_count") != 1:
        errors.append(f"{label}: Proof record_count muss 1 sein")
    try:
        proof = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        errors.append(f"{label}: Proof ist kein UTF-8-JSON")
    else:
        if proof != expected:
            errors.append(f"{label}: Proof-Semantik/FK weicht ab")
    return errors


def _validate_artifact_entries(artifacts: object, label: str) -> list[str]:
    if not isinstance(artifacts, dict) or not artifacts:
        return [f"{label}: artifacts fehlt/leer"]
    errors: list[str] = []
    for key, entry in artifacts.items():
        row_label = f"{label}/{key}"
        if not isinstance(key, str) or not key or not isinstance(entry, dict):
            errors.append(f"{row_label}: Artifacteintrag ungueltig")
            continue
        expected_fields = {"artifact_id", "ref", "sha256", "bytes", "record_count"}
        if set(entry) != expected_fields:
            errors.append(f"{row_label}: Artifactfelder nicht exakt")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(f"{row_label}: sha256 ungueltig")
        if entry.get("artifact_id") != f"sha256:{digest}":
            errors.append(f"{row_label}: artifact_id ungueltig")
        if not _safe_ref(entry.get("ref")):
            errors.append(f"{row_label}: ref nicht sicher/relativ")
        if type(entry.get("bytes")) is not int or entry.get("bytes", -1) < 0:
            errors.append(f"{row_label}: bytes ungueltig")
        if type(entry.get("record_count")) is not int or entry.get("record_count", -1) < 0:
            errors.append(f"{row_label}: record_count ungueltig")
    return errors


def _is_attachment_key(key: object) -> bool:
    return isinstance(key, str) and ATTACHMENT_KEY.fullmatch(key) is not None


def _contract_key_errors(artifacts: object, *, evidence: bool) -> list[str]:
    if not isinstance(artifacts, dict):
        return ["Contract-Artifact-Exact-Set verletzt: artifacts kein Objekt"]
    actual = set(artifacts)
    expected = EVIDENCE_ARTIFACT_KEYS if evidence else AUDIT_ARTIFACT_KEYS
    if evidence:
        actual_static = actual & EVIDENCE_ARTIFACT_KEYS
        unknown = {key for key in actual - EVIDENCE_ARTIFACT_KEYS if not _is_attachment_key(key)}
        missing = expected - actual_static
        extra = unknown
    else:
        missing = expected - actual
        extra = actual - expected
    if not missing and not extra:
        return []
    label = "Evidence" if evidence else "Audit"
    return [
        f"{label}-Artifact-Exact-Set verletzt: "
        f"fehlend={sorted(missing)!r}, extra={sorted(extra, key=str)!r}"
    ]


def validate_audit_contract(
    contract: dict[str, Any], expected_contract_sha256: str, *, plan_id: str,
    run_id: str, audited_commit: str, tooling_commit: str, snapshot_id: str,
) -> list[str]:
    if not isinstance(contract, dict):
        return ["audit_contract: Objekt erwartet"]
    errors: list[str] = []
    expected_fields = {
        "schema_version", "plan_id", "run_id", "audited_commit", "tooling_commit",
        "snapshot_id", "frozen_at", "expires_at", "artifacts", "contract_sha256",
    }
    if set(contract) != expected_fields:
        errors.append("audit_contract: Felder nicht exakt")
    actual = _sha(_canonical(_without(contract, "contract_sha256")))
    if contract.get("contract_sha256") != actual:
        errors.append("audit_contract: self contract_sha256 falsch")
    if expected_contract_sha256 != actual:
        errors.append("audit_contract: externe Contract-SHA weicht ab")
    for field, value in (
        ("schema_version", 1), ("plan_id", plan_id), ("run_id", run_id),
        ("audited_commit", audited_commit), ("tooling_commit", tooling_commit),
        ("snapshot_id", snapshot_id),
    ):
        if contract.get(field) != value:
            errors.append(f"audit_contract: {field} falsch")
    frozen = _timestamp(contract.get("frozen_at"))
    expires = _timestamp(contract.get("expires_at"))
    now = datetime.now(timezone.utc)
    if frozen is None or expires is None or frozen >= expires:
        errors.append("audit_contract: frozen_at/expires_at ungueltig")
    elif frozen > now:
        errors.append("audit_contract: frozen_at liegt in Zukunft")
    elif now > expires:
        errors.append("audit_contract: TTL abgelaufen")
    errors.extend(_contract_key_errors(contract.get("artifacts"), evidence=False))
    errors.extend(_validate_artifact_entries(contract.get("artifacts"), "audit_contract"))
    return errors


def validate_evidence_contract(
    contract: dict[str, Any], expected_sha256: str, audit_contract: dict[str, Any], *,
    plan_id: str, run_id: str, audited_commit: str, tooling_commit: str,
    snapshot_id: str,
) -> list[str]:
    if not isinstance(contract, dict):
        return ["evidence_contract: Objekt erwartet"]
    errors: list[str] = []
    expected_fields = {
        "schema_version", "plan_id", "run_id", "audited_commit", "tooling_commit",
        "snapshot_id", "audit_contract_sha256", "completed_at", "artifacts",
        "evidence_contract_sha256",
    }
    if set(contract) != expected_fields:
        errors.append("evidence_contract: Felder nicht exakt")
    actual = _sha(_canonical(_without(contract, "evidence_contract_sha256")))
    if contract.get("evidence_contract_sha256") != actual:
        errors.append("evidence_contract: self evidence_contract_sha256 falsch")
    if expected_sha256 != actual:
        errors.append("evidence_contract: externe Contract-SHA weicht ab")
    for field, value in (
        ("schema_version", 1), ("plan_id", plan_id), ("run_id", run_id),
        ("audited_commit", audited_commit), ("tooling_commit", tooling_commit),
        ("snapshot_id", snapshot_id),
        ("audit_contract_sha256", audit_contract.get("contract_sha256")),
    ):
        if contract.get(field) != value:
            errors.append(f"evidence_contract: {field} falsch")
    completed = _timestamp(contract.get("completed_at"))
    frozen = _timestamp(audit_contract.get("frozen_at"))
    expires = _timestamp(audit_contract.get("expires_at"))
    now = datetime.now(timezone.utc)
    if completed is None or frozen is None or expires is None or not (frozen <= completed <= expires and completed <= now):
        errors.append("evidence_contract: completed_at ausser Zeitgrenze")
    errors.extend(_contract_key_errors(contract.get("artifacts"), evidence=True))
    errors.extend(_validate_artifact_entries(contract.get("artifacts"), "evidence_contract"))
    return errors


def _artifact_binding_errors(
    records: list[dict[str, Any]], contract: dict[str, Any], key: str, label: str,
) -> list[str]:
    artifacts = contract.get("artifacts")
    expected = artifacts.get(key) if isinstance(artifacts, dict) else None
    if expected != artifact_contract_entry(records, str(expected.get("ref", "")) if isinstance(expected, dict) else ""):
        return [f"{label}: Contract-Artefaktbindung falsch"]
    return []


def _record_time_errors(
    records: list[dict[str, Any]], audit_contract: dict[str, Any], label: str,
    completed_at: object | None = None,
) -> list[str]:
    frozen = _timestamp(audit_contract.get("frozen_at"))
    expires = _timestamp(audit_contract.get("expires_at"))
    now = datetime.now(timezone.utc)
    completed = _timestamp(completed_at) if completed_at is not None else None
    errors: list[str] = []
    for number, row in enumerate(records, 1):
        signed = _timestamp(row.get("signed_at"))
        if (
            signed is None or frozen is None or expires is None
            or not (frozen <= signed <= expires and signed <= now)
            or (completed_at is not None and (completed is None or signed > completed))
        ):
            errors.append(f"{label} Zeile {number}: signed_at ausser Zeitgrenze")
    return errors


def validate_artifact(
    records: list[dict[str, Any]], manifest: dict[str, Any], kind: str,
    id_field: str, *, run_id: str, audited_commit: str, tooling_commit: str,
    snapshot_id: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    expected = make_artifact_manifest(
        kind, records, run_id=run_id, audited_commit=audited_commit,
        tooling_commit=tooling_commit, snapshot_id=snapshot_id,
    )
    if manifest != expected:
        errors.append(f"{kind}: Artefaktmanifest/Hashbindung falsch")
    indexed: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(records, 1):
        item_id = row.get(id_field)
        label = f"{kind} Zeile {number}"
        if not isinstance(item_id, str) or not item_id or item_id in indexed:
            errors.append(f"{label}: {id_field} fehlt/doppelt")
        else:
            indexed[item_id] = row
        if row.get("record_sha256") != _sha(_canonical(_without(row, "record_sha256"))):
            errors.append(f"{label}: record_sha256 falsch")
        if kind == "feature-catalog":
            expected_id = "sha256:" + _sha(
                _canonical(_without(row, "catalog_id", "record_sha256"))
            )
            if item_id != expected_id:
                errors.append(f"{label}: catalog_id nicht inhaltsadressiert")
        if kind == "feature-state-evidence":
            expected_id = "sha256:" + _sha(
                _canonical(_without(row, "evidence_id", "proof_sha256", "record_sha256"))
            )
            if item_id != expected_id:
                errors.append(f"{label}: evidence_id nicht inhaltsadressiert")
        for field, value in (
            ("run_id", run_id), ("audited_commit", audited_commit),
            ("tooling_commit", tooling_commit), ("snapshot_id", snapshot_id),
        ):
            if row.get(field) != value:
                errors.append(f"{label}: {field} falsch")
    if not records:
        errors.append(f"{kind}: Artefakt ist leer")
    return indexed, errors


def _aware_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def _validate_balanced(text: str, path: str, *, braces: bool = False) -> None:
    stack: list[str] = []
    pairs = {')': '(', ']': '[', '}': '{'}
    quote: str | None = None
    escaped = False
    comment = False
    for char in text:
        if comment:
            if char == "\n":
                comment = False
            continue
        if escaped:
            escaped = False
            continue
        if char in {"`", "\\"} and quote is not None:
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char == "#" and braces:
            comment = True
        elif char in {"'", '"'}:
            quote = char
        elif char in "([" + ("{" if braces else ""):
            stack.append(char)
        elif char in ")]" + ("}" if braces else ""):
            if not stack or stack.pop() != pairs[char]:
                raise ContractError(f"parser_error:{path}: unbalanciertes Token {char}")
    if quote or stack:
        raise ContractError(f"parser_error:{path}: unbalancierte Quotes/Klammern")


def _sql_statements(text: str, path: str) -> list[str]:
    _validate_balanced(text, path)
    statements: list[str] = []
    start = 0
    quote: str | None = None
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            if char == quote:
                if index + 1 < len(text) and text[index + 1] == quote:
                    index += 1
                else:
                    quote = None
        elif char in {"'", '"', "`"}:
            quote = char
        elif char == ";":
            if statement := text[start:index].strip():
                statements.append(statement)
            start = index + 1
        index += 1
    if statement := text[start:].strip():
        statements.append(statement)
    return statements


def _parse_sql(text: str, path: str) -> None:
    meaningful = re.sub(r"--[^\n]*(?:\n|$)|/\*.*?\*/", "", text, flags=re.DOTALL).strip()
    if not meaningful:
        raise ContractError(f"parser_error:{path}: leeres SQLite-Skript")
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(text)
    except sqlite3.Error as exc:
        raise ContractError(f"parser_error:{path}: sqlite: {exc}") from exc
    finally:
        connection.close()


def _parse_xml(text: str, path: str) -> ET.Element:
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise ContractError(f"parser_error:{path}: {exc}") from exc


def _parse_batch(text: str, path: str) -> None:
    _validate_balanced(text, path)
    labels: set[str] = set()
    for number, line in enumerate(text.splitlines(), 1):
        if match := re.match(r"\s*:([^:\s]+)", line):
            label = match.group(1).lower()
            if label in labels:
                raise ContractError(f"parser_error:{path}:{number}: doppeltes Label {label}")
            labels.add(label)
    for number, line in enumerate(text.splitlines(), 1):
        if match := re.match(r"\s*call\s+:([^\s]+)", line, re.IGNORECASE):
            if match.group(1).lower() not in labels:
                raise ContractError(
                    f"parser_error:{path}:{number}: unbekanntes Batch-Label {match.group(1)}"
                )


def _parse_powershell(text: str, path: str) -> None:
    executable = shutil.which("powershell") or shutil.which("pwsh")
    if executable is None:
        raise ContractError(f"parser_error:{path}: PowerShell-AST-Parser fehlt")
    parser_script = (
        "$tokens=$null;$errors=$null;"
        "[void][System.Management.Automation.Language.Parser]::ParseInput("
        "[Console]::In.ReadToEnd(),[ref]$tokens,[ref]$errors);"
        "if($errors.Count){$errors|ForEach-Object{$_.Message}|Write-Error;exit 2}"
    )
    try:
        result = subprocess.run(
            [executable, "-NoProfile", "-NonInteractive", "-Command", parser_script],
            input=text, text=True, encoding="utf-8", capture_output=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ContractError(f"parser_error:{path}: PowerShell-Parser nicht verfuegbar: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().replace("\n", " | ")[-500:]
        raise ContractError(f"parser_error:{path}: {detail or 'PowerShell-Syntaxfehler'}")


def _parse_config(text: str, suffix: str, path: str) -> None:
    try:
        if suffix == ".json":
            json.loads(text)
        elif suffix == ".toml":
            tomllib.loads(text)
        elif suffix in {".ini", ".cfg"}:
            parser = configparser.ConfigParser()
            parser.read_string(text)
        elif suffix in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore[import-untyped]
            except ImportError as exc:
                raise ContractError(f"parser_error:{path}: YAML-Parser fehlt") from exc
            yaml.safe_load(text)
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(f"parser_error:{path}: {exc}") from exc


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True,
    ).stdout


def resolve_commit(root: Path, commit: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise ContractError("audited_commit muss volle 40-Zeichen-SHA sein")
    try:
        resolved = _git(root, "rev-parse", "--verify", f"{commit}^{{commit}}").decode().strip()
    except subprocess.CalledProcessError as exc:
        raise ContractError("audited_commit existiert nicht als Gitcommit") from exc
    if resolved.lower() != commit.lower():
        raise ContractError("audited_commit ist nicht kanonisch")
    return resolved


def _tracked_paths(root: Path, commit: str) -> list[str]:
    raw = _git(root, "ls-tree", "-r", "--name-only", "-z", commit)
    paths = [part.decode("utf-8", "surrogateescape") for part in raw.split(b"\0") if part]
    return sorted(paths)


def _blob(root: Path, commit: str, path: str) -> bytes:
    return _git(root, "show", f"{commit}:{path}")


def _call_name(node: ast.Call) -> str:
    fn = node.func
    if isinstance(fn, ast.Name):
        return fn.id
    if isinstance(fn, ast.Attribute):
        return fn.attr
    return ""


def _string_arg(node: ast.Call) -> str | None:
    for arg in node.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.strip():
            return " ".join(arg.value.split())
    return None


def _locator_id(prefix: str, kind: str, path: str, line: int, column: int, detail: str) -> str:
    basis = f"{kind}\0{path}\0{line}\0{column}\0{detail}".encode("utf-8")
    return f"{prefix}-{_sha(basis)[:24]}"


def _bound_row(
    *, source_id: str, source_kind: str, path: str, line: int, column: int,
    detail: str, blob_sha: str, run_id: str, audited_commit: str, snapshot_id: str,
    tooling_commit: str, signed_at: str,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "source_kind": source_kind,
        "path": path,
        "line": line,
        "column": column,
        "detail": detail,
        "source_blob_sha256": blob_sha,
        "run_id": run_id,
        "audited_commit": audited_commit,
        "tooling_commit": tooling_commit,
        "snapshot_id": snapshot_id,
        "signed_at": signed_at,
    }


def enumerate_universes(
    root: Path, audited_commit: str, run_id: str, snapshot_id: str, *,
    tooling_commit: str, signed_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read Git blobs, never working-tree content."""
    root = root.resolve()
    commit = resolve_commit(root, audited_commit)
    requirements: list[dict[str, Any]] = []
    triggers: list[dict[str, Any]] = []

    def append_row(
        target: list[dict[str, Any]], prefix: str, kind: str, path: str,
        line: int, column: int, detail: str, blob_sha: str,
    ) -> None:
        target.append(_bound_row(
            source_id=_locator_id(prefix, kind, path, line, column, detail),
            source_kind=kind, path=path, line=line, column=column, detail=detail,
            blob_sha=blob_sha, run_id=run_id, audited_commit=commit,
            snapshot_id=snapshot_id, tooling_commit=tooling_commit,
            signed_at=signed_at,
        ))

    for path in _tracked_paths(root, commit):
        suffix = PurePosixPath(path).suffix.lower()
        if suffix not in RELEVANT_SUFFIXES:
            continue
        data = _blob(root, commit, path)
        blob_sha = _sha(data)
        try:
            if suffix == ".py":
                encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
                text = data.decode(encoding)
            else:
                text = data.decode("utf-8")
        except (LookupError, SyntaxError, UnicodeDecodeError) as exc:
            raise ContractError(f"Encoding-/Decodefehler in {path}: {exc}") from exc

        append_row(
            requirements, "REQ", "source-coverage-unit", path, 1, 0,
            f"tracked-source:{suffix}:{blob_sha}", blob_sha,
        )

        if suffix in TEXT_SUFFIXES | CONFIG_SUFFIXES:
            if suffix in CONFIG_SUFFIXES:
                _parse_config(text, suffix, path)
                append_row(
                    requirements, "REQ", "structured-config-unit", path, 1, 0,
                    f"config:{suffix}:{blob_sha}", blob_sha,
                )
            for number, line in enumerate(text.splitlines(), 1):
                normalized = " ".join(line.strip().split())
                if normalized and NORMATIVE.search(normalized):
                    source_kind = "normative-text"
                    source_id = _locator_id("REQ", source_kind, path, number, 0, normalized)
                    requirements.append(_bound_row(
                        source_id=source_id, source_kind=source_kind, path=path,
                        line=number, column=0, detail=normalized, blob_sha=blob_sha,
                        run_id=run_id, audited_commit=commit, snapshot_id=snapshot_id,
                        tooling_commit=tooling_commit, signed_at=signed_at,
                    ))
            if suffix != ".py":
                continue

        if suffix in {".ps1", ".psm1"}:
            _parse_powershell(text, path)
            append_row(
                triggers, "TRIG", "powershell-entrypoint", path, 1, 0,
                f"script:{path}", blob_sha,
            )
            for number, line in enumerate(text.splitlines(), 1):
                match = re.match(r"\s*(?:function|filter)\s+([\w:-]+)", line, re.IGNORECASE)
                if match:
                    append_row(
                        triggers, "TRIG", "powershell-function", path, number, 0,
                        match.group(1), blob_sha,
                    )
                for parameter in re.findall(r"\[\w+(?:\([^)]*\))?\]\s*\$([\w]+)", line):
                    append_row(
                        triggers, "TRIG", "powershell-parameter", path, number, 0,
                        parameter, blob_sha,
                    )
            continue

        if suffix in {".bat", ".cmd"}:
            _parse_batch(text, path)
            append_row(
                triggers, "TRIG", "batch-entrypoint", path, 1, 0,
                f"script:{path}", blob_sha,
            )
            for number, line in enumerate(text.splitlines(), 1):
                match = re.match(r"\s*:([^:\s]+)", line)
                if match:
                    append_row(
                        triggers, "TRIG", "batch-label", path, number, 0,
                        match.group(1), blob_sha,
                    )
            continue

        if suffix == ".sql":
            _parse_sql(text, path)
            found = False
            for match in re.finditer(r"\bCREATE\s+TRIGGER\s+([\w.\[\]`\"]+)", text, re.IGNORECASE):
                found = True
                line = text.count("\n", 0, match.start()) + 1
                append_row(
                    triggers, "TRIG", "sql-trigger", path, line, 0,
                    match.group(1), blob_sha,
                )
            if not found:
                append_row(
                    requirements, "REQ", "sql-schema-unit", path, 1, 0,
                    f"schema:{SUPPORTED_SQL_DIALECT}:{blob_sha}", blob_sha,
                )
            continue

        if suffix in {".ui", ".ts"}:
            xml_root = _parse_xml(text, path)
            if suffix == ".ui":
                for index, connection in enumerate(xml_root.findall(".//connection"), 1):
                    detail = ":".join(
                        (connection.findtext(name) or "").strip()
                        for name in ("sender", "signal", "receiver", "slot")
                    )
                    append_row(
                        triggers, "TRIG", "qt-ui-signal", path, 1, index,
                        f"{index}:{detail}", blob_sha,
                    )
                for index, widget in enumerate(xml_root.findall(".//widget"), 1):
                    widget_class = widget.get("class", "")
                    widget_name = widget.get("name", "")
                    if widget_class in {"QPushButton", "QToolButton", "QCheckBox", "QRadioButton", "QComboBox"}:
                        append_row(
                            triggers, "TRIG", "qt-ui-widget", path, 1, index,
                            f"{index}:{widget_class}:{widget_name}", blob_sha,
                        )
                    for string_index, string in enumerate(widget.findall(".//string"), 1):
                        if (string.text or "").strip():
                            append_row(
                                requirements, "REQ", "qt-ui-contract", path, 1, index,
                                f"{index}:{string_index}:{' '.join(string.text.split())}", blob_sha,
                            )
            else:
                for index, message in enumerate(xml_root.findall(".//message"), 1):
                    source = " ".join((message.findtext("source") or "").split())
                    translation = " ".join((message.findtext("translation") or "").split())
                    append_row(
                        requirements, "REQ", "translation-contract", path, 1, index,
                        f"{index}:{source}:{translation}", blob_sha,
                    )
            continue

        try:
            tree = ast.parse(text, filename=path)
        except SyntaxError as exc:
            raise ContractError(f"Python-Parserfehler in {path}:{exc.lineno}: {exc.msg}") from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _call_name(node)
                label = _string_arg(node)
                if name in UI_TEXT_CALLS and label:
                    kind = "ui-contract"
                    source_id = _locator_id("REQ", kind, path, node.lineno, node.col_offset, f"{name}:{label}")
                    requirements.append(_bound_row(
                        source_id=source_id, source_kind=kind, path=path,
                        line=node.lineno, column=node.col_offset, detail=f"{name}:{label}",
                        blob_sha=blob_sha, run_id=run_id, audited_commit=commit,
                        snapshot_id=snapshot_id, tooling_commit=tooling_commit,
                        signed_at=signed_at,
                    ))
                if name in INTERACTIVE_UI_CALLS:
                    kind = "qt-ui-surface"
                    detail = f"{name}:{label or ast.dump(node.func, include_attributes=False)}"
                    append_row(
                        triggers, "TRIG", kind, path, node.lineno, node.col_offset,
                        detail, blob_sha,
                    )
                if name in CONFIG_ACCESS_CALLS:
                    detail = f"{name}:{label or ast.dump(node, include_attributes=False)}"
                    append_row(
                        requirements, "REQ", "config-access", path, node.lineno,
                        node.col_offset, detail, blob_sha,
                    )
                if name in TRIGGER_CALLS:
                    kind = TRIGGER_CALLS[name]
                    detail = f"{name}:{label or ast.dump(node.func, include_attributes=False)}"
                    source_id = _locator_id("TRIG", kind, path, node.lineno, node.col_offset, detail)
                    triggers.append(_bound_row(
                        source_id=source_id, source_kind=kind, path=path,
                        line=node.lineno, column=node.col_offset, detail=detail,
                        blob_sha=blob_sha, run_id=run_id, audited_commit=commit,
                        snapshot_id=snapshot_id, tooling_commit=tooling_commit,
                        signed_at=signed_at,
                    ))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in LIFECYCLE_NAMES:
                    kind = LIFECYCLE_NAMES[node.name]
                    source_id = _locator_id("TRIG", kind, path, node.lineno, node.col_offset, node.name)
                    triggers.append(_bound_row(
                        source_id=source_id, source_kind=kind, path=path,
                        line=node.lineno, column=node.col_offset, detail=node.name,
                        blob_sha=blob_sha, run_id=run_id, audited_commit=commit,
                        snapshot_id=snapshot_id, tooling_commit=tooling_commit,
                        signed_at=signed_at,
                    ))
                for decorator in node.decorator_list:
                    rendered = ast.unparse(decorator) if hasattr(ast, "unparse") else ast.dump(decorator)
                    if re.search(r"(route|hook|callback|receiver|slot|command)", rendered, re.IGNORECASE):
                        kind = "decorator-hook"
                        source_id = _locator_id("TRIG", kind, path, node.lineno, node.col_offset, rendered)
                        triggers.append(_bound_row(
                            source_id=source_id, source_kind=kind, path=path,
                            line=node.lineno, column=node.col_offset, detail=rendered,
                            blob_sha=blob_sha, run_id=run_id, audited_commit=commit,
                            snapshot_id=snapshot_id, tooling_commit=tooling_commit,
                            signed_at=signed_at,
                        ))
        if re.search(r"^\s*if\s+__name__\s*==\s*['\"]__main__['\"]\s*:", text, re.MULTILINE):
            for number, line in enumerate(text.splitlines(), 1):
                if re.search(r"^\s*if\s+__name__\s*==\s*['\"]__main__['\"]\s*:", line):
                    kind = "main-guard"
                    source_id = _locator_id("TRIG", kind, path, number, 0, "__main__")
                    triggers.append(_bound_row(
                        source_id=source_id, source_kind=kind, path=path, line=number,
                        column=0, detail="__main__", blob_sha=blob_sha, run_id=run_id,
                        audited_commit=commit, snapshot_id=snapshot_id,
                        tooling_commit=tooling_commit, signed_at=signed_at,
                    ))
                    break
    return (
        sorted(requirements, key=lambda row: row["source_id"]),
        sorted(triggers, key=lambda row: row["source_id"]),
    )


def universe_digest(rows: Iterable[dict[str, Any]]) -> str:
    return _sha(b"\n".join(_canonical(row) for row in sorted(rows, key=lambda item: item["source_id"])))


def validate_exact_set(
    expected_requirements: list[dict[str, Any]], expected_triggers: list[dict[str, Any]],
    dispositions: list[dict[str, Any]], *, run_id: str, audited_commit: str,
    snapshot_id: str, tooling_commit: str,
    feature_catalog: list[dict[str, Any]], feature_catalog_manifest: dict[str, Any],
    evidence_records: list[dict[str, Any]], evidence_manifest: dict[str, Any],
    reviewer_records: list[dict[str, Any]], reviewer_manifest: dict[str, Any],
    audit_contract: dict[str, Any], expected_contract_sha256: str,
    evidence_contract: dict[str, Any], expected_evidence_contract_sha256: str,
    evidence_root: Path,
) -> list[str]:
    if not isinstance(audit_contract, dict) or not isinstance(evidence_contract, dict):
        return ["Audit-/Evidence-Contract muss Objekt sein"]
    errors: list[str] = []
    errors.extend(validate_audit_contract(
        audit_contract, expected_contract_sha256, plan_id=PLAN_ID, run_id=run_id,
        audited_commit=audited_commit, tooling_commit=tooling_commit,
        snapshot_id=snapshot_id,
    ))
    errors.extend(validate_evidence_contract(
        evidence_contract, expected_evidence_contract_sha256, audit_contract,
        plan_id=PLAN_ID, run_id=run_id, audited_commit=audited_commit,
        tooling_commit=tooling_commit, snapshot_id=snapshot_id,
    ))
    for records, contract, key, label, is_output in (
        (expected_requirements, audit_contract, "requirements-universe", "Requirements", False),
        (expected_triggers, audit_contract, "trigger-universe", "Trigger", False),
        (feature_catalog, audit_contract, "feature-catalog", "Featurekatalog", False),
        (dispositions, evidence_contract, "feature-state", "Feature-State", True),
        (evidence_records, evidence_contract, "feature-state-evidence", "Feature-Evidence", True),
        (reviewer_records, evidence_contract, "reviewer-roster", "Reviewer-Roster", True),
    ):
        errors.extend(_artifact_binding_errors(records, contract, key, label))
        errors.extend(_record_time_errors(
            records, audit_contract, label,
            evidence_contract.get("completed_at") if is_output else None,
        ))
    universes = {"requirement": expected_requirements, "trigger": expected_triggers}
    expected: dict[tuple[str, str], dict[str, Any]] = {}
    digests = {kind: universe_digest(rows) for kind, rows in universes.items()}
    features_by_id, feature_errors = validate_artifact(
        feature_catalog, feature_catalog_manifest, "feature-catalog", "catalog_id",
        run_id=run_id, audited_commit=audited_commit, tooling_commit=tooling_commit,
        snapshot_id=snapshot_id,
    )
    evidence_by_id, evidence_errors = validate_artifact(
        evidence_records, evidence_manifest, "feature-state-evidence", "evidence_id",
        run_id=run_id, audited_commit=audited_commit, tooling_commit=tooling_commit,
        snapshot_id=snapshot_id,
    )
    reviewers_by_id, reviewer_errors = validate_artifact(
        reviewer_records, reviewer_manifest, "reviewer-roster", "reviewer_id",
        run_id=run_id, audited_commit=audited_commit, tooling_commit=tooling_commit,
        snapshot_id=snapshot_id,
    )
    errors.extend(feature_errors + evidence_errors + reviewer_errors)
    expected_feature_proofs = {
        f"feature-proof:{row.get('evidence_id', '')}" for row in evidence_records
    }
    actual_feature_proofs = {
        key for key in evidence_contract.get("artifacts", {})
        if isinstance(key, str) and key.startswith("feature-proof:")
    }
    if actual_feature_proofs != expected_feature_proofs:
        errors.append(
            "Feature-Proof-Key-Exact-Set verletzt: "
            f"fehlend={sorted(expected_feature_proofs - actual_feature_proofs)!r}, "
            f"extra={sorted(actual_feature_proofs - expected_feature_proofs)!r}"
        )
    for number, row in enumerate(evidence_records, 1):
        allowed = {
            "evidence_id", "evidence_kind", "source_id", "feature_id", "path_id",
            "reviewer_id", "path", "source_blob_sha256", "signed_at", "proof_ref",
            "proof_sha256",
            "run_id", "audited_commit", "tooling_commit", "snapshot_id",
            "record_sha256",
        }
        if set(row) != allowed:
            errors.append(f"Feature-Evidence Zeile {number}: Schemafelder nicht exakt")
        for field in (
            "evidence_kind", "source_id", "feature_id", "path_id", "reviewer_id",
            "path", "source_blob_sha256", "signed_at",
        ):
            if not row.get(field):
                errors.append(f"Feature-Evidence Zeile {number}: {field} fehlt")
        proof_ref = row.get("proof_ref")
        if not _safe_ref(proof_ref):
            errors.append(f"Feature-Evidence Zeile {number}: proof_ref ungueltig")
        if not re.fullmatch(r"[0-9a-f]{64}", str(row.get("proof_sha256", ""))):
            errors.append(f"Feature-Evidence Zeile {number}: proof_sha256 ungueltig")
        if row.get("evidence_kind") != "source-review":
            errors.append(f"Feature-Evidence Zeile {number}: evidence_kind ungueltig")
        proof_expected = {field: row.get(field) for field in (
            "evidence_id", "evidence_kind", "source_id", "feature_id", "path_id",
            "reviewer_id", "path", "source_blob_sha256",
        )}
        proof_expected["schema_version"] = 1
        errors.extend(_proof_errors(
            row, evidence_contract, evidence_root, prefix="feature-proof",
            expected=proof_expected, label=f"Feature-Evidence Zeile {number}",
        ))
        if not re.fullmatch(r"[0-9a-f]{64}", str(row.get("source_blob_sha256", ""))):
            errors.append(f"Feature-Evidence Zeile {number}: source_blob_sha256 ungueltig")
    feature_pairs: dict[tuple[str, str], dict[str, Any]] = {}
    catalog_source_owners: dict[str, tuple[str, str]] = {}
    canonical_source_ids = {
        str(row.get("source_id", "")) for rows in universes.values() for row in rows
    }
    for row in features_by_id.values():
        catalog_fields = {
            "catalog_id", "feature_id", "path_id", "name", "source_ids",
            "run_id", "audited_commit", "tooling_commit", "snapshot_id",
            "signed_at", "record_sha256",
        }
        if set(row) != catalog_fields:
            errors.append("Featurekatalog: Schemafelder nicht exakt")
        pair = (str(row.get("feature_id", "")), str(row.get("path_id", "")))
        if not all(pair) or pair in feature_pairs:
            errors.append("Featurekatalog: Feature-/Pfad-ID fehlt/doppelt")
        feature_pairs[pair] = row
        source_ids = row.get("source_ids")
        if (
            not isinstance(source_ids, list) or not source_ids
            or any(not isinstance(source_id, str) or not source_id for source_id in source_ids)
            or len(source_ids) != len(set(source_ids))
        ):
            errors.append(f"Featurekatalog {pair!r}: source_ids fehlt/leer/doppelt")
            continue
        foreign = set(source_ids) - canonical_source_ids
        if foreign:
            errors.append(f"Featurekatalog {pair!r}: fremde source_ids {sorted(foreign)!r}")
        for source_id in source_ids:
            owner = catalog_source_owners.get(source_id)
            if owner is not None and owner != pair:
                errors.append(
                    f"Featurekatalog: source_id {source_id!r} ueberlappt {owner!r}/{pair!r}"
                )
            catalog_source_owners[source_id] = pair
    if not expected_requirements:
        errors.append("Requirements-Universum ist leer")
    if not expected_triggers:
        errors.append("Trigger-Universum ist leer")
    for kind, rows in universes.items():
        for row in rows:
            key = (kind, str(row.get("source_id", "")))
            if not key[1] or key in expected:
                errors.append(f"{kind}-Universum enthaelt fehlende/doppelte source_id")
            expected[key] = row
            if (
                row.get("run_id") != run_id
                or row.get("audited_commit") != audited_commit
                or row.get("tooling_commit") != tooling_commit
                or row.get("snapshot_id") != snapshot_id
            ):
                errors.append(f"{kind}/{key[1]}: Universumsbindung manipuliert")

    seen: set[tuple[str, str]] = set()
    disposition_sources: dict[tuple[str, str], set[str]] = {}
    evidence_consumers: dict[str, int] = {}
    for number, row in enumerate(dispositions, 1):
        state_fields = {
            "universe", "source_id", "run_id", "audited_commit", "tooling_commit",
            "snapshot_id", "universe_sha256", "disposition", "feature_id",
            "path_id", "evidence_id", "reviewer_id", "signed_at",
            "source_blob_sha256",
        }
        if set(row) != state_fields:
            errors.append(f"Disposition Zeile {number}: Schemafelder nicht exakt")
        kind = str(row.get("universe", ""))
        source_id = str(row.get("source_id", ""))
        key = (kind, source_id)
        if key in seen:
            errors.append(f"Disposition Zeile {number}: doppelte ID {key!r}")
        seen.add(key)
        if key not in expected:
            errors.append(f"Disposition Zeile {number}: fremde ID {key!r}")
        if (
            row.get("run_id") != run_id
            or row.get("audited_commit") != audited_commit
            or row.get("tooling_commit") != tooling_commit
            or row.get("snapshot_id") != snapshot_id
        ):
            errors.append(f"Disposition Zeile {number}: Run-/Commit-/Snapshotbindung falsch")
        if row.get("universe_sha256") != digests.get(kind):
            errors.append(f"Disposition Zeile {number}: Universumshash falsch")
        if not _enum_value(row.get("disposition"), DISPOSITIONS):
            errors.append(f"Disposition Zeile {number}: disposition ungueltig")
        for field in ("feature_id", "path_id", "evidence_id", "reviewer_id", "signed_at", "source_blob_sha256"):
            if not row.get(field):
                errors.append(f"Disposition Zeile {number}: {field} fehlt")
        pair = (str(row.get("feature_id", "")), str(row.get("path_id", "")))
        disposition_sources.setdefault(pair, set()).add(source_id)
        catalog = feature_pairs.get(pair)
        if catalog is None:
            errors.append(f"Disposition Zeile {number}: Featurekatalog-FK fehlt")
        elif source_id not in (catalog.get("source_ids") or []):
            errors.append(f"Disposition Zeile {number}: Source fehlt im Featurekatalog")
        source = expected.get(key)
        if source is not None and row.get("source_blob_sha256") != source.get("source_blob_sha256"):
            errors.append(f"Disposition Zeile {number}: Source-Blob falsch")
        evidence = evidence_by_id.get(str(row.get("evidence_id", "")))
        evidence_id = str(row.get("evidence_id", ""))
        if evidence_id:
            evidence_consumers[evidence_id] = evidence_consumers.get(evidence_id, 0) + 1
        reviewer = reviewers_by_id.get(str(row.get("reviewer_id", "")))
        if reviewer is None:
            errors.append(f"Disposition Zeile {number}: Reviewer-FK fehlt")
        if evidence is None:
            errors.append(f"Disposition Zeile {number}: Evidence-FK fehlt")
        else:
            for field, value in (
                ("source_id", source_id), ("feature_id", pair[0]), ("path_id", pair[1]),
                ("reviewer_id", row.get("reviewer_id")),
                ("path", source.get("path") if source is not None else None),
                ("source_blob_sha256", row.get("source_blob_sha256")),
                ("signed_at", row.get("signed_at")),
            ):
                if evidence.get(field) != value:
                    errors.append(f"Disposition Zeile {number}: Evidence-{field} falsch")
        if not _aware_timestamp(row.get("signed_at")):
            errors.append(f"Disposition Zeile {number}: signed_at ungueltig")
    if set(expected) != seen:
        errors.append(
            "Requirements-/Trigger-Exact-Set verletzt: "
            f"fehlend={sorted(set(expected) - seen)!r}, extra={sorted(seen - set(expected))!r}"
        )
    for pair, catalog in feature_pairs.items():
        raw_claims = catalog.get("source_ids")
        claimed = (
            set(raw_claims) if isinstance(raw_claims, list)
            and all(isinstance(value, str) for value in raw_claims) else set()
        )
        consumed = disposition_sources.get(pair, set())
        if claimed != consumed:
            errors.append(
                f"Featurekatalog {pair!r}: Source-Exact-Set verletzt: "
                f"unused={sorted(claimed - consumed)!r}, "
                f"unclaimed={sorted(consumed - claimed)!r}"
            )
    evidence_closure = {
        evidence_id: evidence_consumers.get(evidence_id, 0)
        for evidence_id in evidence_by_id
        if evidence_consumers.get(evidence_id, 0) != 1
    }
    foreign_consumers = set(evidence_consumers) - set(evidence_by_id)
    if evidence_closure or foreign_consumers:
        errors.append(
            "Feature-Evidence-Consumer-Closure verletzt: "
            f"counts={evidence_closure!r}, foreign={sorted(foreign_consumers)!r}"
        )
    return errors


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ContractError(f"{path}: Zeile {number}: Objekt erwartet")
        rows.append(value)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"".join(_canonical(row) + b"\n" for row in rows))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    enum = sub.add_parser("enumerate")
    enum.add_argument("--root", type=Path, required=True)
    enum.add_argument("--audited-commit", required=True)
    enum.add_argument("--run-id", required=True)
    enum.add_argument("--snapshot-id", required=True)
    enum.add_argument("--signed-at", required=True)
    enum.add_argument("--tooling-commit", required=True)
    enum.add_argument("--requirements-out", type=Path, required=True)
    enum.add_argument("--triggers-out", type=Path, required=True)
    verify = sub.add_parser("validate")
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--audited-commit", required=True)
    verify.add_argument("--run-id", required=True)
    verify.add_argument("--snapshot-id", required=True)
    verify.add_argument("--requirements", type=Path, required=True)
    verify.add_argument("--triggers", type=Path, required=True)
    verify.add_argument("--dispositions", type=Path, required=True)
    verify.add_argument("--tooling-commit", required=True)
    verify.add_argument("--feature-catalog", type=Path, required=True)
    verify.add_argument("--feature-catalog-manifest", type=Path, required=True)
    verify.add_argument("--evidence-records", type=Path, required=True)
    verify.add_argument("--evidence-manifest", type=Path, required=True)
    verify.add_argument("--reviewer-records", type=Path, required=True)
    verify.add_argument("--reviewer-manifest", type=Path, required=True)
    verify.add_argument("--audit-contract", type=Path, required=True)
    verify.add_argument("--expected-audit-contract-sha256", required=True)
    verify.add_argument("--evidence-contract", type=Path, required=True)
    verify.add_argument("--expected-evidence-contract-sha256", required=True)
    verify.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        signed_at = args.signed_at if args.command == "enumerate" else json.loads(
            args.audit_contract.read_text(encoding="utf-8")
        ).get("frozen_at")
        if not isinstance(signed_at, str):
            raise ContractError("audit_contract.frozen_at fehlt")
        requirements, triggers = enumerate_universes(
            args.root, args.audited_commit, args.run_id, args.snapshot_id,
            tooling_commit=args.tooling_commit, signed_at=signed_at,
        )
        if args.command == "enumerate":
            _write_jsonl(args.requirements_out, requirements)
            _write_jsonl(args.triggers_out, triggers)
            print(json.dumps({
                "ok": True, "requirements": len(requirements), "triggers": len(triggers),
                "requirements_sha256": universe_digest(requirements),
                "triggers_sha256": universe_digest(triggers),
            }, sort_keys=True))
            return 0
        supplied_requirements = _read_jsonl(args.requirements)
        supplied_triggers = _read_jsonl(args.triggers)
        errors: list[str] = []
        if supplied_requirements != requirements:
            errors.append("Requirements-Universum weicht von kanonischer Gitobjekt-Enumeration ab")
        if supplied_triggers != triggers:
            errors.append("Trigger-Universum weicht von kanonischer Gitobjekt-Enumeration ab")
        audit_contract = json.loads(args.audit_contract.read_text(encoding="utf-8"))
        evidence_contract = json.loads(args.evidence_contract.read_text(encoding="utf-8"))
        errors.extend(validate_exact_set(
            requirements, triggers, _read_jsonl(args.dispositions), run_id=args.run_id,
            audited_commit=resolve_commit(args.root.resolve(), args.audited_commit),
            snapshot_id=args.snapshot_id, tooling_commit=args.tooling_commit,
            feature_catalog=_read_jsonl(args.feature_catalog),
            feature_catalog_manifest=json.loads(args.feature_catalog_manifest.read_text(encoding="utf-8")),
            evidence_records=_read_jsonl(args.evidence_records),
            evidence_manifest=json.loads(args.evidence_manifest.read_text(encoding="utf-8")),
            reviewer_records=_read_jsonl(args.reviewer_records),
            reviewer_manifest=json.loads(args.reviewer_manifest.read_text(encoding="utf-8")),
            audit_contract=audit_contract,
            expected_contract_sha256=args.expected_audit_contract_sha256,
            evidence_contract=evidence_contract,
            expected_evidence_contract_sha256=args.expected_evidence_contract_sha256,
            evidence_root=args.evidence_root,
        ))
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        return 0 if not errors else 2
    except (ContractError, OSError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
