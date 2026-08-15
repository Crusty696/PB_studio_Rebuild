#!/usr/bin/env python3
"""Enumerate and validate Python symbol/edge/state contracts at a Git commit."""
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


CONTRACT_KEYS = ("inputs", "outputs", "side_effects", "errors", "config", "persistence")
EDGE_DISPOSITIONS = {"resolved", "dynamic", "framework", "unreferenced", "unknown"}
SYMBOL_DISPOSITIONS = {"runtime", "non-runtime", "unknown"}
PLAN_ID = "PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15"
SUPPORTED_SQL_DIALECT = "sqlite"


class ContractError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
    manifest = {
        "schema_version": 1, "kind": kind, "run_id": run_id,
        "audited_commit": audited_commit, "tooling_commit": tooling_commit,
        "snapshot_id": snapshot_id, "record_count": len(records),
        "records_sha256": _sha(b"".join(_canonical(row) + b"\n" for row in records)),
    }
    manifest["artifact_id"] = "sha256:" + manifest["records_sha256"]
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
    return path != PurePosixPath(".") and not path.is_absolute() and ".." not in path.parts


def _proof_errors(
    row: dict[str, Any], contract: dict[str, Any], evidence_root: Path,
    *, prefix: str, expected: dict[str, Any], label: str,
) -> list[str]:
    errors: list[str] = []
    ref = row.get("proof_ref")
    key = f"{prefix}:{row.get('evidence_id', '')}"
    descriptor = contract.get("artifacts", {}).get(key)
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
        if set(entry) != {"artifact_id", "ref", "sha256", "bytes", "record_count"}:
            errors.append(f"{row_label}: Artifactfelder nicht exakt")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(f"{row_label}: sha256 ungueltig")
        if entry.get("artifact_id") != f"sha256:{digest}":
            errors.append(f"{row_label}: artifact_id ungueltig")
        if not _safe_ref(entry.get("ref")):
            errors.append(f"{row_label}: ref nicht sicher/relativ")
        if not isinstance(entry.get("bytes"), int) or entry.get("bytes", -1) < 0:
            errors.append(f"{row_label}: bytes ungueltig")
        if not isinstance(entry.get("record_count"), int) or entry.get("record_count", -1) < 0:
            errors.append(f"{row_label}: record_count ungueltig")
    return errors


def validate_audit_contract(
    contract: dict[str, Any], expected_contract_sha256: str, *, plan_id: str,
    run_id: str, audited_commit: str, tooling_commit: str, snapshot_id: str,
) -> list[str]:
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
    errors.extend(_validate_artifact_entries(contract.get("artifacts"), "audit_contract"))
    return errors


def validate_evidence_contract(
    contract: dict[str, Any], expected_sha256: str, audit_contract: dict[str, Any], *,
    plan_id: str, run_id: str, audited_commit: str, tooling_commit: str,
    snapshot_id: str,
) -> list[str]:
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
    errors.extend(_validate_artifact_entries(contract.get("artifacts"), "evidence_contract"))
    return errors


def _artifact_binding_errors(
    records: list[dict[str, Any]], contract: dict[str, Any], key: str, label: str,
) -> list[str]:
    artifacts = contract.get("artifacts")
    expected = artifacts.get(key) if isinstance(artifacts, dict) else None
    actual = artifact_contract_entry(
        records, str(expected.get("ref", "")) if isinstance(expected, dict) else ""
    )
    return [] if expected == actual else [f"{label}: Contract-Artefaktbindung falsch"]


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


def validate_artifact_universe(
    rows: list[dict[str, Any]], manifest: dict[str, Any], kind: str,
    id_field: str, *, run_id: str, audited_commit: str, tooling_commit: str,
    snapshot_id: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    expected = make_artifact_manifest(
        kind, rows, run_id=run_id, audited_commit=audited_commit,
        tooling_commit=tooling_commit, snapshot_id=snapshot_id,
    )
    if manifest != expected:
        errors.append(f"{kind}: Artefaktmanifest/Hashbindung falsch")
    indexed: dict[str, dict[str, Any]] = {}
    for number, row in enumerate(rows, 1):
        item_id = row.get(id_field)
        label = f"{kind} Zeile {number}"
        if not isinstance(item_id, str) or not item_id or item_id in indexed:
            errors.append(f"{label}: {id_field} fehlt/doppelt")
        else:
            indexed[item_id] = row
        if row.get("record_sha256") != _sha(_canonical(_without(row, "record_sha256"))):
            errors.append(f"{label}: record_sha256 falsch")
        for field, value in (
            ("run_id", run_id), ("audited_commit", audited_commit),
            ("tooling_commit", tooling_commit), ("snapshot_id", snapshot_id),
        ):
            if row.get(field) != value:
                errors.append(f"{label}: {field} falsch")
    if not rows:
        errors.append(f"{kind}: Artefakt ist leer")
    return indexed, errors


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True).stdout


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


def _id(prefix: str, *parts: object) -> str:
    return f"{prefix}-{_sha(chr(0).join(map(str, parts)).encode())[:24]}"


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ast.dump(node, include_attributes=False)


def _balanced(text: str, path: str, *, braces: bool = False) -> None:
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
        if quote:
            if char == "`":
                escaped = True
            elif char == quote:
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


def _matching_brace(text: str, opening: int, path: str) -> int:
    depth = 0
    quote: str | None = None
    escaped = False
    comment = False
    for index in range(opening, len(text)):
        char = text[index]
        if comment:
            if char == "\n":
                comment = False
            continue
        if escaped:
            escaped = False
            continue
        if quote:
            if char == "`":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char == "#":
            comment = True
        elif char in {"'", '"'}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    raise ContractError(f"parser_error:{path}: Function-Block nicht geschlossen")


