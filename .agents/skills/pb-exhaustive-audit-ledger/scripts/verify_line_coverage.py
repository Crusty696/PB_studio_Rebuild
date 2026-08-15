from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path

from build_inventory import (
    _batch_blobs,
    _category,
    _discover_workspace_units,
    _generated_candidate,
    _snapshot_basis,
    _text_info,
)


def _linklike(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", lambda: False)
    return path.is_symlink() or bool(is_junction())


def _enumerate_scope(scope_root: Path) -> tuple[dict[str, Path], list[str]]:
    files: dict[str, Path] = {}
    errors: list[str] = []
    if _linklike(scope_root):
        return files, [f"Scopewurzel ist Symlink/Junction: {scope_root}"]
    try:
        def record_walk_error(exc: OSError) -> None:
            errors.append(f"Scopewurzel nicht vollstaendig lesbar: {exc}")

        for dirpath, dirnames, filenames in os.walk(
            scope_root, followlinks=False, onerror=record_walk_error,
        ):
            base = Path(dirpath)
            for name in list(dirnames):
                candidate = base / name
                if _linklike(candidate):
                    errors.append(f"Symlink/Junction im Scope verboten: {candidate}")
                    dirnames.remove(name)
            for name in filenames:
                candidate = base / name
                if _linklike(candidate):
                    errors.append(f"Symlink/Junction-Datei im Scope verboten: {candidate}")
                    continue
                relative = candidate.relative_to(scope_root).as_posix()
                files[relative] = candidate.absolute()
    except OSError as exc:
        errors.append(f"Scopewurzel nicht vollstaendig lesbar: {exc}")
    return files, errors


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root)


def _expected_unit_kinds(meta: dict) -> set[str]:
    kinds = {"metadata"}
    if meta.get("media") == "binary":
        kinds.add("binary-content")
    if meta.get("media") == "gitlink":
        kinds.add("gitlink-target")
    if meta.get("media") == "text" and int(meta.get("line_count") or 0) == 0:
        kinds.add("empty-file")
    if meta.get("generated_candidate"):
        kinds.add("generated-provenance")
    return kinds


