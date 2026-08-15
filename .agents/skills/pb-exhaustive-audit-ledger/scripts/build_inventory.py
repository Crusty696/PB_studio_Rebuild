from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def _run(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root)


def _category(path: str) -> str:
    top = path.split("/", 1)[0]
    if top in {"services", "ui", "database", "workers", "agents"} or path == "main.py":
        return "runtime_product"
    if top in {"tests", "Agent_Tests"} or "test" in Path(path).stem.lower():
        return "tests"
    if top == "docs" or path.endswith(".md"):
        return "docs_governance_evidence"
    if top == "vendor":
        return "vendor"
    if top in {"scripts", "tools", "installer", "pb_packaging", "resources", "translations"}:
        return "ops_build_assets"
    if top == "knowledge":
        return "knowledge"
    return "repo_dependency_config"


def _text_info(data: bytes) -> tuple[str, str | None, int | None, str | None]:
    if b"\x00" in data:
        return "binary", None, None, None
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return "binary", None, None, None
    lines = len(text.splitlines())
    crlf = data.count(b"\r\n")
    lf = data.count(b"\n") - crlf
    eol = "mixed" if crlf and lf else "crlf" if crlf else "lf" if lf else "none"
    return "text", "utf-8", lines, eol


def _generated_candidate(path: str, data: bytes) -> bool:
    lowered = path.lower().replace("\\", "/")
    if any(part in lowered.split("/") for part in ("generated", "autogen")):
        return True
    prefix = data[:4096].lower()
    return b"generated file" in prefix or b"do not edit" in prefix


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _snapshot_basis(rows: list[dict], workspace_units: list[dict]) -> str:
    payload = {"files": rows, "workspace_units": workspace_units}
    basis = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(basis).hexdigest()


def _batch_blobs(root: Path, blob_ids: list[str]) -> dict[str, bytes]:
    unique = sorted(set(blob_ids))
    process = subprocess.Popen(
        ["git", "cat-file", "--batch"], cwd=root,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    stdout, stderr = process.communicate(
        ("".join(f"{blob}\n" for blob in unique)).encode("ascii")
    )
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, process.args, stdout, stderr)
    result: dict[str, bytes] = {}
    cursor = 0
    for expected in unique:
        header_end = stdout.find(b"\n", cursor)
        if header_end < 0:
            raise RuntimeError(f"git cat-file --batch: Header fehlt fuer {expected}")
        actual, object_type, size_raw = stdout[cursor:header_end].decode("ascii").split()
        if actual != expected or object_type != "blob":
            raise RuntimeError(f"git cat-file --batch: unerwartet {actual} {object_type}")
        size = int(size_raw)
        data_start = header_end + 1
        data_end = data_start + size
        result[expected] = stdout[data_start:data_end]
        cursor = data_end + 1
    return result


def _discover_workspace_units(root: Path, run_id: str) -> list[dict]:
    units = []
    scoped = _run(
        root, "status", "--porcelain=v2", "--ignored=matching",
        "--untracked-files=all", "-z",
    ).split(b"\x00")
    for raw in scoped:
        if not raw.startswith((b"? ", b"! ")):
            continue
        kind = "untracked" if raw.startswith(b"? ") else "ignored-root"
        path = raw[2:].decode("utf-8")
        target = root / path
        units.append({
            "run_id": run_id,
            "scope": kind,
            "path": path.replace("\\", "/"),
            "unit_type": "file" if target.is_file() else "directory-root",
            "bytes": target.stat().st_size if target.is_file() else None,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else None,
            "decision": "unresolved",
        })
    units.sort(key=lambda row: (row["scope"], row["path"]))
    return units


