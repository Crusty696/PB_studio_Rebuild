#!/usr/bin/env python3
"""Enumerate and validate Python symbol/edge/state contracts at a Git commit."""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import subprocess
import sys
import tokenize
from pathlib import Path
from typing import Any, Iterable


CONTRACT_KEYS = ("inputs", "outputs", "side_effects", "errors", "config", "persistence")
EDGE_DISPOSITIONS = {"resolved", "dynamic", "framework", "unreferenced", "unknown"}
SYMBOL_DISPOSITIONS = {"runtime", "non-runtime", "unknown"}


class ContractError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
    root: Path, audited_commit: str, run_id: str, snapshot_id: str,
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
            "source_blob_sha256": _sha(data),
        }
        if suffix == ".py":
            try:
                tree = ast.parse(text, filename=path)
            except SyntaxError as exc:
                raise ContractError(f"Python-Parserfehler in {path}: {exc}") from exc
            collector = Collector(path, _sha(data), {
                "run_id": run_id, "audited_commit": commit, "snapshot_id": snapshot_id,
            })
            collector.visit(tree)
            symbols.extend(collector.symbols)
            edges.extend(collector.edges)
            continue
        if suffix in {".ps1", ".psm1"}:
            matches = list(re.finditer(r"(?im)^\s*(?:function|filter)\s+([\w:-]+)", text))
            for index, match in enumerate(matches):
                start = text.count("\n", 0, match.start()) + 1
                end_offset = matches[index + 1].start() if index + 1 < len(matches) else len(text)
                end = max(start, text.count("\n", 0, end_offset) + (0 if end_offset == len(text) and text.endswith("\n") else 1))
                name = match.group(1)
                symbols.append({
                    "symbol_id": _id("SYM", path, name, start, end, "powershell-function"),
                    "path": path, "qualified_name": name, "kind": "powershell-function",
                    "line_start": start, "line_end": end, **binding,
                })
            continue
        if suffix in {".bat", ".cmd"}:
            matches = list(re.finditer(r"(?im)^\s*:([^:\s]+)", text))
            label_ids: dict[str, str] = {}
            for index, match in enumerate(matches):
                start = text.count("\n", 0, match.start()) + 1
                end_offset = matches[index + 1].start() if index + 1 < len(matches) else len(text)
                end = max(start, text.count("\n", 0, end_offset) + 1)
                name = match.group(1)
                symbol_id = _id("SYM", path, name, start, end, "batch-label")
                label_ids[name.lower()] = symbol_id
                symbols.append({
                    "symbol_id": symbol_id, "path": path, "qualified_name": name,
                    "kind": "batch-label", "line_start": start, "line_end": end, **binding,
                })
            for match in re.finditer(r"(?im)^\s*call\s+:([^\s]+)", text):
                line = text.count("\n", 0, match.start()) + 1
                target = match.group(1)
                edges.append({
                    "edge_id": _id("EDGE", path, line, 0, "batch-call", f"MODULE:{path}", target),
                    "path": path, "line": line, "column": 0, "edge_kind": "batch-call",
                    "source_symbol_id": f"MODULE:{path}", "target": target,
                    "target_symbol_id": label_ids.get(target.lower()), **binding,
                })
            continue
        kind = "schema-unit" if suffix == ".sql" else (
            "ui-unit" if suffix == ".ui" else "translation-unit" if suffix == ".ts" else "config-unit"
        )
        line_end = max(1, len(text.splitlines()))
        symbols.append({
            "symbol_id": _id("SYM", path, path, 1, line_end, kind),
            "path": path, "qualified_name": path, "kind": kind,
            "line_start": 1, "line_end": line_end, **binding,
        })

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


def _validate_binding(row: dict[str, Any], label: str, run_id: str, commit: str, snapshot: str, errors: list[str]) -> None:
    if row.get("run_id") != run_id or row.get("audited_commit") != commit or row.get("snapshot_id") != snapshot:
        errors.append(f"{label}: Run-/Commit-/Snapshotbindung falsch")