def _parse_structured(text: str, suffix: str, path: str) -> None:
    try:
        if suffix == ".json":
            json.loads(text)
        elif suffix == ".toml":
            tomllib.loads(text)
        elif suffix in {".ini", ".cfg"}:
            parser = configparser.ConfigParser()
            parser.read_string(text)
        elif suffix in {".ui", ".ts"}:
            ET.fromstring(text)
        elif suffix in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore[import-untyped]
            except ImportError as exc:
                raise ContractError(f"parser_error:{path}: YAML-Parser fehlt") from exc
            yaml.safe_load(text)
        elif suffix == ".sql":
            meaningful = re.sub(
                r"--[^\n]*(?:\n|$)|/\*.*?\*/", "", text, flags=re.DOTALL
            ).strip()
            if not meaningful:
                raise ContractError(f"parser_error:{path}: leeres SQLite-Skript")
            connection = sqlite3.connect(":memory:")
            try:
                connection.executescript(text)
            finally:
                connection.close()
    except ContractError:
        raise
    except Exception as exc:
        raise ContractError(f"parser_error:{path}: {exc}") from exc


def _sql_statements(text: str, path: str) -> list[str]:
    _balanced(text, path)
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


def _parse_batch_units(text: str, path: str) -> None:
    _balanced(text, path)
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


def _parse_powershell(text: str, path: str) -> dict[str, list[dict[str, Any]]]:
    executable = shutil.which("powershell") or shutil.which("pwsh")
    if executable is None:
        raise ContractError(f"parser_error:{path}: PowerShell-AST-Parser fehlt")
    parser_script = (
        "$tokens=$null;$errors=$null;"
        "$ast=[System.Management.Automation.Language.Parser]::ParseInput("
        "[Console]::In.ReadToEnd(),[ref]$tokens,[ref]$errors);"
        "if($errors.Count){$errors|ForEach-Object{$_.Message}|Write-Error;exit 2};"
        "$functions=@($ast.FindAll({param($n)$n -is "
        "[System.Management.Automation.Language.FunctionDefinitionAst]},$true)|ForEach-Object{"
        "[pscustomobject]@{name=$_.Name;start_offset=$_.Extent.StartOffset;"
        "end_offset=$_.Extent.EndOffset;start_line=$_.Extent.StartLineNumber;"
        "end_line=$_.Extent.EndLineNumber}});"
        "$commands=@($ast.FindAll({param($n)$n -is "
        "[System.Management.Automation.Language.CommandAst]},$true)|ForEach-Object{"
        "[pscustomobject]@{name=$_.GetCommandName();start_offset=$_.Extent.StartOffset;"
        "end_offset=$_.Extent.EndOffset;line=$_.Extent.StartLineNumber;"
        "column=$_.Extent.StartColumnNumber}});"
        "[pscustomobject]@{functions=$functions;commands=$commands}|"
        "ConvertTo-Json -Depth 4 -Compress"
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
    try:
        parsed = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ContractError(f"parser_error:{path}: PowerShell-AST-Ausgabe ungueltig") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("functions"), list) or not isinstance(parsed.get("commands"), list):
        raise ContractError(f"parser_error:{path}: PowerShell-AST-Schema ungueltig")
    return parsed


