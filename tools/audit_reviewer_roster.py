"""Cryptographically anchored live reviewer enrollment and signoff receipts.

Unkeyed hashes are integrity checks, not identity attestations. This harness
requires an externally held OpenSSH signing key. Matching public-key SHA-256
must be pinned by audit contract/snapshot. Missing OpenSSH support, key pin,
signed contract, or signed spawn journal is a hard blocker. No unsigned mode.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import agent_session

SCHEMA_VERSION = 2
CONTRACT_NAMESPACE = "pb-audit-contract-v1"
SPAWN_NAMESPACE = "pb-audit-spawn-journal-v1"
ENROLLMENT_NAMESPACE = "pb-audit-enrollment-v1"
SIGNOFF_NAMESPACE = "pb-audit-signoff-v1"
SSH_IDENTITY = "pb-audit-trust-anchor"
LOCK_TIMEOUT_SECONDS = 10.0
LOCK_STALE_SECONDS = 30.0
SESSION_RE = re.compile(r"^[0-9a-f]{32}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ROLE_SET = {"pass-a", "pass-b", "lead-v", "adversarial"}
SPAWN_ROLE_SET = ROLE_SET | {"neutral-director"}
SHARD_RE = re.compile(r"^@audit/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+/(?:[A-Za-z0-9._-]+/)*\*\*$")
SCOPE_RE = re.compile(r"^(?:[A-Za-z0-9._-]+/)+(?:[A-Za-z0-9._-]+/)*\*\*$")


class ContractError(RuntimeError):
    """Fail-closed trust, identity, assignment, or evidence violation."""


EnrollmentError = ContractError


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _run(cwd: Path, *args: str, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            list(args), cwd=cwd, input=input_bytes, check=True, capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ContractError(f"Command fehlgeschlagen: {' '.join(args)}: {exc}") from exc


def _git(root: Path, *args: str) -> str:
    return _run(root, "git", *args).stdout.decode("utf-8").strip()


def _resolve_commit(root: Path, commit: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise ContractError("audited_commit muss volle 40-Zeichen-Git-SHA sein")
    resolved = _git(root, "rev-parse", "--verify", f"{commit}^{{commit}}").lower()
    if resolved != commit.lower():
        raise ContractError("audited_commit loest nicht auf sich selbst auf")
    return resolved


def _norm_path(value: str | Path) -> str:
    return os.path.normcase(str(Path(value).resolve()))


def _common_dir(root: Path) -> Path:
    raw = Path(_git(root, "rev-parse", "--git-common-dir"))
    return (raw if raw.is_absolute() else root / raw).resolve()


def public_key_sha256(public_key_path: Path) -> str:
    if not public_key_path.is_file():
        raise ContractError("externer Public-Key fehlt")
    return _sha(public_key_path.read_bytes())


def _ssh_available() -> None:
    if shutil.which("ssh-keygen") is None:
        raise ContractError("OpenSSH ssh-keygen fehlt; kryptographische Attestierung blockiert")


def sign_file(payload_path: Path, signature_path: Path, signing_key: Path, namespace: str) -> None:
    _ssh_available()
    if not payload_path.is_file() or not signing_key.is_file():
        raise ContractError("Payload oder externer Signing-Key fehlt")
    if signature_path.exists():
        raise ContractError("immutable Signatur existiert bereits")
    produced = payload_path.with_name(payload_path.name + ".sig")
    if produced.exists():
        raise ContractError("verwaiste Signatur blockiert Signing")
    _run(payload_path.parent, "ssh-keygen", "-Y", "sign", "-f", str(signing_key), "-n", namespace, str(payload_path))
    if not produced.is_file():
        raise ContractError("ssh-keygen erzeugte keine Signatur")
    os.replace(produced, signature_path)


def verify_signature(payload_path: Path, signature_path: Path, public_key_path: Path,
                     expected_public_key_sha256: str, namespace: str) -> None:
    _ssh_available()
    if not SHA_RE.fullmatch(expected_public_key_sha256):
        raise ContractError("Public-Key-Pin fehlt/ist ungueltig")
    if public_key_sha256(public_key_path) != expected_public_key_sha256:
        raise ContractError("Public-Key-SHA256 weicht vom gepinnten Trust-Anchor ab")
    if not payload_path.is_file() or not signature_path.is_file():
        raise ContractError("signierter Payload oder Signatur fehlt")
    public_line = public_key_path.read_text(encoding="utf-8").strip()
    if not public_line.startswith(("ssh-ed25519 ", "ssh-rsa ", "ecdsa-sha2-")):
        raise ContractError("ungueltiger OpenSSH Public-Key")
    with tempfile.TemporaryDirectory(prefix="pb-audit-allowed-") as temp:
        allowed = Path(temp) / "allowed_signers"
        allowed.write_text(f"{SSH_IDENTITY} {public_line}\n", encoding="utf-8")
        _run(payload_path.parent, "ssh-keygen", "-Y", "verify", "-f", str(allowed),
             "-I", SSH_IDENTITY, "-n", namespace, "-s", str(signature_path),
             input_bytes=payload_path.read_bytes())


def _load_signed_json(path: Path, signature: Path, public_key: Path, pin: str,
                      namespace: str) -> tuple[dict[str, Any], str]:
    verify_signature(path, signature, public_key, pin, namespace)
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"signiertes JSON unlesbar: {exc}") from exc
    if not isinstance(value, dict) or _canonical(value) + b"\n" != raw:
        raise ContractError("signiertes JSON muss kanonisches Objekt plus LF sein")
    return value, _sha(raw)


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
                try:
                    if time.time() - self.path.stat().st_mtime > LOCK_STALE_SECONDS:
                        self.path.unlink(missing_ok=True)
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise ContractError(f"Lock nicht erhalten: {self.path}")
                time.sleep(0.05)

    def __exit__(self, *_exc: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
        self.path.unlink(missing_ok=True)

    def heartbeat(self) -> None:
        """Keep a legitimately long enrollment lock from looking orphaned."""
        if self.fd is None or not self.path.exists():
            raise ContractError(f"Lock ging waehrend Operation verloren: {self.path}")
        os.utime(self.path, None)


def _read_registry_locked(common_dir: Path) -> dict[str, dict[str, Any]]:
    path = common_dir / "pb-agent-sessions.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"kanonische Shared Registry unlesbar: {exc}") from exc
    rows = data.get("sessions") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ContractError("kanonische Shared Registry hat falsches Schema")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise ContractError("Registry enthaelt Legacy-/ungueltige Session")
        result[row["id"]] = row
    return result


def _live_session(rows: dict[str, dict[str, Any]], session_id: str) -> dict[str, Any]:
    if not SESSION_RE.fullmatch(session_id):
        raise ContractError("session_id ist nicht filename-sichere 32-Zeichen-Hex-ID")
    row = rows.get(session_id)
    if row is None:
        raise ContractError("Session fehlt oder wurde released")
    required = {"forced", "forced_lineage", "parent_session_id", "ancestor_session_ids", "heartbeat", "claims", "worktree", "branch"}
    if not required <= set(row) or not isinstance(row.get("forced"), bool) or not isinstance(row.get("forced_lineage"), bool):
        raise ContractError("Legacy-Session ohne forced/Lineage-Provenienz blockiert Receipt")
    if agent_session._is_dead(row, time.time()):
        raise ContractError("Session ist stale/tot")
    if row["forced"] or row["forced_lineage"]:
        raise ContractError("forced Session/Vorfahr darf nicht attestieren")
    return row


def _validate_patterns(values: Any, regex: re.Pattern[str], label: str) -> list[str]:
    if not isinstance(values, list) or not values or len(values) != len(set(values)):
        raise ContractError(f"{label} muss eindeutige nichtleere Liste sein")
    if any(not isinstance(value, str) or not regex.fullmatch(value) for value in values):
        raise ContractError(f"{label} verletzt kanonische Prefix-Grammatik")
    return list(values)


def deterministic_reviewer_id(run_id: str, session_id: str, commit: str,
                              snapshot_id: str) -> str:
    return "REV-" + _sha(_canonical({
        "run_id": run_id, "session_id": session_id,
        "audited_commit": commit.lower(), "snapshot_id": snapshot_id,
    }))[:20].upper()


def _validate_spawn_journal(journal: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    if set(journal) != {"schema_version", "records"} or journal["schema_version"] != 1:
        raise ContractError("Spawn-Journal-Schema falsch")
    records = journal["records"]
    if not isinstance(records, list) or not records:
        raise ContractError("Spawn-Journal ist leer")
    by_id: dict[str, dict[str, Any]] = {}
    lineage: dict[str, list[str]] = {}
    previous: str | None = None
    for index, row in enumerate(records, 1):
        if not isinstance(row, dict):
            raise ContractError("Spawn-Journal-Record muss Objekt sein")
        body = {key: row.get(key) for key in ("seq", "session_id", "parent_session_id", "role", "forced", "spawned_at", "previous_record_sha256")}
        if row.get("record_sha256") != _sha(_canonical(body)):
            raise ContractError("Spawn-Journal-Recordhash falsch")
        sid, parent = row.get("session_id"), row.get("parent_session_id")
        if row.get("seq") != index or row.get("previous_record_sha256") != previous:
            raise ContractError("Spawn-Journal ist nicht append-only verkettet")
        if not isinstance(sid, str) or not SESSION_RE.fullmatch(sid) or sid in by_id:
            raise ContractError("Spawn-Journal session_id fehlt/doppelt")
        if row.get("role") not in SPAWN_ROLE_SET or not isinstance(row.get("forced"), bool):
            raise ContractError("Spawn-Journal Rolle/forced ungueltig")
        if parent is not None and parent not in by_id:
            raise ContractError("Spawn-Journal Parent muss frueherer Record sein")
        lineage[sid] = [*lineage.get(parent, []), parent] if parent else []
        by_id[sid] = row
        previous = row["record_sha256"]
    return by_id, lineage


def _validate_contract(root: Path, contract: dict[str, Any], contract_sha: str,
                       spawn_sha: str, public_pin: str) -> tuple[str, dict[str, dict[str, Any]]]:
    required = {"schema_version", "run_id", "audited_commit", "snapshot_id",
                "public_key_sha256", "spawn_journal_sha256", "reviewers",
                "reviewer_pairs", "assignments", "required_signoffs"}
    if set(contract) != required or contract.get("schema_version") != 1:
        raise ContractError("Reviewer-Contract Schema/Feldmenge falsch")
    commit = _resolve_commit(root, str(contract["audited_commit"]))
    if contract["public_key_sha256"] != public_pin or contract["spawn_journal_sha256"] != spawn_sha:
        raise ContractError("Reviewer-Contract Trust-/Spawn-Bindung falsch")
    if not contract_sha or not contract.get("run_id") or not contract.get("snapshot_id"):
        raise ContractError("Reviewer-Contract Run/Snapshot fehlt")
    reviewers = contract["reviewers"]
    if not isinstance(reviewers, list) or len(reviewers) < 2:
        raise ContractError("exakte required reviewers fehlen")
    by_id: dict[str, dict[str, Any]] = {}
    sessions: set[str] = set()
    for spec in reviewers:
        if not isinstance(spec, dict) or set(spec) != {"reviewer_id", "session_id", "role", "output_claims", "review_scope"}:
            raise ContractError("Reviewer-Spec Feldmenge falsch")
        sid, rid = spec["session_id"], spec["reviewer_id"]
        if not isinstance(sid, str) or not SESSION_RE.fullmatch(sid) or sid in sessions:
            raise ContractError("Reviewer-Spec Session fehlt/doppelt")
        if spec["role"] not in ROLE_SET or rid in by_id:
            raise ContractError("Reviewer-Spec Rolle/ID fehlt/doppelt")
        if rid != deterministic_reviewer_id(contract["run_id"], sid, commit, contract["snapshot_id"]):
            raise ContractError("Reviewer-ID nicht deterministisch")
        _validate_patterns(spec["output_claims"], SHARD_RE, "output_claims")
        _validate_patterns(spec["review_scope"], SCOPE_RE, "review_scope")
        sessions.add(sid)
        by_id[rid] = spec
    claimed_prefixes: list[tuple[str, str]] = []
    for rid, spec in by_id.items():
        for claim in spec["output_claims"]:
            prefix = claim[:-2]
            for prior_rid, prior_prefix in claimed_prefixes:
                if prefix.startswith(prior_prefix) or prior_prefix.startswith(prefix):
                    raise ContractError(
                        f"Output-Shard-Claims ueberlappen: {prior_rid}/{rid}"
                    )
            claimed_prefixes.append((rid, prefix))
    pairs = contract["reviewer_pairs"]
    if not isinstance(pairs, list) or not pairs:
        raise ContractError("reviewer_pairs ist mandatory und nichtleer")
    normalized_pairs: set[tuple[str, str]] = set()
    for pair in pairs:
        if not isinstance(pair, list) or len(pair) != 2 or pair[0] not in by_id or pair[1] not in by_id or pair[0] == pair[1]:
            raise ContractError("fremdes/ungueltiges reviewer_pair")
        key = tuple(sorted(pair))
        if key in normalized_pairs:
            raise ContractError("doppeltes reviewer_pair")
        normalized_pairs.add(key)
    assignments = contract["assignments"]
    if not isinstance(assignments, list) or not assignments:
        raise ContractError("exakte assignments fehlen")
    assignment_ids: set[str] = set()
    assigned_reviewers: set[str] = set()
    for item in assignments:
        keys = {"assignment_id", "reviewer_id", "role", "pass", "output_claim", "review_scope"}
        if not isinstance(item, dict) or set(item) != keys or item["assignment_id"] in assignment_ids:
            raise ContractError("Assignment Feldmenge/ID falsch")
        spec = by_id.get(item["reviewer_id"])
        if spec is None or item["role"] != spec["role"]:
            raise ContractError("Assignment Reviewer/Rolle falsch")
        if item["output_claim"] not in spec["output_claims"] or item["review_scope"] not in spec["review_scope"]:
            raise ContractError("Assignment Claim/Scope nicht exakt im Reviewer-Vertrag")
        if item["pass"] not in {"A", "B", "completion"}:
            raise ContractError("Assignment Pass ungueltig")
        assignment_ids.add(item["assignment_id"])
        assigned_reviewers.add(item["reviewer_id"])
    if assigned_reviewers != set(by_id):
        raise ContractError("Assignments decken required reviewers nicht exakt")
    signoffs = contract["required_signoffs"]
    if not isinstance(signoffs, list) or not signoffs:
        raise ContractError("required_signoffs fehlen")
    seen_roles: set[str] = set()
    for item in signoffs:
        if not isinstance(item, dict) or set(item) != {"reviewer_id", "role"}:
            raise ContractError("required_signoff Feldmenge falsch")
        spec = by_id.get(item["reviewer_id"])
        if spec is None or item["role"] != spec["role"] or item["role"] in seen_roles:
            raise ContractError("required_signoff Reviewer/Rolle falsch/doppelt")
        seen_roles.add(item["role"])
    if not {"lead-v", "adversarial"} <= seen_roles:
        raise ContractError("Lead V plus Adversarial Signoff fehlen")
    return commit, by_id


def _load_trust(root: Path, contract_path: Path, contract_signature: Path,
                spawn_journal_path: Path, spawn_journal_signature: Path,
                public_key_path: Path, expected_public_key_sha256: str
                ) -> tuple[dict[str, Any], str, dict[str, dict[str, Any]], dict[str, list[str]], str, dict[str, dict[str, Any]]]:
    contract, contract_sha = _load_signed_json(contract_path, contract_signature,
                                               public_key_path, expected_public_key_sha256,
                                               CONTRACT_NAMESPACE)
    journal, spawn_sha = _load_signed_json(spawn_journal_path, spawn_journal_signature,
                                           public_key_path, expected_public_key_sha256,
                                           SPAWN_NAMESPACE)
    spawn, lineage = _validate_spawn_journal(journal)
    commit, reviewers = _validate_contract(root, contract, contract_sha, spawn_sha,
                                           expected_public_key_sha256)
    for spec in reviewers.values():
        record = spawn.get(spec["session_id"])
        if record is None or record["role"] != spec["role"]:
            raise ContractError("Reviewer fehlt/hat andere Rolle im signierten Spawn-Journal")
        if record["forced"] or any(spawn[ancestor]["forced"] for ancestor in lineage[spec["session_id"]]):
            raise ContractError("Reviewer oder Vorfahr wurde forced gestartet")
    return contract, contract_sha, spawn, lineage, commit, reviewers


def _worktree_state(root: Path, session: dict[str, Any], commit: str) -> dict[str, Any]:
    worktree = Path(str(session["worktree"]))
    if not worktree.is_absolute() or not worktree.is_dir():
        raise ContractError("registrierter Worktree fehlt")
    listed = {_norm_path(line.removeprefix("worktree "))
              for line in _git(root, "worktree", "list", "--porcelain").splitlines()
              if line.startswith("worktree ")}
    if _norm_path(worktree) not in listed:
        raise ContractError("registrierter Pfad ist kein realer Git-Worktree")
    head = _git(worktree, "rev-parse", "HEAD").lower()
    branch = _git(worktree, "rev-parse", "--abbrev-ref", "HEAD")
    dirty = _git(worktree, "status", "--porcelain", "--untracked-files=all")
    if _common_dir(worktree) != _common_dir(root) or head != commit or branch != session["branch"] or dirty:
        raise ContractError("Worktree Common-Dir/HEAD/Branch/Clean-Gate rot")
    return {"path": str(worktree.resolve()), "common_dir": str(_common_dir(root)),
            "head": head, "branch": branch, "clean": True}


def _read_roster(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"Roster unlesbar: {exc}") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise ContractError("Rosterzeile muss Objekt sein")
    return rows


def _row_from_receipt(receipt: dict[str, Any], receipt_ref: str, receipt_sha: str,
                      signature_ref: str) -> dict[str, Any]:
    state = receipt["worktree"]
    return {"run_id": receipt["run_id"], "audited_commit": receipt["audited_commit"],
            "snapshot_id": receipt["snapshot_id"], "reviewer_id": receipt["reviewer_id"],
            "session_id": receipt["session_id"], "role": receipt["role"],
            "parent_session_id": receipt["parent_session_id"],
            "ancestor_session_ids": receipt["ancestor_session_ids"],
            "worktree": state["path"], "branch": state["branch"], "commit_sha": state["head"],
            "claims": receipt["output_claims"], "review_scope": receipt["review_scope"],
            "session_receipt_ref": receipt_ref, "session_receipt_sha256": receipt_sha,
            "session_receipt_signature_ref": signature_ref,
            "contract_sha256": receipt["contract_sha256"],
            "spawn_journal_sha256": receipt["spawn_journal_sha256"],
            "public_key_sha256": receipt["public_key_sha256"],
            "roster_signed_at": receipt["enrolled_at"]}


def enroll(*, root: Path, session_id: str, contract_path: Path,
           contract_signature: Path, spawn_journal_path: Path,
           spawn_journal_signature: Path, public_key_path: Path,
           expected_public_key_sha256: str, receipts_dir: Path,
           roster_path: Path, signing_key: Path) -> dict[str, Any]:
    root = root.resolve()
    contract, contract_sha, spawn, lineage, commit, reviewers = _load_trust(
        root, contract_path, contract_signature, spawn_journal_path,
        spawn_journal_signature, public_key_path, expected_public_key_sha256)
    spec = next((value for value in reviewers.values() if value["session_id"] == session_id), None)
    if spec is None:
        raise ContractError("Session ist kein exakt required reviewer")
    common = _common_dir(root)
    receipts_dir.mkdir(parents=True, exist_ok=True)
    roster_path.parent.mkdir(parents=True, exist_ok=True)
    with _FileLock(common / "pb-agent-sessions.lock") as registry_guard, _FileLock(roster_path.with_name(roster_path.name + ".lock")):
        sessions = _read_registry_locked(common)
        session = _live_session(sessions, session_id)
        record = spawn[session_id]
        if session["parent_session_id"] != record["parent_session_id"] or session["ancestor_session_ids"] != lineage[session_id]:
            raise ContractError("Registry-Lineage weicht von signiertem Spawn-Journal ab")
        if session["claims"] != spec["output_claims"]:
            raise ContractError("output_claims muessen exakt Registry-Claims entsprechen")
        registry_guard.heartbeat()
        state = _worktree_state(root, session, commit)
        registry_guard.heartbeat()
        if _read_registry_locked(common).get(session_id) != session:
            raise ContractError("Registry-Session driftete waehrend Enrollment")
        existing = _read_roster(roster_path)
        if any(row.get("session_id") == session_id or row.get("reviewer_id") == spec["reviewer_id"] for row in existing):
            raise ContractError("Session/Reviewer bereits enrolled")
        receipt_ref, signature_ref = f"{session_id}.json", f"{session_id}.json.sig"
        receipt_path, signature_path = receipts_dir / receipt_ref, receipts_dir / signature_ref
        receipt = {"schema_version": SCHEMA_VERSION, "run_id": contract["run_id"],
                   "audited_commit": commit, "snapshot_id": contract["snapshot_id"],
                   "reviewer_id": spec["reviewer_id"], "session_id": session_id,
                   "role": spec["role"], "parent_session_id": record["parent_session_id"],
                   "ancestor_session_ids": lineage[session_id],
                   "output_claims": spec["output_claims"], "review_scope": spec["review_scope"],
                   "worktree": state, "registry_session_sha256": _sha(_canonical(session)),
                   "contract_sha256": contract_sha,
                   "spawn_journal_sha256": contract["spawn_journal_sha256"],
                   "public_key_sha256": expected_public_key_sha256,
                   "enrolled_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if receipt_path.exists() or signature_path.exists():
            verify_signature(receipt_path, signature_path, public_key_path,
                             expected_public_key_sha256, ENROLLMENT_NAMESPACE)
            recovered = json.loads(receipt_path.read_text(encoding="utf-8"))
            fixed = {key: receipt[key] for key in receipt if key != "enrolled_at"}
            if {key: recovered.get(key) for key in fixed} != fixed:
                raise ContractError("verwaistes Receipt passt nicht zur Live-Session")
            receipt = recovered
        else:
            receipt_path.write_bytes(_canonical(receipt) + b"\n")
            try:
                sign_file(receipt_path, signature_path, signing_key, ENROLLMENT_NAMESPACE)
                verify_signature(
                    receipt_path, signature_path, public_key_path,
                    expected_public_key_sha256, ENROLLMENT_NAMESPACE,
                )
                registry_guard.heartbeat()
            except Exception:
                receipt_path.unlink(missing_ok=True)
                signature_path.unlink(missing_ok=True)
                raise
        row = _row_from_receipt(receipt, receipt_ref, _sha(receipt_path.read_bytes()), signature_ref)
        temp = roster_path.with_name(roster_path.name + ".tmp")
        temp.write_bytes(b"".join(_canonical(item) + b"\n" for item in [*existing, row]))
        os.replace(temp, roster_path)
        return row


def verify_roster(root: Path, roster_path: Path, receipts_dir: Path, *,
                  contract_path: Path, contract_signature: Path,
                  spawn_journal_path: Path, spawn_journal_signature: Path,
                  public_key_path: Path, expected_public_key_sha256: str) -> list[str]:
    try:
        root = root.resolve()
        contract, contract_sha, spawn, lineage, commit, reviewers = _load_trust(
            root, contract_path, contract_signature, spawn_journal_path,
            spawn_journal_signature, public_key_path, expected_public_key_sha256)
        rows = _read_roster(roster_path)
        by_id = {str(row.get("reviewer_id")): row for row in rows}
        if len(by_id) != len(rows) or set(by_id) != set(reviewers):
            raise ContractError("Roster ist nicht exakte required-reviewer-Menge")
        sessions = [row.get("session_id") for row in rows]
        if len(sessions) != len(set(sessions)):
            raise ContractError("Roster session_id doppelt")
        for rid, spec in reviewers.items():
            row, sid = by_id[rid], spec["session_id"]
            expected = {"run_id": contract["run_id"], "audited_commit": commit,
                        "snapshot_id": contract["snapshot_id"], "reviewer_id": rid,
                        "session_id": sid, "role": spec["role"],
                        "parent_session_id": spawn[sid]["parent_session_id"],
                        "ancestor_session_ids": lineage[sid], "commit_sha": commit,
                        "claims": spec["output_claims"], "review_scope": spec["review_scope"],
                        "contract_sha256": contract_sha,
                        "spawn_journal_sha256": contract["spawn_journal_sha256"],
                        "public_key_sha256": expected_public_key_sha256}
            if any(row.get(key) != value for key, value in expected.items()):
                raise ContractError(f"{rid}: Roster weicht von signiertem exakten Vertrag ab")
            receipt_ref, sig_ref = row.get("session_receipt_ref"), row.get("session_receipt_signature_ref")
            if receipt_ref != f"{sid}.json" or sig_ref != f"{sid}.json.sig":
                raise ContractError(f"{rid}: unsicherer Receipt-Dateiname")
            receipt_path, sig_path = receipts_dir / receipt_ref, receipts_dir / sig_ref
            verify_signature(receipt_path, sig_path, public_key_path,
                             expected_public_key_sha256, ENROLLMENT_NAMESPACE)
            if _sha(receipt_path.read_bytes()) != row.get("session_receipt_sha256"):
                raise ContractError(f"{rid}: Receipt-Hash falsch")
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            if _canonical(receipt) + b"\n" != receipt_path.read_bytes():
                raise ContractError(f"{rid}: Receipt nicht kanonisch")
            if _row_from_receipt(receipt, receipt_ref, row["session_receipt_sha256"], sig_ref) != row:
                raise ContractError(f"{rid}: Receipt/Roster-Projektion weicht ab")
        for a_id, b_id in contract["reviewer_pairs"]:
            a, b = by_id[a_id], by_id[b_id]
            if a["session_id"] in b["ancestor_session_ids"] or b["session_id"] in a["ancestor_session_ids"]:
                raise ContractError("Reviewer-Paar ist Vorfahr/Nachfahre")
            if _norm_path(a["worktree"]) == _norm_path(b["worktree"]):
                raise ContractError("Reviewer-Paar teilt Worktree")
            shared = set(a["ancestor_session_ids"]) & set(b["ancestor_session_ids"])
            for ancestor in shared:
                if spawn[ancestor]["role"] != "neutral-director" or ancestor in sessions:
                    raise ContractError("gemeinsamer Vorfahr ist nicht neutraler Director ohne Signoff")
        return []
    except (ContractError, OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return [str(exc)]


def finalize_signoff(*, root: Path, session_id: str, role: str,
                     basis_sha256: str, verdict: str, roster_path: Path,
                     receipts_dir: Path, attestations_dir: Path,
                     contract_path: Path, contract_signature: Path,
                     spawn_journal_path: Path, spawn_journal_signature: Path,
                     public_key_path: Path, expected_public_key_sha256: str,
                     signing_key: Path) -> Path:
    if not SHA_RE.fullmatch(basis_sha256) or verdict not in {"pass", "fail"}:
        raise ContractError("basis_sha256/verdict ungueltig")
    root = root.resolve()
    common = _common_dir(root)
    roster_lock = roster_path.with_name(roster_path.name + ".lock")
    with _FileLock(common / "pb-agent-sessions.lock") as registry_guard, _FileLock(roster_lock):
        registry_guard.heartbeat()
        errors = verify_roster(
            root, roster_path, receipts_dir, contract_path=contract_path,
            contract_signature=contract_signature,
            spawn_journal_path=spawn_journal_path,
            spawn_journal_signature=spawn_journal_signature,
            public_key_path=public_key_path,
            expected_public_key_sha256=expected_public_key_sha256,
        )
        if errors:
            raise ContractError("Roster vor Signoff rot: " + "; ".join(errors))
        registry_guard.heartbeat()
        contract, contract_sha, _spawn, _lineage, _commit, reviewers = _load_trust(
            root, contract_path, contract_signature, spawn_journal_path,
            spawn_journal_signature, public_key_path,
            expected_public_key_sha256,
        )
        spec = next(
            (value for value in reviewers.values() if value["session_id"] == session_id),
            None,
        )
        required = {
            item["reviewer_id"]: item["role"]
            for item in contract["required_signoffs"]
        }
        if (
            spec is None
            or required.get(spec["reviewer_id"]) != role
            or spec["role"] != role
        ):
            raise ContractError("Session/Rolle ist kein exakt required signoff")
        session = _live_session(_read_registry_locked(common), session_id)
        row = next(row for row in _read_roster(roster_path) if row["session_id"] == session_id)
        if session["claims"] != row["claims"]:
            raise ContractError("aktive Session/Receipt-Claims drifteten")
        receipt_path = receipts_dir / row["session_receipt_ref"]
        attestation = {"schema_version": 1, "run_id": contract["run_id"],
                       "reviewer_id": spec["reviewer_id"], "session_id": session_id,
                       "role": role, "basis_sha256": basis_sha256, "verdict": verdict,
                       "contract_sha256": contract_sha,
                       "enrollment_receipt_sha256": _sha(receipt_path.read_bytes()),
                       "signed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        attestations_dir.mkdir(parents=True, exist_ok=True)
        path = attestations_dir / f"{role}-{session_id}.json"
        signature = attestations_dir / f"{role}-{session_id}.json.sig"
        if path.exists() or signature.exists():
            raise ContractError("immutable Signoff-Attestierung existiert bereits")
        path.write_bytes(_canonical(attestation) + b"\n")
        try:
            sign_file(path, signature, signing_key, SIGNOFF_NAMESPACE)
            verify_signature(
                path, signature, public_key_path,
                expected_public_key_sha256, SIGNOFF_NAMESPACE,
            )
            registry_guard.heartbeat()
        except Exception:
            path.unlink(missing_ok=True)
            signature.unlink(missing_ok=True)
            raise
        return path


def verify_attestation_bundle(root: Path, roster_path: Path, receipts_dir: Path,
                              attestations_dir: Path, *, basis_sha256: str,
                              contract_path: Path, contract_signature: Path,
                              spawn_journal_path: Path, spawn_journal_signature: Path,
                              public_key_path: Path,
                              expected_public_key_sha256: str) -> list[str]:
    errors = verify_roster(root, roster_path, receipts_dir,
                           contract_path=contract_path, contract_signature=contract_signature,
                           spawn_journal_path=spawn_journal_path,
                           spawn_journal_signature=spawn_journal_signature,
                           public_key_path=public_key_path,
                           expected_public_key_sha256=expected_public_key_sha256)
    if errors:
        return errors
    try:
        if not SHA_RE.fullmatch(basis_sha256):
            raise ContractError("basis_sha256 ungueltig")
        contract, contract_sha, _spawn, _lineage, _commit, reviewers = _load_trust(
            root.resolve(), contract_path, contract_signature, spawn_journal_path,
            spawn_journal_signature, public_key_path, expected_public_key_sha256)
        rows = {row["reviewer_id"]: row for row in _read_roster(roster_path)}
        expected_files: set[str] = set()
        for required in contract["required_signoffs"]:
            rid, role = required["reviewer_id"], required["role"]
            spec, row = reviewers[rid], rows[rid]
            name = f"{role}-{spec['session_id']}.json"
            expected_files |= {name, name + ".sig"}
            path, signature = attestations_dir / name, attestations_dir / (name + ".sig")
            verify_signature(path, signature, public_key_path,
                             expected_public_key_sha256, SIGNOFF_NAMESPACE)
            value = json.loads(path.read_text(encoding="utf-8"))
            expected = {"schema_version": 1, "run_id": contract["run_id"],
                        "reviewer_id": rid, "session_id": spec["session_id"],
                        "role": role, "basis_sha256": basis_sha256, "verdict": "pass",
                        "contract_sha256": contract_sha,
                        "enrollment_receipt_sha256": row["session_receipt_sha256"]}
            if any(value.get(key) != expected_value for key, expected_value in expected.items()):
                raise ContractError("Signoff-Attestierung Bindung/Verdict falsch")
        actual = {path.name for path in attestations_dir.iterdir() if path.is_file()}
        if actual != expected_files:
            raise ContractError("Attestation-Bundle Dateimenge nicht exakt")
        return []
    except (ContractError, OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return [str(exc)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-check")

    def add_trust(command: argparse.ArgumentParser) -> None:
        command.add_argument("--root", type=Path, required=True)
        command.add_argument("--contract", type=Path, required=True)
        command.add_argument("--contract-signature", type=Path, required=True)
        command.add_argument("--spawn-journal", type=Path, required=True)
        command.add_argument("--spawn-journal-signature", type=Path, required=True)
        command.add_argument("--public-key", type=Path, required=True)
        command.add_argument("--public-key-sha256", required=True)
        command.add_argument("--roster", type=Path, required=True)
        command.add_argument("--receipts-dir", type=Path, required=True)

    enroll_parser = sub.add_parser("enroll")
    add_trust(enroll_parser)
    enroll_parser.add_argument("--session-id", required=True)
    enroll_parser.add_argument("--signing-key", type=Path, required=True)

    verify_parser = sub.add_parser("verify")
    add_trust(verify_parser)

    finalize_parser = sub.add_parser("finalize")
    add_trust(finalize_parser)
    finalize_parser.add_argument("--session-id", required=True)
    finalize_parser.add_argument("--role", required=True, choices=sorted(ROLE_SET))
    finalize_parser.add_argument("--basis-sha256", required=True)
    finalize_parser.add_argument("--verdict", required=True, choices=("pass", "fail"))
    finalize_parser.add_argument("--attestations-dir", type=Path, required=True)
    finalize_parser.add_argument("--signing-key", type=Path, required=True)

    bundle_parser = sub.add_parser("verify-bundle")
    add_trust(bundle_parser)
    bundle_parser.add_argument("--basis-sha256", required=True)
    bundle_parser.add_argument("--attestations-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "self-check":
        try:
            _ssh_available()
            print(json.dumps({"ok": True, "trust": "external-openssh-signature-required"}))
            return 0
        except ContractError as exc:
            print(json.dumps({"ok": False, "errors": [str(exc)]}))
            return 2
    trust = {
        "contract_path": args.contract,
        "contract_signature": args.contract_signature,
        "spawn_journal_path": args.spawn_journal,
        "spawn_journal_signature": args.spawn_journal_signature,
        "public_key_path": args.public_key,
        "expected_public_key_sha256": args.public_key_sha256,
    }
    try:
        if args.command == "enroll":
            result = enroll(
                root=args.root, session_id=args.session_id,
                roster_path=args.roster, receipts_dir=args.receipts_dir,
                signing_key=args.signing_key, **trust,
            )
            print(json.dumps({"ok": True, "reviewer": result}, ensure_ascii=False))
            return 0
        if args.command == "verify":
            errors = verify_roster(
                args.root, args.roster, args.receipts_dir, **trust,
            )
        elif args.command == "finalize":
            path = finalize_signoff(
                root=args.root, session_id=args.session_id, role=args.role,
                basis_sha256=args.basis_sha256, verdict=args.verdict,
                roster_path=args.roster, receipts_dir=args.receipts_dir,
                attestations_dir=args.attestations_dir,
                signing_key=args.signing_key, **trust,
            )
            print(json.dumps({"ok": True, "attestation": str(path)}, ensure_ascii=False))
            return 0
        else:
            errors = verify_attestation_bundle(
                args.root, args.roster, args.receipts_dir,
                args.attestations_dir, basis_sha256=args.basis_sha256, **trust,
            )
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False))
        return 0 if not errors else 2
    except ContractError as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