def build(
    root: Path,
    output: Path,
    scope_decisions: Path | None = None,
    run_id: str = "",
) -> dict[str, object]:
    root = root.resolve()
    if not run_id.strip():
        raise RuntimeError("run_id fehlt")
    output = output.resolve()
    try:
        output.relative_to(root)
    except ValueError:
        pass
    else:
        raise RuntimeError("Evidence-Ausgabe innerhalb Produkt-Worktree ist verboten")
    output.mkdir(parents=True, exist_ok=True)
    head = _run(root, "rev-parse", "HEAD").decode().strip()
    status = _run(root, "status", "--porcelain=v2", "--untracked-files=all").decode("utf-8", "replace")

    workspace_units = _discover_workspace_units(root, run_id)
    if scope_decisions is not None:
        decisions = _read_jsonl(scope_decisions)
        decision_map = {(row.get("scope"), row.get("path")): row for row in decisions}
        for unit in workspace_units:
            decision = decision_map.pop((unit["scope"], unit["path"]), None)
            if decision:
                unit.update(decision)
        for decision in decision_map.values():
            if decision.get("scope") == "external":
                workspace_units.append(decision)
    for unit in workspace_units:
        unit["run_id"] = run_id
    workspace_units.sort(key=lambda row: (str(row.get("scope")), str(row.get("path"))))
    _write_jsonl(output / "workspace_units.jsonl", workspace_units)

    tree = _run(root, "ls-tree", "-r", "-z", "--full-tree", "HEAD").split(b"\x00")
    tree_entries = []
    for raw in tree:
        if raw:
            meta, path_raw = raw.split(b"\t", 1)
            mode, object_type, blob = meta.decode().split()
            tree_entries.append((mode, object_type, blob, path_raw.decode("utf-8")))
    blob_data = _batch_blobs(
        root, [blob for mode, _object_type, blob, _path in tree_entries if mode != "160000"]
    )
    rows = []
    for mode, object_type, blob, path in tree_entries:
        if mode == "160000":
            data = b""
            media, encoding, line_count, eol = "gitlink", None, None, None
        else:
            data = blob_data[blob]
            media, encoding, line_count, eol = _text_info(data)
        rows.append({
            "run_id": run_id,
            "origin": "git",
            "commit_sha": head,
            "path": path.replace("\\", "/"),
            "git_mode": mode,
            "git_object_type": object_type,
            "git_blob": blob,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "media": media,
            "encoding": encoding,
            "eol": eol,
            "line_count": line_count,
            "category": _category(path),
            "generated_candidate": _generated_candidate(path, data),
            "lfs_pointer": data.startswith(b"version https://git-lfs.github.com/spec/v1"),
            "disposition": "direct-review",
            "exclusion_id": None,
        })

    scope_errors = []
    for unit in workspace_units:
        if unit.get("decision") == "included-expanded":
            manifest_path = Path(str(unit.get("expanded_manifest", "")))
            if not manifest_path.is_file():
                scope_errors.append(f"Expansionmanifest fehlt: {unit.get('path')}")
                continue
            manifest_data = manifest_path.read_bytes()
            if hashlib.sha256(manifest_data).hexdigest() != unit.get("manifest_sha256"):
                scope_errors.append(f"Expansionmanifest-Hash falsch: {unit.get('path')}")
                continue
            for expanded in _read_jsonl(manifest_path):
                expanded = dict(expanded)
                expanded["run_id"] = run_id
                expanded["origin"] = "scope"
                expanded["scope_id"] = unit.get("scope_id")
                expanded["commit_sha"] = head
                rows.append(expanded)
            if unit.get("scope") == "ignored-root":
                expected_root = (root / str(unit.get("path", ""))).resolve()
                if Path(str(unit.get("scope_root", ""))).resolve() != expected_root:
                    scope_errors.append(f"Ignored scope_root weicht vom entdeckten Pfad ab: {unit.get('path')}")
        elif unit.get("decision") != "excluded-approved":
            scope_errors.append(f"Scopeentscheidung offen/ungueltig: {unit.get('scope')}:{unit.get('path')}")

    snapshot_id = _snapshot_basis(rows, workspace_units)
    for row in rows:
        row["snapshot_id"] = snapshot_id
    _write_jsonl(output / "files.jsonl", rows)
    summary = {
        "run_id": run_id,
        "snapshot_id": snapshot_id,
        "commit_sha": head,
        "git_status_porcelain_v2": status.splitlines(),
        "clean": not bool(status.strip()),
        "file_count": len(rows),
        "text_file_count": sum(r["media"] == "text" for r in rows),
        "binary_file_count": sum(r["media"] == "binary" for r in rows),
        "gitlink_count": sum(r["media"] == "gitlink" for r in rows),
        "text_line_count": sum((r["line_count"] or 0) for r in rows),
        "workspace_unit_count": len(workspace_units),
        "workspace_units_sha256": hashlib.sha256(
            json.dumps(workspace_units, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }
    (output / "snapshot.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not summary["clean"] or scope_errors:
        raise RuntimeError(
            "; ".join(
                (["Working tree ist nicht clean"] if not summary["clean"] else [])
                + scope_errors
                + ["Snapshot-Artefakte nur zur Scope-Klaerung, nicht signierbar"]
            )
        )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scope-decisions", type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(
            build(args.root, args.output, args.scope_decisions, args.run_id),
            ensure_ascii=False, indent=2,
        ))
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