class Collector(ast.NodeVisitor):
    def __init__(self, path: str, blob_sha: str, binding: dict[str, str]) -> None:
        self.path = path
        self.blob_sha = blob_sha
        self.binding = binding
        self.scope: list[str] = []
        self.current_symbol: list[str] = []
        self.symbols: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []

    def _bound(self) -> dict[str, str]:
        return {**self.binding, "source_blob_sha256": self.blob_sha}

    def _symbol(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified = ".".join([*self.scope, node.name])
        kind = "async-method" if isinstance(node, ast.AsyncFunctionDef) else "method"
        if not self.scope or (self.scope and self.scope[-1].endswith("()")):
            kind = "async-function" if isinstance(node, ast.AsyncFunctionDef) else "function"
        symbol_id = _id("SYM", self.path, qualified, node.lineno, node.end_lineno, kind)
        self.symbols.append({
            "symbol_id": symbol_id, "path": self.path, "qualified_name": qualified,
            "kind": kind, "line_start": node.lineno, "line_end": node.end_lineno,
            **self._bound(),
        })
        self.scope.append(f"{node.name}()")
        self.current_symbol.append(symbol_id)
        for decorator in node.decorator_list:
            self._edge(decorator, "decorator", _dotted(decorator.func if isinstance(decorator, ast.Call) else decorator))
            self.visit(decorator)
        arguments = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        if node.args.vararg:
            arguments.append(node.args.vararg)
        if node.args.kwarg:
            arguments.append(node.args.kwarg)
        for argument in arguments:
            if argument.annotation is not None:
                self._edge(argument.annotation, "annotation", _dotted(argument.annotation))
                self.visit(argument.annotation)
        if node.returns is not None:
            self._edge(node.returns, "annotation", _dotted(node.returns))
            self.visit(node.returns)
        for default in [*node.args.defaults, *(item for item in node.args.kw_defaults if item is not None)]:
            self._edge(default, "default", _dotted(default))
            self.visit(default)
        for child in node.body:
            self.visit(child)
        self.current_symbol.pop()
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._symbol(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._symbol(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified = ".".join([*self.scope, node.name])
        symbol_id = _id("SYM", self.path, qualified, node.lineno, node.end_lineno, "class")
        self.symbols.append({
            "symbol_id": symbol_id, "path": self.path, "qualified_name": qualified,
            "kind": "class", "line_start": node.lineno, "line_end": node.end_lineno,
            **self._bound(),
        })
        self.scope.append(node.name)
        self.current_symbol.append(symbol_id)
        for decorator in node.decorator_list:
            self._edge(decorator, "decorator", _dotted(decorator.func if isinstance(decorator, ast.Call) else decorator))
            self.visit(decorator)
        for base in node.bases:
            self._edge(base, "class-base", _dotted(base))
            self.visit(base)
        for keyword in node.keywords:
            target = _dotted(keyword.value.func if isinstance(keyword.value, ast.Call) else keyword.value)
            self._edge(keyword.value, "class-keyword", target)
            self.visit(keyword.value)
        for child in node.body:
            self.visit(child)
        self.current_symbol.pop()
        self.scope.pop()

    def _edge(self, node: ast.AST, kind: str, target: str) -> None:
        line = int(getattr(node, "lineno", 0))
        col = int(getattr(node, "col_offset", 0))
        source = self.current_symbol[-1] if self.current_symbol else f"MODULE:{self.path}"
        edge_id = _id("EDGE", self.path, line, col, kind, source, target)
        self.edges.append({
            "edge_id": edge_id, "path": self.path, "line": line, "column": col,
            "edge_kind": kind, "source_symbol_id": source, "target": target,
            **self._bound(),
        })

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._edge(node, "import", alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        for alias in node.names:
            self._edge(node, "import-from", f"{module}:{alias.name}")

    def visit_Call(self, node: ast.Call) -> None:
        target = _dotted(node.func)
        leaf = target.rsplit(".", 1)[-1]
        if leaf in {"import_module", "__import__"}:
            kind = "dynamic-import"
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                target = node.args[0].value
        elif leaf in {"getattr", "setattr", "hasattr"}:
            kind = "reflection"
            if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
                target = f"{_dotted(node.args[0])}.{node.args[1].value}"
        elif leaf == "connect":
            kind = "qt-connect"
            if node.args:
                target = _dotted(node.args[0])
        elif target.startswith("subprocess.") or leaf in {"Popen", "run", "check_call", "check_output"}:
            kind = "subprocess"
        else:
            kind = "call"
        self._edge(node, kind, target)
        self.generic_visit(node)


def enumerate_contract_universe(
    root: Path, audited_commit: str, run_id: str, snapshot_id: str, *,
    tooling_commit: str, signed_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = root.resolve()
    commit = resolve_commit(root, audited_commit)
    relevant_suffixes = {".py", ".ps1", ".psm1", ".bat", ".cmd", ".sql", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".ui", ".ts"}
    paths = [
        value.decode("utf-8", "surrogateescape")
        for value in _git(root, "ls-tree", "-r", "--name-only", "-z", commit).split(b"\0")
        if value and Path(value.decode("utf-8", "surrogateescape")).suffix.lower() in relevant_suffixes
    ]
    symbols: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for path in sorted(paths):
        data = _git(root, "show", f"{commit}:{path}")
        suffix = Path(path).suffix.lower()
        try:
            if suffix == ".py":
                encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
                text = data.decode(encoding)
            else:
                text = data.decode("utf-8")
        except (LookupError, SyntaxError, UnicodeDecodeError) as exc:
            raise ContractError(f"Encoding-/Decodefehler in {path}: {exc}") from exc
        binding = {
            "run_id": run_id, "audited_commit": commit, "snapshot_id": snapshot_id,
            "tooling_commit": tooling_commit, "source_blob_sha256": _sha(data),
            "signed_at": signed_at,
        }
        if suffix == ".py":
            try:
                tree = ast.parse(text, filename=path)
            except SyntaxError as exc:
                raise ContractError(f"Python-Parserfehler in {path}: {exc}") from exc
            collector = Collector(path, _sha(data), {
                "run_id": run_id, "audited_commit": commit, "snapshot_id": snapshot_id,
                "tooling_commit": tooling_commit, "signed_at": signed_at,
            })
            collector.visit(tree)
            symbols.extend(collector.symbols)
            edges.extend(collector.edges)
            continue
        if suffix in {".ps1", ".psm1"}:
            ps_ast = _parse_powershell(text, path)
            ps_symbols: dict[str, dict[str, Any]] = {}
            ps_ranges: dict[str, tuple[int, int]] = {}
            for function in ps_ast["functions"]:
                name = str(function.get("name", ""))
                start = int(function.get("start_line", 0))
                end = int(function.get("end_line", 0))
                start_offset = int(function.get("start_offset", -1))
                end_offset = int(function.get("end_offset", -1))
                if not name or start < 1 or end < start or start_offset < 0 or end_offset <= start_offset:
                    raise ContractError(f"parser_error:{path}: PowerShell-Function-AST ungueltig")
                row = {
                    "symbol_id": _id("SYM", path, name, start, end, "powershell-function"),
                    "path": path, "qualified_name": name, "kind": "powershell-function",
                    "line_start": start, "line_end": end, **binding,
                }
                symbols.append(row)
                ps_symbols[name.lower()] = row
                ps_ranges[name.lower()] = (start_offset, end_offset)
            for command in ps_ast["commands"]:
                target_name = str(command.get("name") or "")
                target = ps_symbols.get(target_name.lower())
                offset = int(command.get("start_offset", -1))
                if target is None or offset < 0:
                    continue
                containing = [
                    (end - start, name) for name, (start, end) in ps_ranges.items()
                    if start <= offset < end
                ]
                source = ps_symbols[min(containing)[1]] if containing else None
                line = int(command.get("line", 0))
                column = max(0, int(command.get("column", 1)) - 1)
                source_id = source["symbol_id"] if source else f"MODULE:{path}"
                edges.append({
                    "edge_id": _id("EDGE", path, line, column, "powershell-call", source_id, target["qualified_name"]),
                    "path": path, "line": line, "column": column,
                    "edge_kind": "powershell-call", "source_symbol_id": source_id,
                    "target": target["qualified_name"], "target_symbol_id": target["symbol_id"], **binding,
                })
            continue
        if suffix in {".bat", ".cmd"}:
            _parse_batch_units(text, path)
            matches = list(re.finditer(r"(?im)^\s*:([^:\s]+)", text))
            label_ids: dict[str, str] = {}
            total_lines = max(1, len(text.splitlines()))
            for index, match in enumerate(matches):
                start = text.count("\n", 0, match.start()) + 1
                end = (
                    text.count("\n", 0, matches[index + 1].start())
                    if index + 1 < len(matches) else total_lines
                )
                name = match.group(1)
                if name.lower() in label_ids:
                    raise ContractError(f"parser_error:{path}:{start}: doppeltes Label {name}")
                symbol_id = _id("SYM", path, name, start, end, "batch-label")
                label_ids[name.lower()] = symbol_id
                symbols.append({
                    "symbol_id": symbol_id, "path": path, "qualified_name": name,
                    "kind": "batch-label", "line_start": start, "line_end": end, **binding,
                })
            for match in re.finditer(r"(?im)^\s*call\s+:([^\s]+)", text):
                line = text.count("\n", 0, match.start()) + 1
                target = match.group(1)
                current = next(
                    (row for row in reversed(symbols) if row["path"] == path and row["line_start"] <= line <= row["line_end"]),
                    None,
                )
                edges.append({
                    "edge_id": _id("EDGE", path, line, 0, "batch-call", current["symbol_id"] if current else f"MODULE:{path}", target),
                    "path": path, "line": line, "column": 0, "edge_kind": "batch-call",
                    "source_symbol_id": current["symbol_id"] if current else f"MODULE:{path}", "target": target,
                    "target_symbol_id": label_ids.get(target.lower()), **binding,
                })
            continue
        _parse_structured(text, suffix, path)
        kind = "schema-unit" if suffix == ".sql" else (
            "ui-unit" if suffix == ".ui" else "translation-unit" if suffix == ".ts" else "config-unit"
        )
        line_end = max(1, len(text.splitlines()))
        unit = {
            "symbol_id": _id("SYM", path, path, 1, line_end, kind),
            "path": path, "qualified_name": path, "kind": kind,
            "line_start": 1, "line_end": line_end, **binding,
        }
        if suffix == ".sql":
            unit["parser_dialect"] = SUPPORTED_SQL_DIALECT
        symbols.append(unit)

    name_index: dict[str, list[str]] = {}
    for symbol in symbols:
        qualified = str(symbol["qualified_name"])
        for name in {qualified, qualified.rsplit(".", 1)[-1].removesuffix("()") }:
            name_index.setdefault(name, []).append(str(symbol["symbol_id"]))
    for edge in edges:
        if "target_symbol_id" not in edge:
            target = str(edge.get("target", ""))
            candidates = name_index.get(target, [])
            if not candidates and "." in target:
                candidates = name_index.get(target.rsplit(".", 1)[-1], [])
            edge["target_symbol_id"] = candidates[0] if len(candidates) == 1 else None
    return (
        sorted(symbols, key=lambda row: row["symbol_id"]),
        sorted(edges, key=lambda row: row["edge_id"]),
    )


def universe_digest(rows: Iterable[dict[str, Any]], id_field: str) -> str:
    return _sha(b"\n".join(_canonical(row) for row in sorted(rows, key=lambda item: item[id_field])))


def _validate_binding(
    row: dict[str, Any], label: str, run_id: str, commit: str,
    tooling_commit: str, snapshot: str, errors: list[str],
) -> None:
    if (
        row.get("run_id") != run_id or row.get("audited_commit") != commit
        or row.get("tooling_commit") != tooling_commit
        or row.get("snapshot_id") != snapshot
    ):
        errors.append(f"{label}: Run-/Commit-/Tooling-/Snapshotbindung falsch")


def validate_contracts(
    expected_symbols: list[dict[str, Any]], expected_edges: list[dict[str, Any]],
    states: list[dict[str, Any]], edge_states: list[dict[str, Any]], *,
    run_id: str, audited_commit: str, tooling_commit: str, snapshot_id: str,
    feature_records: list[dict[str, Any]], feature_manifest: dict[str, Any],
    runtime_records: list[dict[str, Any]], runtime_manifest: dict[str, Any],
    reviewer_records: list[dict[str, Any]], reviewer_manifest: dict[str, Any],
    evidence_records: list[dict[str, Any]], evidence_manifest: dict[str, Any],
    trigger_records: list[dict[str, Any]], trigger_manifest: dict[str, Any],
    audit_contract: dict[str, Any], expected_contract_sha256: str,
    evidence_contract: dict[str, Any], expected_evidence_contract_sha256: str,
    evidence_root: Path,
) -> list[str]:
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
        (expected_symbols, audit_contract, "symbol-catalog", "Symbolkatalog", False),
        (expected_edges, audit_contract, "edge-catalog", "Kantenkatalog", False),
        (feature_records, audit_contract, "feature-catalog", "Featurekatalog", False),
        (trigger_records, audit_contract, "trigger-universe", "Triggeruniversum", False),
        (states, evidence_contract, "symbol-state", "Symbol-State", True),
        (edge_states, evidence_contract, "edge-state", "Kanten-State", True),
        (evidence_records, evidence_contract, "symbol-state-evidence", "Symbol-Evidence", True),
        (reviewer_records, evidence_contract, "reviewer-roster", "Reviewer-Roster", True),
        (runtime_records, evidence_contract, "runtime-evidence", "Runtime-Evidence", True),
    ):
        errors.extend(_artifact_binding_errors(records, contract, key, label))
        errors.extend(_record_time_errors(
            records, audit_contract, label,
            evidence_contract.get("completed_at") if is_output else None,
        ))
    symbol_map = {row["symbol_id"]: row for row in expected_symbols}
    edge_map = {row["edge_id"]: row for row in expected_edges}
    if len(symbol_map) != len(expected_symbols):
        errors.append("Symboluniversum enthaelt doppelte IDs")
    if len(edge_map) != len(expected_edges):
        errors.append("Kantenuniversum enthaelt doppelte IDs")
    symbol_hash = universe_digest(expected_symbols, "symbol_id")
    edge_hash = universe_digest(expected_edges, "edge_id")
    artifact_specs = (
        (feature_records, feature_manifest, "feature-catalog", "catalog_id"),
        (runtime_records, runtime_manifest, "runtime-evidence", "evidence_id"),
        (reviewer_records, reviewer_manifest, "reviewer-roster", "reviewer_id"),
        (evidence_records, evidence_manifest, "symbol-evidence", "evidence_id"),
        (trigger_records, trigger_manifest, "trigger-catalog", "source_id"),
    )
    artifact_indexes: list[dict[str, dict[str, Any]]] = []
    for records, manifest, kind, id_field in artifact_specs:
        index, artifact_errors = validate_artifact_universe(
            records, manifest, kind, id_field, run_id=run_id,
            audited_commit=audited_commit, tooling_commit=tooling_commit,
            snapshot_id=snapshot_id,
        )
        artifact_indexes.append(index)
        errors.extend(artifact_errors)
    known_feature_ids = {
        str(row.get("feature_id", "")) for row in artifact_indexes[0].values()
        if row.get("feature_id")
    }
    runtime_evidence_ids = set(artifact_indexes[1])
    reviewer_ids = set(artifact_indexes[2])
    evidence_ids = set(artifact_indexes[3])
    canonical_triggers = list(artifact_indexes[4].values())
    if not known_feature_ids:
        errors.append("Featureuniversum ist leer")
    if not reviewer_ids:
        errors.append("Reviewer-Roster ist leer")
    if not evidence_ids:
        errors.append("Evidence-Universum ist leer")
    for prefix, records in (
        ("symbol-proof", evidence_records), ("runtime-proof", runtime_records),
    ):
        expected_proofs = {f"{prefix}:{row.get('evidence_id', '')}" for row in records}
        actual_proofs = {
            key for key in evidence_contract.get("artifacts", {})
            if isinstance(key, str) and key.startswith(f"{prefix}:")
        }
        if actual_proofs != expected_proofs:
            errors.append(
                f"{prefix}-Key-Exact-Set verletzt: "
                f"fehlend={sorted(expected_proofs - actual_proofs)!r}, "
                f"extra={sorted(actual_proofs - expected_proofs)!r}"
            )

    for number, runtime in enumerate(runtime_records, 1):
        label = f"Runtime-Evidence Zeile {number}"
        expected_fields = {
            "evidence_id", "evidence_kind", "symbol_id", "reviewer_id", "path",
            "source_blob_sha256", "proof_ref", "run_id", "audited_commit",
            "tooling_commit", "snapshot_id", "signed_at", "record_sha256",
        }
        if set(runtime) != expected_fields:
            errors.append(f"{label}: Schemafelder nicht exakt")
        if runtime.get("evidence_kind") != "runtime":
            errors.append(f"{label}: evidence_kind ungueltig")
        _validate_binding(
            runtime, label, run_id, audited_commit, tooling_commit, snapshot_id, errors,
        )
        source = symbol_map.get(str(runtime.get("symbol_id", "")))
        if source is None:
            errors.append(f"{label}: fremde symbol_id")
        elif (
            runtime.get("path") != source.get("path")
            or runtime.get("source_blob_sha256") != source.get("source_blob_sha256")
        ):
            errors.append(f"{label}: Source-Pfad/Blob falsch")
        if runtime.get("reviewer_id") not in reviewer_ids:
            errors.append(f"{label}: Reviewer-FK fehlt")
        if not _safe_ref(runtime.get("proof_ref")):
            errors.append(f"{label}: proof_ref ungueltig")
        if not re.fullmatch(r"[0-9a-f]{64}", str(runtime.get("source_blob_sha256", ""))):
            errors.append(f"{label}: source_blob_sha256 ungueltig")
        proof_expected = {field: runtime.get(field) for field in (
            "evidence_id", "evidence_kind", "symbol_id", "reviewer_id", "path",
            "source_blob_sha256",
        ) if field in runtime}
        proof_expected["schema_version"] = 1
        errors.extend(_proof_errors(
            runtime, evidence_contract, evidence_root, prefix="runtime-proof",
            expected=proof_expected, label=label,
        ))

    for number, evidence in enumerate(evidence_records, 1):
        label = f"Symbol-Evidence Zeile {number}"
        allowed = {
            "evidence_id", "evidence_kind", "symbol_id", "edge_id", "reviewer_id",
            "path", "source_blob_sha256", "signed_at", "proof_ref",
            "run_id", "audited_commit", "tooling_commit", "snapshot_id",
            "record_sha256",
        }
        expected_fields = set(allowed) - ({"edge_id"} if evidence.get("symbol_id") else {"symbol_id"})
        if set(evidence) != expected_fields:
            errors.append(f"{label}: Schemafelder nicht exakt")
        for field in (
            "evidence_kind", "reviewer_id", "path", "source_blob_sha256",
            "signed_at",
        ):
            if not evidence.get(field):
                errors.append(f"{label}: {field} fehlt")
        has_symbol = bool(evidence.get("symbol_id"))
        has_edge = bool(evidence.get("edge_id"))
        if has_symbol == has_edge:
            errors.append(f"{label}: exakt symbol_id oder edge_id erforderlich")
        source = symbol_map.get(str(evidence.get("symbol_id", ""))) if has_symbol else edge_map.get(str(evidence.get("edge_id", "")))
        if source is None:
            errors.append(f"{label}: fremdes Ziel")
        elif evidence.get("path") != source.get("path") or evidence.get("source_blob_sha256") != source.get("source_blob_sha256"):
            errors.append(f"{label}: Source-Pfad/Blob falsch")
        if evidence.get("reviewer_id") not in reviewer_ids:
            errors.append(f"{label}: Reviewer-FK fehlt")
        proof_ref = evidence.get("proof_ref")
        if not _safe_ref(proof_ref):
            errors.append(f"{label}: proof_ref ungueltig")
        expected_kind = "symbol-review" if has_symbol else "edge-review"
        if evidence.get("evidence_kind") != expected_kind:
            errors.append(f"{label}: evidence_kind ungueltig")
        proof_expected = {field: evidence.get(field) for field in (
            "evidence_id", "evidence_kind", "reviewer_id", "path", "source_blob_sha256",
        )}
        proof_expected["symbol_id" if has_symbol else "edge_id"] = evidence.get(
            "symbol_id" if has_symbol else "edge_id"
        )
        proof_expected["schema_version"] = 1
        errors.extend(_proof_errors(
            evidence, evidence_contract, evidence_root, prefix="symbol-proof",
            expected=proof_expected, label=label,
        ))
        if not re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("source_blob_sha256", ""))):
            errors.append(f"{label}: source_blob_sha256 ungueltig")

    evidence_consumers: set[str] = set()

    def validate_evidence(
        values: object, label: str, *, symbol_id: str | None = None,
        edge_id: str | None = None, reviewer_id: object = None,
        signed_at: object = None,
    ) -> None:
        if not isinstance(values, list) or not values:
            errors.append(f"{label}: Evidence-IDs fehlen")
        elif (
            any(not isinstance(value, str) or value not in evidence_ids for value in values)
            or len(values) != len(set(values))
        ):
            errors.append(f"{label}: unbekannte Evidence-ID oder Duplikat")
        else:
            for value in values:
                evidence_consumers.add(value)
                evidence = artifact_indexes[3][value]
                if symbol_id is not None and evidence.get("symbol_id") != symbol_id:
                    errors.append(f"{label}: Evidence-Symbol-FK falsch")
                if edge_id is not None and evidence.get("edge_id") != edge_id:
                    errors.append(f"{label}: Evidence-Kanten-FK falsch")
                if evidence.get("reviewer_id") != reviewer_id:
                    errors.append(f"{label}: Evidence-Reviewer-FK falsch")
                if evidence.get("signed_at") != signed_at:
                    errors.append(f"{label}: Evidence-signed_at-FK falsch")

    seen_symbols: set[str] = set()
    runtime_consumers: dict[str, int] = {}
    for number, row in enumerate(states, 1):
        symbol_id = str(row.get("symbol_id", ""))
        label = f"Symbol-State Zeile {number}/{symbol_id}"
        state_fields = {
            "symbol_id", "path", "qualified_name", "kind", "line_start", "line_end",
            "source_blob_sha256", "run_id", "audited_commit", "tooling_commit",
            "snapshot_id", "symbols_sha256", "edges_sha256", "role", "feature_ids",
            "reviewer_id", "caller_contract", "contracts", "disposition",
            "runtime_evidence_ids", "signed_at",
        }
        if row.get("disposition") == "non-runtime":
            state_fields.add("non_runtime_contract")
        if row.get("disposition") == "unknown":
            state_fields.add("unknown_reason")
        if set(row) != state_fields:
            errors.append(f"{label}: Schemafelder nicht exakt")
        if symbol_id in seen_symbols:
            errors.append(f"{label}: doppelte symbol_id")
        seen_symbols.add(symbol_id)
        source = symbol_map.get(symbol_id)
        if source is None:
            errors.append(f"{label}: fremde symbol_id")
        else:
            for field in ("path", "qualified_name", "kind", "line_start", "line_end", "source_blob_sha256"):
                if row.get(field) != source.get(field):
                    errors.append(f"{label}: {field} weicht vom Universum ab")
        _validate_binding(
            row, label, run_id, audited_commit, tooling_commit, snapshot_id, errors,
        )
        if row.get("symbols_sha256") != symbol_hash or row.get("edges_sha256") != edge_hash:
            errors.append(f"{label}: Universumshash falsch")
        role = row.get("role")
        if role not in {"feature", "support", "framework", "dead-candidate"}:
            errors.append(f"{label}: role ungueltig")
        feature_ids = row.get("feature_ids")
        if not isinstance(feature_ids, list) or not feature_ids or len(feature_ids) != len(set(feature_ids)):
            errors.append(f"{label}: feature_ids fehlt/leer/doppelt")
        elif any(feature_id not in known_feature_ids for feature_id in feature_ids):
            errors.append(f"{label}: unbekannte feature_id")
        if row.get("reviewer_id") not in reviewer_ids:
            errors.append(f"{label}: unbekannter Reviewer")
        caller = row.get("caller_contract")
        if not isinstance(caller, dict) or caller.get("kind") not in {"incoming-edges", "framework-hook", "entrypoint", "unreferenced"}:
            errors.append(f"{label}: Caller-/Frameworkvertrag fehlt")
        else:
            validate_evidence(
                caller.get("evidence_ids"), f"{label}/Caller", symbol_id=symbol_id,
                reviewer_id=row.get("reviewer_id"), signed_at=row.get("signed_at"),
            )
            caller_edges = caller.get("edge_ids")
            incoming = {
                edge_id for edge_id, edge in edge_map.items()
                if edge.get("target_symbol_id") == symbol_id
            }
            trigger_match = any(
                trigger.get("path") == row.get("path")
                and (
                    trigger.get("target_symbol_id") == symbol_id
                    or (
                        trigger.get("source_kind") in {"entrypoint", "main-guard", "decorator-hook"}
                        and str(row.get("qualified_name", "")).rsplit(".", 1)[-1].removesuffix("()")
                        in {str(trigger.get("detail", "")), "main"}
                    )
                )
                for trigger in canonical_triggers
            )
            if not isinstance(caller_edges, list):
                errors.append(f"{label}: Caller-edge_ids fehlt")
            elif incoming:
                if caller.get("kind") != "incoming-edges" or set(caller_edges) != incoming:
                    errors.append(f"{label}: kanonische Incoming-Kanten nicht exakt dispositioniert")
            elif caller_edges:
                errors.append(f"{label}: Symbol ohne Incoming darf keine edge_ids behaupten")
            elif trigger_match and caller.get("kind") not in {"entrypoint", "framework-hook"}:
                errors.append(f"{label}: kanonischer Entry-/Frameworkhook falsch dispositioniert")
            elif not trigger_match and caller.get("kind") != "unreferenced":
                errors.append(f"{label}: entrypoint/framework ohne kanonischen Trigger")
        contracts = row.get("contracts")
        if not isinstance(contracts, dict):
            errors.append(f"{label}: contracts fehlt")
        else:
            if set(contracts) != set(CONTRACT_KEYS):
                errors.append(f"{label}: Contract-Objekt Felder nicht exakt")
            for key in CONTRACT_KEYS:
                cell = contracts.get(key)
                if not isinstance(cell, dict) or cell.get("status") not in {"reviewed", "n-a", "unknown"}:
                    errors.append(f"{label}: Vertrag {key} fehlt/ungueltig")
                else:
                    if set(cell) != {"status", "evidence_ids"}:
                        errors.append(f"{label}: Vertrag {key} Schemafelder nicht exakt")
                    validate_evidence(
                        cell.get("evidence_ids"), f"{label}/Vertrag {key}",
                        symbol_id=symbol_id, reviewer_id=row.get("reviewer_id"),
                        signed_at=row.get("signed_at"),
                    )
        disposition = row.get("disposition")
        if disposition not in SYMBOL_DISPOSITIONS:
            errors.append(f"{label}: disposition ungueltig")
        if disposition == "runtime":
            runtime_ids = row.get("runtime_evidence_ids")
            if not isinstance(runtime_ids, list) or not runtime_ids:
                errors.append(f"{label}: Runtime-Disposition ohne Evidence-ID")
            else:
                string_runtime_ids = [value for value in runtime_ids if isinstance(value, str)]
                if len(string_runtime_ids) != len(runtime_ids) or len(string_runtime_ids) != len(set(string_runtime_ids)):
                    errors.append(f"{label}: Runtime-Evidence-ID doppelt konsumiert")
                for evidence_id in runtime_ids:
                    if not isinstance(evidence_id, str) or evidence_id not in runtime_evidence_ids:
                        errors.append(f"{label}: unbekannte Runtime-Evidence-ID")
                        continue
                    runtime_consumers[evidence_id] = runtime_consumers.get(evidence_id, 0) + 1
                    if artifact_indexes[1][evidence_id].get("symbol_id") != symbol_id:
                        errors.append(f"{label}: Runtime-Evidence-Symbol-FK falsch")
                    if artifact_indexes[1][evidence_id].get("reviewer_id") != row.get("reviewer_id"):
                        errors.append(f"{label}: Runtime-Evidence-Reviewer-FK falsch")
                    if artifact_indexes[1][evidence_id].get("signed_at") != row.get("signed_at"):
                        errors.append(f"{label}: Runtime-Evidence-signed_at-FK falsch")
        if disposition == "non-runtime":
            if row.get("runtime_evidence_ids") not in ([], None):
                errors.append(f"{label}: Non-Runtime-Disposition mit Runtime-Evidence-ID")
            contract = row.get("non_runtime_contract")
            if not isinstance(contract, dict) or not all(contract.get(key) for key in ("kind", "evidence_id", "reason")):
                errors.append(f"{label}: Non-Runtime-Vertrag fehlt")
            elif contract["evidence_id"] not in evidence_ids:
                errors.append(f"{label}: Non-Runtime-Vertrag referenziert unbekannte Evidence-ID")
            elif artifact_indexes[3][contract["evidence_id"]].get("symbol_id") != symbol_id:
                errors.append(f"{label}: Non-Runtime-Evidence-Symbol-FK falsch")
            else:
                evidence_consumers.add(contract["evidence_id"])
                evidence = artifact_indexes[3][contract["evidence_id"]]
                if evidence.get("reviewer_id") != row.get("reviewer_id"):
                    errors.append(f"{label}: Non-Runtime-Evidence-Reviewer-FK falsch")
                if evidence.get("signed_at") != row.get("signed_at"):
                    errors.append(f"{label}: Non-Runtime-Evidence-signed_at-FK falsch")
        if disposition == "unknown" and not row.get("unknown_reason"):
            errors.append(f"{label}: UNKNOWN ohne Grund")

    seen_edges: set[str] = set()
    for number, row in enumerate(edge_states, 1):
        edge_id = str(row.get("edge_id", ""))
        label = f"Kanten-State Zeile {number}/{edge_id}"
        edge_fields = {
            "edge_id", "path", "line", "column", "edge_kind", "source_symbol_id",
            "target", "target_symbol_id", "source_blob_sha256", "run_id",
            "audited_commit", "tooling_commit", "snapshot_id", "symbols_sha256",
            "edges_sha256", "disposition", "reviewer_id", "evidence_ids", "signed_at",
        }
        if row.get("disposition") == "unknown":
            edge_fields.add("unknown_reason")
        if set(row) != edge_fields:
            errors.append(f"{label}: Schemafelder nicht exakt")
        if edge_id in seen_edges:
            errors.append(f"{label}: doppelte edge_id")
        seen_edges.add(edge_id)
        source = edge_map.get(edge_id)
        if source is None:
            errors.append(f"{label}: fremde edge_id")
        else:
            for field in (
                "path", "line", "column", "edge_kind", "source_symbol_id",
                "target", "target_symbol_id", "source_blob_sha256",
            ):
                if row.get(field) != source.get(field):
                    errors.append(f"{label}: {field} weicht vom Universum ab")
        _validate_binding(
            row, label, run_id, audited_commit, tooling_commit, snapshot_id, errors,
        )
        if row.get("symbols_sha256") != symbol_hash or row.get("edges_sha256") != edge_hash:
            errors.append(f"{label}: Universumshash falsch")
        if row.get("disposition") not in EDGE_DISPOSITIONS:
            errors.append(f"{label}: disposition ungueltig")
        elif row.get("disposition") == "unknown" and not row.get("unknown_reason"):
            errors.append(f"{label}: UNKNOWN-Kante ohne Grund")
        if row.get("reviewer_id") not in reviewer_ids:
            errors.append(f"{label}: unbekannter Reviewer")
        validate_evidence(
            row.get("evidence_ids"), label, edge_id=edge_id,
            reviewer_id=row.get("reviewer_id"), signed_at=row.get("signed_at"),
        )

    if set(symbol_map) != seen_symbols:
        errors.append(
            "Symbol-Exact-Set verletzt: "
            f"fehlend={sorted(set(symbol_map) - seen_symbols)!r}, extra={sorted(seen_symbols - set(symbol_map))!r}"
        )
    if set(edge_map) != seen_edges:
        errors.append(
            "Kanten-Exact-Set verletzt: "
            f"fehlend={sorted(set(edge_map) - seen_edges)!r}, extra={sorted(seen_edges - set(edge_map))!r}"
        )
    orphan_evidence = evidence_ids - evidence_consumers
    if orphan_evidence:
        errors.append(f"Symbol-/Edge-Evidence-Closure verletzt: orphan={sorted(orphan_evidence)!r}")
    orphan_runtime = runtime_evidence_ids - set(runtime_consumers)
    duplicate_runtime = sorted(
        evidence_id for evidence_id, count in runtime_consumers.items() if count != 1
    )
    if orphan_runtime or duplicate_runtime:
        errors.append(
            "Runtime-Evidence-Exact-Set verletzt: "
            f"orphan={sorted(orphan_runtime)!r}, mehrfach={duplicate_runtime!r}"
        )
    if not expected_symbols:
        errors.append("Symboluniversum ist leer")
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
    verify = sub.add_parser("validate")
    for item in (enum, verify):
        item.add_argument("--root", type=Path, required=True)
        item.add_argument("--audited-commit", required=True)
        item.add_argument("--run-id", required=True)
        item.add_argument("--snapshot-id", required=True)
    enum.add_argument("--signed-at", required=True)
    enum.add_argument("--tooling-commit", required=True)
    enum.add_argument("--symbols-out", type=Path, required=True)
    enum.add_argument("--edges-out", type=Path, required=True)
    verify.add_argument("--symbols", type=Path, required=True)
    verify.add_argument("--edges", type=Path, required=True)
    verify.add_argument("--symbol-states", type=Path, required=True)
    verify.add_argument("--edge-states", type=Path, required=True)
    verify.add_argument("--feature-universe", type=Path, required=True)
    verify.add_argument("--runtime-universe", type=Path, required=True)
    verify.add_argument("--reviewer-roster", type=Path, required=True)
    verify.add_argument("--evidence-universe", type=Path, required=True)
    verify.add_argument("--trigger-universe", type=Path, required=True)
    verify.add_argument("--feature-manifest", type=Path, required=True)
    verify.add_argument("--runtime-manifest", type=Path, required=True)
    verify.add_argument("--reviewer-manifest", type=Path, required=True)
    verify.add_argument("--evidence-manifest", type=Path, required=True)
    verify.add_argument("--trigger-manifest", type=Path, required=True)
    verify.add_argument("--tooling-commit", required=True)
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
        symbols, edges = enumerate_contract_universe(
            args.root, args.audited_commit, args.run_id, args.snapshot_id,
            tooling_commit=args.tooling_commit, signed_at=signed_at,
        )
        if args.command == "enumerate":
            _write_jsonl(args.symbols_out, symbols)
            _write_jsonl(args.edges_out, edges)
            print(json.dumps({
                "ok": True, "symbols": len(symbols), "edges": len(edges),
                "symbols_sha256": universe_digest(symbols, "symbol_id"),
                "edges_sha256": universe_digest(edges, "edge_id"),
            }, sort_keys=True))
            return 0
        errors: list[str] = []
        if _read_jsonl(args.symbols) != symbols:
            errors.append("Symboluniversum weicht von kanonischer Gitobjekt-Enumeration ab")
        if _read_jsonl(args.edges) != edges:
            errors.append("Kantenuniversum weicht von kanonischer Gitobjekt-Enumeration ab")
        audit_contract = json.loads(args.audit_contract.read_text(encoding="utf-8"))
        evidence_contract = json.loads(args.evidence_contract.read_text(encoding="utf-8"))
        errors.extend(validate_contracts(
            symbols, edges, _read_jsonl(args.symbol_states), _read_jsonl(args.edge_states),
            run_id=args.run_id, audited_commit=resolve_commit(args.root.resolve(), args.audited_commit),
            tooling_commit=args.tooling_commit, snapshot_id=args.snapshot_id,
            feature_records=_read_jsonl(args.feature_universe),
            feature_manifest=json.loads(args.feature_manifest.read_text(encoding="utf-8")),
            runtime_records=_read_jsonl(args.runtime_universe),
            runtime_manifest=json.loads(args.runtime_manifest.read_text(encoding="utf-8")),
            reviewer_records=_read_jsonl(args.reviewer_roster),
            reviewer_manifest=json.loads(args.reviewer_manifest.read_text(encoding="utf-8")),
            evidence_records=_read_jsonl(args.evidence_universe),
            evidence_manifest=json.loads(args.evidence_manifest.read_text(encoding="utf-8")),
            trigger_records=_read_jsonl(args.trigger_universe),
            trigger_manifest=json.loads(args.trigger_manifest.read_text(encoding="utf-8")),
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
