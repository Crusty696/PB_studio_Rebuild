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
import hashlib
import io
import json
import re
import subprocess
import sys
import tokenize
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


DISPOSITIONS = {"feature", "support", "dead-candidate"}
NORMATIVE = re.compile(
    r"\b(muss|muessen|müssen|pflicht|required|must|shall|darf\s+nicht|forbidden)\b",
    re.IGNORECASE,
)
UI_TEXT_CALLS = {
    "QAction", "QPushButton", "QToolButton", "QCheckBox", "QRadioButton",
    "setText", "setTitle", "setWindowTitle", "addAction", "addButton",
    "addTab", "addMenu", "setPlaceholderText",
}
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
}
LIFECYCLE_NAMES = {
    "main": "entrypoint", "startup": "startup", "shutdown": "shutdown",
    "closeEvent": "shutdown", "showEvent": "startup", "timerEvent": "timer",
}


class ContractError(RuntimeError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
        "snapshot_id": snapshot_id,
    }


def enumerate_universes(
    root: Path, audited_commit: str, run_id: str, snapshot_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read Git blobs, never working-tree content."""
    root = root.resolve()
    commit = resolve_commit(root, audited_commit)
    requirements: list[dict[str, Any]] = []
    triggers: list[dict[str, Any]] = []
    for path in _tracked_paths(root, commit):
        suffix = PurePosixPath(path).suffix.lower()
        if suffix not in {".py", ".md", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json"}:
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

        if suffix in {".md", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json"}:
            for number, line in enumerate(text.splitlines(), 1):
                normalized = " ".join(line.strip().split())
                if normalized and NORMATIVE.search(normalized):
                    source_kind = "normative-text"
                    source_id = _locator_id("REQ", source_kind, path, number, 0, normalized)
                    requirements.append(_bound_row(
                        source_id=source_id, source_kind=source_kind, path=path,
                        line=number, column=0, detail=normalized, blob_sha=blob_sha,
                        run_id=run_id, audited_commit=commit, snapshot_id=snapshot_id,
                    ))
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
                        snapshot_id=snapshot_id,
                    ))
                if name in TRIGGER_CALLS:
                    kind = TRIGGER_CALLS[name]
                    detail = f"{name}:{label or ast.dump(node.func, include_attributes=False)}"
                    source_id = _locator_id("TRIG", kind, path, node.lineno, node.col_offset, detail)
                    triggers.append(_bound_row(
                        source_id=source_id, source_kind=kind, path=path,
                        line=node.lineno, column=node.col_offset, detail=detail,
                        blob_sha=blob_sha, run_id=run_id, audited_commit=commit,
                        snapshot_id=snapshot_id,
                    ))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name in LIFECYCLE_NAMES:
                    kind = LIFECYCLE_NAMES[node.name]
                    source_id = _locator_id("TRIG", kind, path, node.lineno, node.col_offset, node.name)
                    triggers.append(_bound_row(
                        source_id=source_id, source_kind=kind, path=path,
                        line=node.lineno, column=node.col_offset, detail=node.name,
                        blob_sha=blob_sha, run_id=run_id, audited_commit=commit,
                        snapshot_id=snapshot_id,
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
                            snapshot_id=snapshot_id,
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
    snapshot_id: str,
) -> list[str]:
    errors: list[str] = []
    universes = {"requirement": expected_requirements, "trigger": expected_triggers}
    expected: dict[tuple[str, str], dict[str, Any]] = {}
    digests = {kind: universe_digest(rows) for kind, rows in universes.items()}
    for kind, rows in universes.items():
        for row in rows:
            key = (kind, str(row.get("source_id", "")))
            if not key[1] or key in expected:
                errors.append(f"{kind}-Universum enthaelt fehlende/doppelte source_id")
            expected[key] = row
            if row.get("run_id") != run_id or row.get("audited_commit") != audited_commit or row.get("snapshot_id") != snapshot_id:
                errors.append(f"{kind}/{key[1]}: Universumsbindung manipuliert")

    seen: set[tuple[str, str]] = set()
    for number, row in enumerate(dispositions, 1):
        kind = str(row.get("universe", ""))
        source_id = str(row.get("source_id", ""))
        key = (kind, source_id)
        if key in seen:
            errors.append(f"Disposition Zeile {number}: doppelte ID {key!r}")
        seen.add(key)
        if key not in expected:
            errors.append(f"Disposition Zeile {number}: fremde ID {key!r}")
        if row.get("run_id") != run_id or row.get("audited_commit") != audited_commit or row.get("snapshot_id") != snapshot_id:
            errors.append(f"Disposition Zeile {number}: Run-/Commit-/Snapshotbindung falsch")
        if row.get("universe_sha256") != digests.get(kind):
            errors.append(f"Disposition Zeile {number}: Universumshash falsch")
        if row.get("disposition") not in DISPOSITIONS:
            errors.append(f"Disposition Zeile {number}: disposition ungueltig")
        for field in ("feature_id", "path_id", "evidence"):
            if not row.get(field):
                errors.append(f"Disposition Zeile {number}: {field} fehlt")
    if set(expected) != seen:
        errors.append(
            "Requirements-/Trigger-Exact-Set verletzt: "
            f"fehlend={sorted(set(expected) - seen)!r}, extra={sorted(seen - set(expected))!r}"
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
    args = parser.parse_args(argv)
    try:
        requirements, triggers = enumerate_universes(
            args.root, args.audited_commit, args.run_id, args.snapshot_id,
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
        errors.extend(validate_exact_set(
            requirements, triggers, _read_jsonl(args.dispositions), run_id=args.run_id,
            audited_commit=resolve_commit(args.root.resolve(), args.audited_commit),
            snapshot_id=args.snapshot_id,
        ))
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        return 0 if not errors else 2
    except (ContractError, OSError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