def _reviewer_roster(
    roster_path: Path,
    snapshot: dict,
    run_id: str,
    audited_commit: str,
    snapshot_id: str,
) -> tuple[dict[str, dict], list[str]]:
    errors: list[str] = []
    if not roster_path.is_file():
        return {}, ["Reviewer-Roster fehlt"]
    roster_bytes = roster_path.read_bytes()
    if snapshot.get("reviewer_roster_sha256") != _sha(roster_bytes):
        errors.append("Reviewer-Roster-Hash stimmt nicht mit snapshot.json")
    try:
        rows = _jsonl(roster_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, errors + [f"Reviewer-Roster unlesbar: {exc}"]
    if not rows:
        errors.append("Reviewer-Roster ist leer")
    roster: dict[str, dict] = {}
    sessions: dict[str, str] = {}
    required_text = ("reviewer_id", "session_id", "worktree", "branch", "commit_sha")
    for index, row in enumerate(rows, 1):
        label = f"Reviewer-Roster Zeile {index}"
        if not isinstance(row, dict):
            errors.append(f"{label}: JSON-Objekt erforderlich")
            continue
        if row.get("run_id") != run_id:
            errors.append(f"{label}: run_id falsch")
        if row.get("audited_commit") != audited_commit:
            errors.append(f"{label}: audited_commit falsch")
        if row.get("snapshot_id") != snapshot_id:
            errors.append(f"{label}: snapshot_id falsch")
        missing = [
            field
            for field in required_text
            if not isinstance(row.get(field), str) or not row[field].strip()
        ]
        if missing:
            errors.append(f"{label}: Pflichtfelder fehlen/ungueltig: {missing}")
        reviewer_id = str(row.get("reviewer_id", ""))
        session_id = str(row.get("session_id", ""))
        if reviewer_id in roster:
            errors.append(f"{label}: doppelte reviewer_id {reviewer_id!r}")
        else:
            roster[reviewer_id] = row
        if session_id in sessions:
            errors.append(
                f"{label}: session_id {session_id!r} bereits Reviewer {sessions[session_id]!r} zugeordnet"
            )
        else:
            sessions[session_id] = reviewer_id
        if row.get("commit_sha") != audited_commit:
            errors.append(f"{label}: commit_sha ist nicht audited_commit")
        worktree = Path(str(row.get("worktree", "")))
        if not worktree.is_absolute():
            errors.append(f"{label}: worktree muss absoluter Pfad sein")
        lineage = row.get("ancestor_session_ids")
        if not isinstance(lineage, list) or any(not isinstance(item, str) or not item for item in lineage):
            errors.append(f"{label}: ancestor_session_ids muss Liste nichtleerer Session-IDs sein")
            lineage = []
        if len(lineage) != len(set(lineage)):
            errors.append(f"{label}: ancestor_session_ids enthaelt Duplikate")
        if session_id and session_id in lineage:
            errors.append(f"{label}: eigene session_id darf nicht in ancestor_session_ids stehen")
        parent_id = row.get("parent_session_id")
        if lineage:
            if parent_id != lineage[-1]:
                errors.append(f"{label}: parent_session_id muss letztem ancestor_session_ids-Eintrag entsprechen")
        elif parent_id is not None:
            errors.append(f"{label}: Root-Reviewer braucht parent_session_id null")
        claims = row.get("claims")
        if (
            not isinstance(claims, list)
            or not claims
            or any(not isinstance(claim, str) or not claim.strip() for claim in claims)
            or len(claims) != len(set(claims))
        ):
            errors.append(f"{label}: claims muss eindeutige nichtleere String-Liste sein")
        elif any(
            claim.startswith(("/", "\\"))
            or ".." in Path(claim.replace("\\", "/")).parts
            for claim in claims
        ):
            errors.append(f"{label}: claims muessen relative Repo-Pfade/Globs sein")
        review_scope = row.get("review_scope")
        if (
            not isinstance(review_scope, list) or not review_scope
            or any(not isinstance(scope, str) or not scope.strip() for scope in review_scope)
            or len(review_scope) != len(set(review_scope))
        ):
            errors.append(f"{label}: review_scope muss eindeutige nichtleere String-Liste sein")
    if rows:
        errors.append("Reviewer-Live-Enrollment-Harness fehlt; Rosterdatei allein ist keine Identitaetsattestierung")
    return roster, errors


def _identity_closure(reviewer: dict) -> set[str]:
    return {str(reviewer.get("session_id", "")), *map(str, reviewer.get("ancestor_session_ids") or [])} - {""}


def _reviewer_claims_path(reviewer: dict, path: str) -> bool:
    normalized = path.replace("\\", "/")
    return any(
        fnmatch.fnmatchcase(normalized, str(claim).replace("\\", "/"))
        for claim in reviewer.get("review_scope") or []
    )


def _independent_reviewers(
    reviewer_ids_a: set[str],
    reviewer_ids_b: set[str],
    roster: dict[str, dict],
) -> bool:
    if reviewer_ids_a & reviewer_ids_b:
        return False
    rows_a = [roster[reviewer] for reviewer in reviewer_ids_a if reviewer in roster]
    rows_b = [roster[reviewer] for reviewer in reviewer_ids_b if reviewer in roster]
    return not any(
        a.get("session_id") in (b.get("ancestor_session_ids") or [])
        or b.get("session_id") in (a.get("ancestor_session_ids") or [])
        for a in rows_a for b in rows_b
    )


def verify(
    root: Path,
    snapshot_path: Path,
    inventory_path: Path,
    pass_a: Path,
    pass_b: Path,
    non_line_units: Path,
    exclusions_path: Path,
    workspace_units_path: Path,
    reviewer_roster_path: Path,
) -> list[str]:
    inventory = _jsonl(inventory_path)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    exclusion_rows = _jsonl(exclusions_path)
    exclusions = {row.get("exclusion_id"): row for row in exclusion_rows}
    workspace_units = _jsonl(workspace_units_path)
    errors: list[str] = []
    run_id = str(snapshot.get("run_id", ""))
    if not run_id:
        errors.append("snapshot.json run_id fehlt")
    paths = [row.get("path") for row in inventory]
    if not inventory:
        errors.append("Inventory ist leer")
    if len(paths) != len(set(paths)):
        errors.append("Inventory enthaelt doppelte Pfade")
    if len(exclusions) != len(exclusion_rows):
        errors.append("Exklusionsledger enthaelt fehlende/doppelte exclusion_id")
    inv = {row["path"]: row for row in inventory if row.get("path")}
    rows_without_snapshot = [
        {key: value for key, value in row.items() if key != "snapshot_id"}
        for row in inventory
    ]
    computed_snapshot_id = _snapshot_basis(rows_without_snapshot, workspace_units)
    snapshot_ids = {row.get("snapshot_id") for row in inventory}
    if snapshot_ids != {computed_snapshot_id}:
        errors.append("Inventory-snapshot_id stimmt nicht mit neu berechnetem Inhalt")
    if snapshot.get("snapshot_id") != computed_snapshot_id:
        errors.append("snapshot.json stimmt nicht mit Inventory")
    workspace_basis = json.dumps(
        workspace_units, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    if snapshot.get("workspace_unit_count") != len(workspace_units):
        errors.append("snapshot.json workspace_unit_count stimmt nicht")
    if snapshot.get("workspace_units_sha256") != hashlib.sha256(workspace_basis).hexdigest():
        errors.append("snapshot.json workspace_units_sha256 stimmt nicht")
    head = _run(root, "rev-parse", "HEAD").decode().strip()
    status = _run(root, "status", "--porcelain=v2", "--untracked-files=all").decode("utf-8", "replace")
    if status.strip():
        errors.append("Current Working Tree ist nicht clean")
    if snapshot.get("clean") is not True:
        errors.append("snapshot.json clean ist nicht true")
    audited_commit = str(snapshot.get("audited_commit", ""))
    resolved_audited_commit = ""
    if not audited_commit:
        errors.append("snapshot.json audited_commit fehlt")
    elif not re.fullmatch(r"[0-9a-f]{40}", audited_commit):
        errors.append("audited_commit muss 40-stellige lowercase Git-SHA sein")
    else:
        try:
            resolved_audited_commit = _run(
                root, "rev-parse", "--verify", f"{audited_commit}^{{commit}}"
            ).decode().strip()
        except subprocess.CalledProcessError:
            resolved_audited_commit = ""
            errors.append(f"audited_commit existiert nicht als Commit: {audited_commit}")
        if resolved_audited_commit and resolved_audited_commit != audited_commit:
            errors.append("audited_commit muss vollstaendige kanonische Commit-SHA sein")
    if snapshot.get("commit_sha") != audited_commit or any(
        row.get("commit_sha") != audited_commit for row in inventory
    ):
        errors.append("Snapshot/Inventory commit_sha stimmt nicht mit audited_commit")
    reviewer_roster, roster_errors = _reviewer_roster(
        reviewer_roster_path, snapshot, run_id, audited_commit, computed_snapshot_id,
    )
    errors.extend(roster_errors)
    if any(row.get("run_id") != run_id for row in inventory + workspace_units):
        errors.append("Inventory/Workspace run_id weicht vom Snapshot ab")
    summary_expected = {
        "file_count": len(inventory),
        "text_file_count": sum(row.get("media") == "text" for row in inventory),
        "binary_file_count": sum(row.get("media") == "binary" for row in inventory),
        "gitlink_count": sum(row.get("media") == "gitlink" for row in inventory),
        "text_line_count": sum(int(row.get("line_count") or 0) for row in inventory),
    }
    for field, expected in summary_expected.items():
        if snapshot.get(field) != expected:
            errors.append(f"snapshot.json {field} stimmt nicht: {snapshot.get(field)} != {expected}")
    current_tree: dict[str, tuple[str, str, str]] = {}
    treeish = resolved_audited_commit or head
    for raw in _run(root, "ls-tree", "-r", "-z", "--full-tree", treeish).split(b"\x00"):
        if raw:
            meta, path_raw = raw.split(b"\t", 1)
            mode, object_type, object_id = meta.decode().split()
            current_tree[path_raw.decode("utf-8")] = (mode, object_type, object_id)
    current_blobs = _batch_blobs(
        root, [object_id for mode, _object_type, object_id in current_tree.values() if mode != "160000"]
    )
    git_inventory_paths = {path for path, row in inv.items() if row.get("origin") == "git"}
    if git_inventory_paths != set(current_tree):
        missing = sorted(set(current_tree) - git_inventory_paths)
        extra = sorted(git_inventory_paths - set(current_tree))
        errors.append(
            f"Inventory/audited_commit-Pfadmenge driftet; missing={missing[:5]} extra={extra[:5]}"
        )
    current_workspace = _discover_workspace_units(root, run_id)
    current_discovered = {
        (row.get("scope"), row.get("path")): row for row in current_workspace
    }
    stored_discovered = {
        (row.get("scope"), row.get("path")): row for row in workspace_units
        if row.get("scope") in {"untracked", "ignored-root"}
    }
    if set(current_discovered) != set(stored_discovered):
        errors.append("Current untracked/ignored Scopewurzeln weichen vom Snapshot ab")
    for key in set(current_discovered) & set(stored_discovered):
        for field in ("unit_type", "bytes", "sha256"):
            if current_discovered[key].get(field) != stored_discovered[key].get(field):
                errors.append(f"Scope-Discovery {key}: {field} driftet")

    global_declared_sources: dict[str, str] = {}
    included_scope_ids: dict[str, str] = {}
    for unit in workspace_units:
        decision = unit.get("decision")
        label = f"scope:{unit.get('scope')}:{unit.get('path')}"
        if decision == "included-expanded":
            manifest = Path(str(unit.get("expanded_manifest", "")))
            if not manifest.is_file() or _sha(manifest.read_bytes()) != unit.get("manifest_sha256"):
                errors.append(f"{label}: Expansionmanifest fehlt oder Hash falsch")
                continue
            scope_id = unit.get("scope_id")
            scope_root = Path(str(unit.get("scope_root", ""))).resolve()
            if not scope_id or not scope_root.is_dir():
                errors.append(f"{label}: scope_id/scope_root fehlt oder ungueltig")
                continue
            prior_unit = included_scope_ids.get(str(scope_id))
            if prior_unit is not None:
                errors.append(f"{label}: doppelte scope_id {scope_id}; zuerst {prior_unit}")
            else:
                included_scope_ids[str(scope_id)] = label
            manifest_rows = _jsonl(manifest)
            if not manifest_rows:
                errors.append(f"{label}: Expansionmanifest ist leer")
                continue
            manifest_paths = {str(row.get("path")) for row in manifest_rows}
            inventory_paths = {
                path for path, row in inv.items()
                if row.get("origin") == "scope" and row.get("scope_id") == scope_id
            }
            if manifest_paths != inventory_paths:
                errors.append(f"{label}: Expansionmanifest und Inventory-Pfadmenge weichen ab")
            manifest_by_path = {str(row.get("path")): row for row in manifest_rows}
            if len(manifest_by_path) != len(manifest_rows):
                errors.append(f"{label}: Expansionmanifest enthaelt doppelte/fehlende logische Pfade")
            compare_fields = (
                "relative_path", "sha256", "bytes", "media", "encoding", "eol",
                "line_count", "category", "generated_candidate", "lfs_pointer",
                "disposition", "exclusion_id", "git_mode", "git_object_type", "git_blob",
            )
            for logical_path, manifest_row in manifest_by_path.items():
                inventory_row = inv.get(logical_path)
                if inventory_row is None:
                    continue
                if Path(str(manifest_row.get("source_path", ""))).resolve() != Path(
                    str(inventory_row.get("source_path", ""))
                ).resolve():
                    errors.append(f"{label}:{logical_path}: Manifest-/Inventory-source_path weicht ab")
                for field in compare_fields:
                    if manifest_row.get(field) != inventory_row.get(field):
                        errors.append(f"{label}:{logical_path}: Manifest-/Inventory-{field} weicht ab")
                if (
                    manifest_row.get("git_mode") != "external"
                    or manifest_row.get("git_object_type") != "file"
                    or manifest_row.get("git_blob") is not None
                ):
                    errors.append(f"{label}:{logical_path}: Scope-Dateimodus muss external/file/null sein")
            actual_files, traversal_errors = _enumerate_scope(scope_root)
            errors.extend(f"{label}: {error}" for error in traversal_errors)
            declared_files: dict[str, Path] = {}
            declared_sources: set[str] = set()
            for manifest_row in manifest_rows:
                relative_raw = str(manifest_row.get("relative_path", ""))
                relative_path = Path(relative_raw)
                if (
                    not relative_raw or relative_path.is_absolute()
                    or ".." in relative_path.parts
                    or relative_path.as_posix() != relative_raw.replace("\\", "/")
                ):
                    errors.append(f"{label}: invalid relative_path: {relative_raw!r}")
                    continue
                source = Path(str(manifest_row.get("source_path", ""))).resolve()
                expected_source = (scope_root / relative_path).resolve()
                if os.path.normcase(str(source)) != os.path.normcase(str(expected_source)):
                    errors.append(f"{label}: relative_path/source_path widersprechen sich: {relative_raw}")
                normalized_source = os.path.normcase(str(source))
                if normalized_source in declared_sources:
                    errors.append(f"{label}: doppelte source_path: {source}")
                declared_sources.add(normalized_source)
                prior_scope = global_declared_sources.get(normalized_source)
                if prior_scope is not None:
                    errors.append(
                        f"{label}: source_path bereits deklariert in Scope {prior_scope}: {source}"
                    )
                global_declared_sources[normalized_source] = str(unit.get("scope_id"))
                declared_files[relative_path.as_posix()] = source
            if set(actual_files) != set(declared_files):
                errors.append(f"{label}: Scopewurzel nicht vollstaendig im Expansionmanifest")
            if unit.get("scope") == "ignored-root":
                expected_root = (root / str(unit.get("path", ""))).resolve()
                if scope_root != expected_root:
                    errors.append(f"{label}: ignored scope_root weicht vom entdeckten Pfad ab")
        elif decision == "excluded-approved":
            if not all(unit.get(key) for key in ("approved_by", "approved_at", "decision_ref", "reason")):
                errors.append(f"{label}: Scope-Exklusionsgenehmigung unvollstaendig")
        else:
            errors.append(f"{label}: Scopeentscheidung ungeklaert/ungueltig: {decision!r}")
    included_scope_ids = {
        unit.get("scope_id") for unit in workspace_units
        if unit.get("decision") == "included-expanded"
    }
    inventory_scope_ids = {
        row.get("scope_id") for row in inventory if row.get("origin") == "scope"
    }
    if included_scope_ids != inventory_scope_ids:
        errors.append("Included Scope-IDs und Scope-Inventory stimmen nicht ueberein")

    used_exclusions: set[str] = set()
    for row in inventory:
        path = row.get("path")
        disposition = row.get("disposition")
        if disposition not in {"direct-review", "excluded-approved"}:
            errors.append(f"{path}: ungueltige disposition {disposition!r}")
        if disposition == "excluded-approved":
            exclusion_id = row.get("exclusion_id")
            exclusion = exclusions.get(exclusion_id)
            used_exclusions.add(str(exclusion_id))
            if not exclusion or exclusion.get("path") != path:
                errors.append(f"{path}: Exklusion fehlt oder passt nicht")
            elif not all(exclusion.get(key) for key in ("approved_by", "approved_at", "decision_ref", "reason")):
                errors.append(f"{path}: Exklusionsgenehmigung unvollstaendig")
            elif exclusion.get("run_id") != run_id:
                errors.append(f"{path}: Exklusions-run_id falsch")
        if row.get("origin") == "scope":
            source = Path(str(row.get("source_path", "")))
            if not source.is_file() or _linklike(source):
                errors.append(f"{path}: Scope-Datei fehlt")
                continue
            current_data = source.read_bytes()
            current_mode = "external"
            if (
                row.get("git_mode") != "external"
                or row.get("git_object_type") != "file"
                or row.get("git_blob") is not None
            ):
                errors.append(f"{path}: Scope-Dateimodus muss external/file/null sein")
        else:
            blob = row.get("git_blob")
            current_entry = current_tree.get(str(path))
            if current_entry is None:
                errors.append(f"{path}: fehlt in audited_commit")
                continue
            current_mode, current_object_type, current_blob = current_entry
            if row.get("git_mode") != current_mode or row.get("git_object_type") != current_object_type:
                errors.append(f"{path}: Git-Mode/Objekttyp manipuliert oder driftet")
            if current_blob != blob:
                errors.append(f"{path}: Git-Blob/Gitlink-Target driftet")
            current_data = b"" if current_mode == "160000" else current_blobs[current_blob]
        if _sha(current_data) != row.get("sha256"):
            errors.append(f"{path}: audited_commit-Inhalt driftet")
        if current_mode == "160000":
            derived = {
                "media": "gitlink", "encoding": None, "line_count": None,
                "eol": None, "bytes": 0, "generated_candidate": False,
                "lfs_pointer": False,
            }
        else:
            media, encoding, line_count, eol = _text_info(current_data)
            derived = {
                "media": media, "encoding": encoding, "line_count": line_count,
                "eol": eol, "bytes": len(current_data),
                "generated_candidate": _generated_candidate(str(path), current_data),
                "lfs_pointer": current_data.startswith(b"version https://git-lfs.github.com/spec/v1"),
            }
        derived["category"] = _category(str(path))
        for field, expected in derived.items():
            if row.get(field) != expected:
                errors.append(f"{path}: abgeleitetes Feld {field} manipuliert/driftet")
    if {str(key) for key in exclusions} != used_exclusions:
        errors.append("Exklusionsledger enthaelt unbenutzte oder unreferenzierte Eintraege")

    reviewers: dict[tuple[str, str], set[str]] = defaultdict(set)
    for label, ledger_path in (("A", pass_a), ("B", pass_b)):
        ranges: dict[str, list[dict]] = defaultdict(list)
        for row in _jsonl(ledger_path):
            path = row.get("path")
            if row.get("pass") != label:
                errors.append(f"{ledger_path}: falscher Pass {row.get('pass')} statt {label}")
            if path not in inv:
                errors.append(f"{ledger_path}: unbekannter Pfad {path}")
                continue
            if inv[path].get("disposition") != "direct-review" or inv[path].get("media") != "text":
                errors.append(f"{label}:{path}: Range fuer nicht direkt gepruefte Textdatei")
            if row.get("snapshot_id") != computed_snapshot_id:
                errors.append(f"{label}:{path}: falsche snapshot_id")
            if row.get("run_id") != run_id:
                errors.append(f"{label}:{path}: falsche run_id")
            ranges[path].append(row)
            reviewer_id = str(row.get("reviewer_id", ""))
            reviewers[(label, path)].add(reviewer_id)
            if reviewer_id not in reviewer_roster:
                errors.append(f"{label}:{path}: reviewer_id fehlt im Reviewer-Roster")
            elif not _reviewer_claims_path(reviewer_roster[reviewer_id], str(path)):
                errors.append(f"{label}:{path}: Reviewer-Roster-Claims decken Pfad nicht ab")
            if row.get("file_sha256") != inv[path]["sha256"]:
                errors.append(f"{label}:{path}: Ledger-SHA != Inventory-SHA")
            checks = row.get("checks") or {}
            required = {"semantics", "errors", "state", "threading", "io_db_gpu", "wiring"}
            if any(checks.get(key) != "done" for key in required):
                errors.append(f"{label}:{path}:{row.get('start_line')}-{row.get('end_line')}: Checks unvollstaendig")
            if row.get("verdict") != "reviewed" or not row.get("signed_at") or not row.get("reviewer_id"):
                errors.append(f"{label}:{path}:{row.get('start_line')}-{row.get('end_line')}: Signoff unvollstaendig")

        for path, meta in inv.items():
            if meta["media"] != "text" or meta["disposition"] != "direct-review":
                continue
            expected_end = int(meta["line_count"] or 0)
            rows = sorted(ranges.get(path, []), key=lambda r: (int(r["start_line"]), int(r["end_line"])))
            if expected_end == 0:
                if rows:
                    errors.append(f"{label}:{path}: leere Datei darf keine Zeilenrange haben")
                continue
            if expected_end <= 200 and len(rows) != 1:
                errors.append(f"{label}:{path}: Datei bis 200 Zeilen braucht genau eine Range")
            cursor = 1
            for index, row in enumerate(rows):
                start, end = int(row["start_line"]), int(row["end_line"])
                size = end - start + 1
                if start != cursor:
                    errors.append(f"{label}:{path}: erwartet Start {cursor}, erhalten {start}")
                if end < start or end > expected_end:
                    errors.append(f"{label}:{path}: ungueltige Range {start}-{end}, EOF {expected_end}")
                if size > 200 or (size < 100 and index != len(rows) - 1 and expected_end > 200):
                    errors.append(f"{label}:{path}: Rangegroesse {size} ausserhalb 100-200")
                cursor = end + 1
            if cursor != expected_end + 1:
                errors.append(f"{label}:{path}: Abdeckung endet {cursor - 1}, EOF {expected_end}")

    for path, meta in inv.items():
        if meta["media"] != "text" or meta["disposition"] != "direct-review" or not meta["line_count"]:
            continue
        if not _independent_reviewers(
            reviewers[("A", path)], reviewers[("B", path)], reviewer_roster,
        ):
            errors.append(f"{path}: Pass A/B haben gleiche Reviewer-Identity/Lineage")
        if len(reviewers[("A", path)]) != 1 or len(reviewers[("B", path)]) != 1:
            errors.append(f"{path}: pro Pass genau ein Reviewer erforderlich")

    unit_reviewers: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    unit_counts: dict[tuple[str, str, str], int] = defaultdict(int)
    for row in _jsonl(non_line_units):
        label, path, kind = row.get("pass"), row.get("path"), row.get("unit_kind")
        if label not in {"A", "B"} or path not in inv:
            errors.append(f"non_line_units:{path}: Pass/Pfad ungueltig")
            continue
        if row.get("run_id") != run_id:
            errors.append(f"non_line_units:{label}:{path}:{kind}: falsche run_id")
        meta = inv[path]
        if meta.get("disposition") != "direct-review" or kind not in _expected_unit_kinds(meta):
            errors.append(f"non_line_units:{path}:{kind}: unerwartete Einheit")
        if row.get("snapshot_id") != computed_snapshot_id or row.get("file_sha256") != meta.get("sha256"):
            errors.append(f"non_line_units:{label}:{path}:{kind}: Snapshot-/Datei-SHA falsch")
        checks = row.get("checks") or {}
        required = {"identity", "format", "provenance", "consumer", "integrity"}
        if any(checks.get(key) != "done" for key in required):
            errors.append(f"non_line_units:{label}:{path}:{kind}: Checks unvollstaendig")
        if row.get("verdict") != "reviewed" or not row.get("signed_at") or not row.get("reviewer_id"):
            errors.append(f"non_line_units:{label}:{path}:{kind}: Signoff unvollstaendig")
        reviewer_id = str(row.get("reviewer_id", ""))
        unit_reviewers[(label, path, kind)].add(reviewer_id)
        if reviewer_id not in reviewer_roster:
            errors.append(f"non_line_units:{label}:{path}:{kind}: reviewer_id fehlt im Reviewer-Roster")
        elif not _reviewer_claims_path(reviewer_roster[reviewer_id], str(path)):
            errors.append(
                f"non_line_units:{label}:{path}:{kind}: "
                "Reviewer-Roster-Claims decken Pfad nicht ab"
            )
        unit_counts[(label, path, kind)] += 1

    for path, meta in inv.items():
        if meta.get("disposition") != "direct-review":
            continue
        for kind in _expected_unit_kinds(meta):
            if unit_counts[("A", path, kind)] != 1 or unit_counts[("B", path, kind)] != 1:
                errors.append(f"{path}:{kind}: genau eine Einheit pro Pass erforderlich")
            if not _independent_reviewers(
                unit_reviewers[("A", path, kind)],
                unit_reviewers[("B", path, kind)],
                reviewer_roster,
            ):
                errors.append(f"{path}:{kind}: Pass A/B haben gleiche Reviewer-Identity/Lineage")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--pass-a", type=Path, required=True)
    parser.add_argument("--pass-b", type=Path, required=True)
    parser.add_argument("--non-line-units", type=Path, required=True)
    parser.add_argument("--exclusions", type=Path, required=True)
    parser.add_argument("--workspace-units", type=Path, required=True)
    parser.add_argument("--reviewer-roster", type=Path, required=True)
    args = parser.parse_args()
    errors = verify(
        args.root.resolve(), args.snapshot, args.inventory, args.pass_a,
        args.pass_b, args.non_line_units, args.exclusions, args.workspace_units,
        args.reviewer_roster,
    )
    print(json.dumps({"ok": not errors, "error_count": len(errors), "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