def validate_contracts(
    expected_symbols: list[dict[str, Any]], expected_edges: list[dict[str, Any]],
    states: list[dict[str, Any]], edge_states: list[dict[str, Any]], *,
    run_id: str, audited_commit: str, snapshot_id: str,
    known_feature_ids: set[str], runtime_evidence_ids: set[str],
    reviewer_ids: set[str], evidence_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    symbol_map = {row["symbol_id"]: row for row in expected_symbols}
    edge_map = {row["edge_id"]: row for row in expected_edges}
    if len(symbol_map) != len(expected_symbols):
        errors.append("Symboluniversum enthaelt doppelte IDs")
    if len(edge_map) != len(expected_edges):
        errors.append("Kantenuniversum enthaelt doppelte IDs")
    symbol_hash = universe_digest(expected_symbols, "symbol_id")
    edge_hash = universe_digest(expected_edges, "edge_id")
    if not known_feature_ids:
        errors.append("Featureuniversum ist leer")
    if not reviewer_ids:
        errors.append("Reviewer-Roster ist leer")
    if not evidence_ids:
        errors.append("Evidence-Universum ist leer")

    def validate_evidence(values: object, label: str) -> None:
        if not isinstance(values, list) or not values:
            errors.append(f"{label}: Evidence-IDs fehlen")
        elif any(not isinstance(value, str) or value not in evidence_ids for value in values):
            errors.append(f"{label}: unbekannte Evidence-ID")

    seen_symbols: set[str] = set()
    for number, row in enumerate(states, 1):
        symbol_id = str(row.get("symbol_id", ""))
        label = f"Symbol-State Zeile {number}/{symbol_id}"
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
        _validate_binding(row, label, run_id, audited_commit, snapshot_id, errors)
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
            validate_evidence(caller.get("evidence_ids"), f"{label}/Caller")
            caller_edges = caller.get("edge_ids")
            if not isinstance(caller_edges, list):
                errors.append(f"{label}: Caller-edge_ids fehlt")
            elif caller.get("kind") == "incoming-edges":
                if not caller_edges:
                    errors.append(f"{label}: Incoming-Caller ohne Kante")
                for edge_id in caller_edges:
                    edge = edge_map.get(edge_id)
                    if edge is None:
                        errors.append(f"{label}: Caller referenziert fremde Kante")
                    elif edge.get("target_symbol_id") != symbol_id:
                        errors.append(f"{label}: Caller-Kante referenziert nicht Zielsymbol")
            elif caller_edges:
                errors.append(f"{label}: Nicht-Incoming-Caller darf keine edge_ids behaupten")
        contracts = row.get("contracts")
        if not isinstance(contracts, dict):
            errors.append(f"{label}: contracts fehlt")
        else:
            for key in CONTRACT_KEYS:
                cell = contracts.get(key)
                if not isinstance(cell, dict) or cell.get("status") not in {"reviewed", "n-a", "unknown"}:
                    errors.append(f"{label}: Vertrag {key} fehlt/ungueltig")
                else:
                    validate_evidence(cell.get("evidence_ids"), f"{label}/Vertrag {key}")
        disposition = row.get("disposition")
        if disposition not in SYMBOL_DISPOSITIONS:
            errors.append(f"{label}: disposition ungueltig")
        if disposition == "runtime" and not row.get("runtime_evidence_ids"):
            errors.append(f"{label}: Runtime-Disposition ohne Evidence-ID")
        elif disposition == "runtime" and any(
            evidence_id not in runtime_evidence_ids for evidence_id in row.get("runtime_evidence_ids", [])
        ):
            errors.append(f"{label}: unbekannte Runtime-Evidence-ID")
        if disposition == "non-runtime":
            if row.get("runtime_evidence_ids") not in ([], None):
                errors.append(f"{label}: Non-Runtime-Disposition mit Runtime-Evidence-ID")
            contract = row.get("non_runtime_contract")
            if not isinstance(contract, dict) or not all(contract.get(key) for key in ("kind", "evidence_id", "reason")):
                errors.append(f"{label}: Non-Runtime-Vertrag fehlt")
            elif contract["evidence_id"] not in evidence_ids:
                errors.append(f"{label}: Non-Runtime-Vertrag referenziert unbekannte Evidence-ID")
        if disposition == "unknown" and not row.get("unknown_reason"):
            errors.append(f"{label}: UNKNOWN ohne Grund")

    seen_edges: set[str] = set()
    for number, row in enumerate(edge_states, 1):
        edge_id = str(row.get("edge_id", ""))
        label = f"Kanten-State Zeile {number}/{edge_id}"
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
        _validate_binding(row, label, run_id, audited_commit, snapshot_id, errors)
        if row.get("symbols_sha256") != symbol_hash or row.get("edges_sha256") != edge_hash:
            errors.append(f"{label}: Universumshash falsch")
        if row.get("disposition") not in EDGE_DISPOSITIONS:
            errors.append(f"{label}: disposition ungueltig")
        elif row.get("disposition") == "unknown" and not row.get("unknown_reason"):
            errors.append(f"{label}: UNKNOWN-Kante ohne Grund")
        if row.get("reviewer_id") not in reviewer_ids:
            errors.append(f"{label}: unbekannter Reviewer")
        validate_evidence(row.get("evidence_ids"), label)

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


def validate_reference_universe(
    rows: list[dict[str, Any]], id_field: str, label: str, *, run_id: str,
    audited_commit: str, snapshot_id: str, require_snapshot: bool = True,
) -> tuple[set[str], list[str]]:
    ids: set[str] = set()
    errors: list[str] = []
    if not rows:
        errors.append(f"{label} ist leer")
    for number, row in enumerate(rows, 1):
        item_id = row.get(id_field)
        row_label = f"{label} Zeile {number}"
        if not isinstance(item_id, str) or not item_id or item_id in ids:
            errors.append(f"{row_label}: {id_field} fehlt/doppelt")
        else:
            ids.add(item_id)
        if row.get("run_id") != run_id:
            errors.append(f"{row_label}: run_id falsch")
        commit = row.get("audited_commit", row.get("commit_sha"))
        if commit != audited_commit:
            errors.append(f"{row_label}: audited_commit/commit_sha falsch")
        if require_snapshot and row.get("snapshot_id") != snapshot_id:
            errors.append(f"{row_label}: snapshot_id falsch")
        if not require_snapshot and row.get("snapshot_id") not in (None, snapshot_id):
            errors.append(f"{row_label}: vorhandene snapshot_id falsch")
    return ids, errors


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
    args = parser.parse_args(argv)
    try:
        symbols, edges = enumerate_contract_universe(
            args.root, args.audited_commit, args.run_id, args.snapshot_id,
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
        reference_specs = (
            (args.feature_universe, "feature_id", "Featureuniversum", True),
            (args.runtime_universe, "evidence_id", "Runtimeuniversum", True),
            (args.reviewer_roster, "reviewer_id", "Reviewer-Roster", False),
            (args.evidence_universe, "evidence_id", "Evidence-Universum", True),
        )
        reference_ids: list[set[str]] = []
        for path, id_field, label, require_snapshot in reference_specs:
            ids, reference_errors = validate_reference_universe(
                _read_jsonl(path), id_field, label, run_id=args.run_id,
                audited_commit=resolve_commit(args.root.resolve(), args.audited_commit),
                snapshot_id=args.snapshot_id, require_snapshot=require_snapshot,
            )
            reference_ids.append(ids)
            errors.extend(reference_errors)
        errors.extend(validate_contracts(
            symbols, edges, _read_jsonl(args.symbol_states), _read_jsonl(args.edge_states),
            run_id=args.run_id, audited_commit=resolve_commit(args.root.resolve(), args.audited_commit),
            snapshot_id=args.snapshot_id,
            known_feature_ids=reference_ids[0], runtime_evidence_ids=reference_ids[1],
            reviewer_ids=reference_ids[2], evidence_ids=reference_ids[3],
        ))
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        return 0 if not errors else 2
    except (ContractError, OSError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
