"""Live-enroll reviewer identities and verify immutable audit receipts.

Enrollment is the only operation which reads the mutable agent registry and
worktree. Final verification deliberately uses the hash-bound receipt only, so
released sessions and removed worktrees do not invalidate completed reviews.

Trust boundary: receipts prove that this tool observed local registry/Git state.
They are hashes, not signatures. An actor able to replace validator, roster and
receipt bytes together remains outside this local trust model; dual independent
signoff and a fixed tooling commit remain required.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import agent_session

ISSUER = "PB_STUDIO_AUDIT_REVIEWER_ROSTER_V1"
SCHEMA_VERSION = 1
LOCK_TIMEOUT_SECONDS = 10.0


class EnrollmentError(RuntimeError):
    """Live identity cannot be enrolled without weakening a gate."""


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run(cwd: Path, *args: str) -> str:
    try:
        return subprocess.run(
            list(args), cwd=cwd, check=True, capture_output=True, text=True,
            timeout=30,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise EnrollmentError(f"Command fehlgeschlagen: {' '.join(args)}: {exc}") from exc


def _resolve_commit(root: Path, commit: str) -> str:
    if len(commit) != 40 or any(ch not in "0123456789abcdefABCDEF" for ch in commit):
        raise EnrollmentError("audited_commit muss volle 40-Zeichen-Git-SHA sein")
    resolved = _run(root, "git", "rev-parse", "--verify", f"{commit}^{{commit}}")
    if resolved.lower() != commit.lower():
        raise EnrollmentError("audited_commit loest nicht auf sich selbst auf")
    return resolved.lower()


def _norm_path(path: str | Path) -> str:
    return os.path.normcase(str(Path(path).resolve()))


def _worktree_paths(root: Path) -> set[str]:
    paths: set[str] = set()
    for line in _run(root, "git", "worktree", "list", "--porcelain").splitlines():
        if line.startswith("worktree "):
            paths.add(_norm_path(line.removeprefix("worktree ")))
    return paths


def _common_dir(cwd: Path) -> str:
    raw = _run(cwd, "git", "rev-parse", "--git-common-dir")
    path = Path(raw)
    if not path.is_absolute():
        path = cwd / path
    return _norm_path(path)


def _clean_git_state(worktree: Path) -> dict[str, Any]:
    head = _run(worktree, "git", "rev-parse", "HEAD").lower()
    branch = _run(worktree, "git", "rev-parse", "--abbrev-ref", "HEAD")
    dirty = _run(worktree, "git", "status", "--porcelain", "--untracked-files=all")
    return {
        "path": str(worktree.resolve()),
        "common_dir": _common_dir(worktree),
        "branch": branch,
        "head": head,
        "clean": dirty == "",
        "status_porcelain_sha256": _sha(dirty.encode("utf-8")),
    }


def _valid_patterns(values: list[str], label: str) -> list[str]:
    if (
        not isinstance(values, list)
        or not values
        or any(not isinstance(value, str) for value in values)
        or len(values) != len(set(values))
    ):
        raise EnrollmentError(f"{label} muss eindeutige nichtleere Liste sein")
    normalized: list[str] = []
    for value in values:
        item = value.replace("\\", "/").strip()
        if not item or item.startswith("/") or ".." in Path(item).parts:
            raise EnrollmentError(f"{label} enthaelt unsicheren Pfad/Glob: {value!r}")
        normalized.append(item)
    return normalized


def _patterns_overlap(left: list[str], right: list[str]) -> bool:
    for a in left:
        for b in right:
            if a == b or fnmatch.fnmatchcase(a, b) or fnmatch.fnmatchcase(b, a):
                return True
    return False


def deterministic_reviewer_id(
    run_id: str, session_id: str, audited_commit: str, snapshot_id: str
) -> str:
    digest = _sha(_canonical({
        "run_id": run_id,
        "session_id": session_id,
        "audited_commit": audited_commit.lower(),
        "snapshot_id": snapshot_id,
    }))
    return f"REV-{digest[:20].upper()}"


def _read_roster(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise EnrollmentError(f"Roster Zeile {number}: Objekt erwartet")
        rows.append(value)
    return rows


class _FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: int | None = None

    def __enter__(self) -> "_FileLock":
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode("ascii"))
                return self
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise EnrollmentError(f"Roster-Lock nicht erhalten: {self.path}")
                time.sleep(0.05)

    def __exit__(self, *_exc: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
        self.path.unlink(missing_ok=True)


def enroll(
    *,
    root: Path,
    session_id: str,
    run_id: str,
    audited_commit: str,
    snapshot_id: str,
    output_claims: list[str],
    review_scope: list[str],
    receipts_dir: Path,
    roster_path: Path,
) -> dict[str, Any]:
    root = root.resolve()
    commit = _resolve_commit(root, audited_commit)
    claims = _valid_patterns(output_claims, "output_claims")
    scope = _valid_patterns(review_scope, "review_scope")
    if not run_id or not snapshot_id or not session_id:
        raise EnrollmentError("run_id, snapshot_id und session_id sind Pflicht")

    # status() prunes stale/dead sessions under the registry lock.
    live = {str(row.get("id")): row for row in agent_session.status()}
    session = live.get(session_id)
    if session is None:
        raise EnrollmentError("Session fehlt, ist stale oder wurde bereits released")
    if session.get("forced") is True:
        raise EnrollmentError("forced Session darf keinen Audit-Receipt erhalten")
    lineage = session.get("ancestor_session_ids")
    parent = session.get("parent_session_id")
    if not isinstance(lineage, list) or any(not isinstance(item, str) or not item for item in lineage):
        raise EnrollmentError("Registry-Lineage fehlt oder ist ungueltig")
    if len(lineage) != len(set(lineage)) or session_id in lineage:
        raise EnrollmentError("Registry-Lineage zyklisch oder doppelt")
    if (lineage and parent != lineage[-1]) or (not lineage and parent is not None):
        raise EnrollmentError("Parent und transitive Registry-Lineage widersprechen sich")

    worktree = Path(str(session.get("worktree", "")))
    if not worktree.is_absolute() or not worktree.is_dir():
        raise EnrollmentError("registrierter Worktree fehlt")
    if _norm_path(worktree) not in _worktree_paths(root):
        raise EnrollmentError("registrierter Pfad ist kein realer Git-Worktree")
    state = _clean_git_state(worktree)
    if state["common_dir"] != _common_dir(root):
        raise EnrollmentError("Worktree gehoert nicht zum kanonischen Git-Common-Dir")
    if state["head"] != commit:
        raise EnrollmentError("Worktree-HEAD ist nicht audited_commit")
    if not state["clean"]:
        raise EnrollmentError("Worktree ist nicht clean")
    registered_branch = str(session.get("branch", ""))
    if registered_branch != state["branch"]:
        raise EnrollmentError("Registry-Branch und realer Worktree-Branch weichen ab")

    registry_session = {
        key: session.get(key)
        for key in (
            "id", "agent", "task", "pid", "host", "branch", "worktree",
            "started_at", "heartbeat", "claims", "parent_session_id",
            "ancestor_session_ids", "forced",
        )
    }
    reviewer_id = deterministic_reviewer_id(run_id, session_id, commit, snapshot_id)
    enrolled_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "issuer": ISSUER,
        "run_id": run_id,
        "audited_commit": commit,
        "snapshot_id": snapshot_id,
        "reviewer_id": reviewer_id,
        "session_id": session_id,
        "parent_session_id": parent,
        "ancestor_session_ids": lineage,
        "output_claims": claims,
        "review_scope": scope,
        "registry_session": registry_session,
        "registry_session_sha256": _sha(_canonical(registry_session)),
        "worktree": state,
        "enrolled_at": enrolled_at,
    }
    receipt_bytes = _canonical(receipt) + b"\n"
    receipt_sha = _sha(receipt_bytes)
    receipt_ref = f"{session_id}.json"
    row = {
        "run_id": run_id,
        "audited_commit": commit,
        "snapshot_id": snapshot_id,
        "reviewer_id": reviewer_id,
        "session_id": session_id,
        "parent_session_id": parent,
        "ancestor_session_ids": lineage,
        "worktree": state["path"],
        "branch": state["branch"],
        "commit_sha": commit,
        "claims": claims,
        "review_scope": scope,
        "session_receipt_ref": receipt_ref,
        "session_receipt_sha256": receipt_sha,
        "roster_signed_at": enrolled_at,
    }

    receipts_dir.mkdir(parents=True, exist_ok=True)
    roster_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path = receipts_dir / receipt_ref
    lock_path = roster_path.with_name(roster_path.name + ".lock")
    with _FileLock(lock_path):
        existing = _read_roster(roster_path)
        for number, item in enumerate(existing, 1):
            _valid_patterns(item.get("claims"), f"Roster Zeile {number} claims")
        if any(item.get("session_id") == session_id for item in existing):
            raise EnrollmentError("session_id bereits enrolled")
        if any(item.get("reviewer_id") == reviewer_id for item in existing):
            raise EnrollmentError("reviewer_id bereits enrolled")
        if any(_patterns_overlap(claims, item.get("claims") or []) for item in existing):
            raise EnrollmentError("Output-Claims ueberlappen bestehendes Reviewer-Shard")
        try:
            with receipt_path.open("xb") as handle:
                handle.write(receipt_bytes)
        except FileExistsError as exc:
            raise EnrollmentError("immutable Receipt existiert bereits") from exc
        roster_bytes = b"".join(_canonical(item) + b"\n" for item in [*existing, row])
        temp_path = roster_path.with_name(roster_path.name + ".tmp")
        try:
            temp_path.write_bytes(roster_bytes)
            os.replace(temp_path, roster_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            receipt_path.unlink(missing_ok=True)
            raise
    return row


def verify_roster(
    root: Path,
    roster_path: Path,
    receipts_dir: Path,
    *,
    run_id: str,
    audited_commit: str,
    snapshot_id: str,
    reviewer_pairs: list[tuple[str, str]] | None = None,
) -> list[str]:
    errors: list[str] = []
    try:
        commit = _resolve_commit(root.resolve(), audited_commit)
        rows = _read_roster(roster_path)
    except (EnrollmentError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [str(exc)]
    if not rows:
        return ["Reviewer-Roster ist leer"]
    by_reviewer: dict[str, dict[str, Any]] = {}
    by_session: dict[str, str] = {}
    all_claims: list[tuple[str, list[str]]] = []
    required = {
        "run_id", "audited_commit", "snapshot_id", "reviewer_id", "session_id",
        "parent_session_id", "ancestor_session_ids", "worktree", "branch",
        "commit_sha", "claims", "review_scope", "session_receipt_ref",
        "session_receipt_sha256", "roster_signed_at",
    }
    for number, row in enumerate(rows, 1):
        label = f"Roster Zeile {number}"
        missing = sorted(required - set(row))
        if missing:
            errors.append(f"{label}: Pflichtfelder fehlen: {missing}")
            continue
        reviewer_id = str(row["reviewer_id"])
        session_id = str(row["session_id"])
        if reviewer_id in by_reviewer:
            errors.append(f"{label}: reviewer_id doppelt")
        if session_id in by_session:
            errors.append(f"{label}: session_id doppelt")
        by_reviewer[reviewer_id] = row
        by_session[session_id] = reviewer_id
        expected_reviewer = deterministic_reviewer_id(run_id, session_id, commit, snapshot_id)
        if reviewer_id != expected_reviewer:
            errors.append(f"{label}: reviewer_id ist nicht deterministisch gebunden")
        if row["run_id"] != run_id or row["audited_commit"] != commit:
            errors.append(f"{label}: Run-/Commit-Bindung falsch")
        if row["snapshot_id"] != snapshot_id or row["commit_sha"] != commit:
            errors.append(f"{label}: Snapshot-/Commit-Signoff falsch")
        lineage = row["ancestor_session_ids"]
        if not isinstance(lineage, list) or len(lineage) != len(set(lineage)):
            errors.append(f"{label}: Lineage ungueltig")
            lineage = []
        if session_id in lineage:
            errors.append(f"{label}: eigene Session in Lineage")
        if (lineage and row["parent_session_id"] != lineage[-1]) or (
            not lineage and row["parent_session_id"] is not None
        ):
            errors.append(f"{label}: Parent/Lineage widersprechen sich")
        try:
            claims = _valid_patterns(row["claims"], "claims")
            _valid_patterns(row["review_scope"], "review_scope")
        except EnrollmentError as exc:
            errors.append(f"{label}: {exc}")
            claims = []
        for prior_id, prior_claims in all_claims:
            if _patterns_overlap(claims, prior_claims):
                errors.append(f"{label}: Output-Claims ueberlappen Reviewer {prior_id}")
        all_claims.append((reviewer_id, claims))

        receipt_ref = str(row["session_receipt_ref"])
        if receipt_ref != f"{session_id}.json" or Path(receipt_ref).name != receipt_ref:
            errors.append(f"{label}: unsicherer/falscher Receipt-Ref")
            continue
        receipt_path = receipts_dir / receipt_ref
        try:
            receipt_bytes = receipt_path.read_bytes()
            receipt = json.loads(receipt_bytes.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{label}: Receipt unlesbar: {exc}")
            continue
        if _sha(receipt_bytes) != row["session_receipt_sha256"]:
            errors.append(f"{label}: Receipt-Hash falsch")
        if _canonical(receipt) + b"\n" != receipt_bytes:
            errors.append(f"{label}: Receipt ist nicht kanonisch serialisiert")
        if receipt.get("issuer") != ISSUER or receipt.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"{label}: Receipt-Issuer/Schema falsch")
        projection = {
            "run_id": receipt.get("run_id"),
            "audited_commit": receipt.get("audited_commit"),
            "snapshot_id": receipt.get("snapshot_id"),
            "reviewer_id": receipt.get("reviewer_id"),
            "session_id": receipt.get("session_id"),
            "parent_session_id": receipt.get("parent_session_id"),
            "ancestor_session_ids": receipt.get("ancestor_session_ids"),
            "worktree": (receipt.get("worktree") or {}).get("path"),
            "branch": (receipt.get("worktree") or {}).get("branch"),
            "commit_sha": (receipt.get("worktree") or {}).get("head"),
            "claims": receipt.get("output_claims"),
            "review_scope": receipt.get("review_scope"),
            "roster_signed_at": receipt.get("enrolled_at"),
        }
        for field, value in projection.items():
            if row.get(field) != value:
                errors.append(f"{label}: Receipt/Roster-{field} weicht ab")
        registry_session = receipt.get("registry_session")
        if not isinstance(registry_session, dict) or _sha(_canonical(registry_session)) != receipt.get(
            "registry_session_sha256"
        ):
            errors.append(f"{label}: Registry-Session-Hash falsch")
        elif registry_session.get("id") != session_id or registry_session.get("forced") is not False:
            errors.append(f"{label}: Registry-Session-ID/forced ungueltig")
        worktree = receipt.get("worktree") or {}
        if worktree.get("head") != commit or worktree.get("clean") is not True:
            errors.append(f"{label}: Enrollment-Worktree war nicht clean/audited_commit")
        if worktree.get("common_dir") != _common_dir(root.resolve()):
            errors.append(f"{label}: Enrollment-Worktree gehoert anderem Git-Common-Dir")
        if isinstance(registry_session, dict):
            if _norm_path(registry_session.get("worktree", "")) != _norm_path(
                worktree.get("path", "")
            ) or registry_session.get("branch") != worktree.get("branch"):
                errors.append(f"{label}: Registry-/Git-Worktree-Bindung widerspricht sich")
            if registry_session.get("parent_session_id") != receipt.get(
                "parent_session_id"
            ) or registry_session.get("ancestor_session_ids") != receipt.get(
                "ancestor_session_ids"
            ):
                errors.append(f"{label}: Registry-/Receipt-Lineage widerspricht sich")

    for reviewer_a, reviewer_b in reviewer_pairs or []:
        a, b = by_reviewer.get(reviewer_a), by_reviewer.get(reviewer_b)
        if a is None or b is None:
            errors.append(f"Reviewer-Paar {reviewer_a}/{reviewer_b}: fremde ID")
            continue
        if a["session_id"] == b["session_id"] or a["reviewer_id"] == b["reviewer_id"]:
            errors.append(f"Reviewer-Paar {reviewer_a}/{reviewer_b}: gleiche Session/Identity")
        if a["session_id"] in (b.get("ancestor_session_ids") or []) or b["session_id"] in (
            a.get("ancestor_session_ids") or []
        ):
            errors.append(f"Reviewer-Paar {reviewer_a}/{reviewer_b}: Vorfahr/Nachfahre")
        if _norm_path(a["worktree"]) == _norm_path(b["worktree"]):
            errors.append(f"Reviewer-Paar {reviewer_a}/{reviewer_b}: gleicher Worktree")
        shared_ancestors = set(a.get("ancestor_session_ids") or []) & set(
            b.get("ancestor_session_ids") or []
        )
        signing_shared_ancestors = sorted(shared_ancestors & set(by_session))
        if signing_shared_ancestors:
            errors.append(
                f"Reviewer-Paar {reviewer_a}/{reviewer_b}: gemeinsamer Director "
                f"hat Signoff {signing_shared_ancestors}"
            )
        # A common ancestor outside the roster is intentionally allowed:
        # neutral Director, no pass/signoff.
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    enroll_parser = sub.add_parser("enroll")
    enroll_parser.add_argument("--root", type=Path, required=True)
    enroll_parser.add_argument("--session-id", required=True)
    enroll_parser.add_argument("--run-id", required=True)
    enroll_parser.add_argument("--audited-commit", required=True)
    enroll_parser.add_argument("--snapshot-id", required=True)
    enroll_parser.add_argument("--output-claim", action="append", required=True)
    enroll_parser.add_argument("--review-scope", action="append", required=True)
    enroll_parser.add_argument("--receipts-dir", type=Path, required=True)
    enroll_parser.add_argument("--roster", type=Path, required=True)

    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--root", type=Path, required=True)
    verify_parser.add_argument("--roster", type=Path, required=True)
    verify_parser.add_argument("--receipts-dir", type=Path, required=True)
    verify_parser.add_argument("--run-id", required=True)
    verify_parser.add_argument("--audited-commit", required=True)
    verify_parser.add_argument("--snapshot-id", required=True)
    verify_parser.add_argument("--pair", nargs=2, action="append", default=[])
    args = parser.parse_args(argv)
    try:
        if args.command == "enroll":
            row = enroll(
                root=args.root, session_id=args.session_id, run_id=args.run_id,
                audited_commit=args.audited_commit, snapshot_id=args.snapshot_id,
                output_claims=args.output_claim, review_scope=args.review_scope,
                receipts_dir=args.receipts_dir, roster_path=args.roster,
            )
            print(json.dumps({"ok": True, "reviewer": row}, ensure_ascii=False, indent=2))
            return 0
        errors = verify_roster(
            args.root, args.roster, args.receipts_dir, run_id=args.run_id,
            audited_commit=args.audited_commit, snapshot_id=args.snapshot_id,
            reviewer_pairs=[tuple(pair) for pair in args.pair],
        )
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        return 0 if not errors else 2
    except EnrollmentError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
