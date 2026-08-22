from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tools import agent_session
from tools import audit_completion as completion
from tools import audit_reviewer_roster as roster


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


class GateContractTests(unittest.TestCase):
    def test_tooling_commit_policy_is_mandatory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            _git(root, "init", "-b", "main")
            _git(root, "config", "user.email", "audit@example.invalid")
            _git(root, "config", "user.name", "Audit Test")
            (root / "seed").write_text("x", encoding="utf-8")
            _git(root, "add", "seed")
            _git(root, "commit", "-m", "seed")
            with self.assertRaises(roster.ContractError):
                roster.load_trust_policy(root, _git(root, "rev-parse", "HEAD"))

    def test_lock_exit_never_removes_foreign_owner_token(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "owned.lock"
            guard = roster._FileLock(path)
            guard.__enter__()
            foreign = {"token": "foreign", "pid": 1, "heartbeat": time.time()}
            agent_session._write_lock_payload(
                guard.fd, roster._canonical(foreign) + b"\n",
            )
            with self.assertRaises(roster.ContractError):
                guard.__exit__(None, None, None)
            self.assertTrue(path.exists())

    def test_stale_lock_recovery_never_replaces_shared_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "stale.lock"
            path.write_bytes(roster._canonical({
                "token": "dead", "pid": 999999,
                "heartbeat": time.time() - roster.LOCK_STALE_SECONDS - 5,
            }) + b"\n")
            with mock.patch.object(
                roster.os, "replace",
                side_effect=AssertionError("shared lock path must not be replaced"),
            ):
                with roster._FileLock(path):
                    self.assertTrue(path.exists())

    def test_reviewer_and_registry_share_same_kernel_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            common = Path(temp)
            path = common / "pb-agent-sessions.lock"
            with (
                mock.patch.object(agent_session, "_git_common_dir", return_value=common),
                mock.patch.object(agent_session, "LOCK_TIMEOUT_SEC", 0.05),
                roster._FileLock(path),
            ):
                with self.assertRaises(TimeoutError):
                    agent_session._Lock().__enter__()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-b", "main")
        _git(self.repo, "config", "user.email", "audit@example.invalid")
        _git(self.repo, "config", "user.name", "Audit Test")
        (self.repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        self.keys: dict[str, Path] = {}
        self.public_keys: dict[str, Path] = {}
        for role in ("authority", "spawn", "lead-v", "adversarial"):
            key = self.base / f"key-{role}"
            subprocess.run(
                ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
                check=True, capture_output=True,
            )
            self.keys[role] = key
            self.public_keys[role] = key.with_suffix(".pub")
        policy = {
            "schema_version": 1,
            "status": "provisioned",
            "identities": {
                role: {
                    "openssh_identity": f"pb-audit-{role}",
                    "public_key_sha256": roster.public_key_sha256(self.public_keys[role]),
                }
                for role in ("authority", "spawn", "lead-v", "adversarial")
            },
        }
        policy_path = self.repo / roster.TRUST_POLICY_PATH
        policy_path.parent.mkdir(parents=True)
        policy_path.write_bytes(roster._canonical(policy) + b"\n")
        _git(self.repo, "add", "seed.txt", roster.TRUST_POLICY_PATH)
        _git(self.repo, "commit", "-m", "seed trust policy")
        self.tooling_commit = _git(self.repo, "rev-parse", "HEAD")
        self.commit = self.tooling_commit
        self.policy, self.policy_sha, self.policy_blob_id = roster.load_trust_policy(
            self.repo, self.tooling_commit
        )
        self.common = self.repo / ".git"
        self.registry_patch = mock.patch.object(
            agent_session, "_git_common_dir", return_value=self.common
        )
        self.registry_patch.start()
        agent_session.bootstrap_initialize_empty()
        self.receipts = self.base / "receipts"
        self.attestations = self.base / "attestations"
        self.roster_path = self.base / "reviewer_roster.jsonl"
        self.contract_path = self.base / "contract.json"
        self.contract_sig = self.base / "contract.json.sig"
        self.spawn_path = self.base / "spawn.json"
        self.spawn_sig = self.base / "spawn.json.sig"
        self.binding_path = self.base / "readiness-binding.json"
        self.binding_sig = self.base / "readiness-binding.json.sig"
        self.audit_contract_path = self.base / "audit-contract.json"
        self.audit_contract_sig = self.base / "audit-contract.json.sig"
        self.director = self._claim("director", [])
        self.lead = self._claim(
            "lead", ["@audit/RUN-1/lead/**"], parent=self.director["id"]
        )
        self.adversarial = self._claim(
            "adversarial", ["@audit/RUN-1/adversarial/**"], parent=self.director["id"]
        )
        self._write_trust()

    def tearDown(self) -> None:
        self.registry_patch.stop()
        self.temp.cleanup()

    def _worktree(self, name: str) -> Path:
        path = self.base / f"wt-{name}"
        _git(self.repo, "worktree", "add", "--detach", str(path), self.commit)
        return path

    def _claim(self, name: str, claims: list[str], parent: str | None = None) -> dict:
        session, conflicts = agent_session.claim(
            name, "audit", claims, branch="HEAD", worktree=str(self._worktree(name)),
            parent_session_id=parent,
        )
        self.assertTrue(session)
        self.assertFalse(conflicts)
        return session

    def _record(
        self, seq: int, session: dict, role: str, previous: str | None,
        *, forced: bool | None = None, parent: str | None | object = ...,
    ) -> dict:
        body = {
            "seq": seq,
            "session_id": session["id"],
            "parent_session_id": (
                session["parent_session_id"] if parent is ... else parent
            ),
            "role": role,
            "forced": session["forced"] if forced is None else forced,
            "spawned_at": session["started_at"],
            "previous_record_sha256": previous,
        }
        return {**body, "record_sha256": roster._sha(roster._canonical(body))}

    def _signed(self, path: Path, value: dict, namespace: str, role: str) -> None:
        path.write_bytes(roster._canonical(value) + b"\n")
        signature = path.with_name(path.name + ".sig")
        signature.unlink(missing_ok=True)
        roster.sign_file(path, signature, self.keys[role], namespace)

    def _write_trust(
        self, *, direct_ancestor: bool = False, forced_director: bool = False,
        pairs: list[dict[str, str]] | None = None,
    ) -> None:
        if direct_ancestor:
            raw = json.loads((self.common / "pb-agent-sessions.json").read_text(encoding="utf-8"))
            for session in raw["sessions"]:
                if session["id"] == self.adversarial["id"]:
                    session["parent_session_id"] = self.lead["id"]
                    session["ancestor_session_ids"] = [self.director["id"], self.lead["id"]]
                    self.adversarial = session
            (self.common / "pb-agent-sessions.json").write_text(json.dumps(raw), encoding="utf-8")
        records: list[dict] = []
        previous = None
        for seq, (session, role, forced, parent) in enumerate(
            [
                (self.director, "neutral-director", forced_director, ...),
                (self.lead, "lead-v", False, ...),
                (
                    self.adversarial,
                    "adversarial",
                    False,
                    self.lead["id"] if direct_ancestor else ...,
                ),
            ],
            1,
        ):
            record = self._record(seq, session, role, previous, forced=forced, parent=parent)
            records.append(record)
            previous = record["record_sha256"]
        self._signed(
            self.spawn_path, {"schema_version": 1, "records": records},
            roster.SPAWN_NAMESPACE, "spawn",
        )
        lead_id = roster.deterministic_reviewer_id(
            "RUN-1", self.lead["id"], self.commit, "snapshot-1"
        )
        adversarial_id = roster.deterministic_reviewer_id(
            "RUN-1", self.adversarial["id"], self.commit, "snapshot-1"
        )
        reviewers = [
            {
                "reviewer_id": lead_id,
                "session_id": self.lead["id"],
                "role": "lead-v",
                "output_claims": ["@audit/RUN-1/lead/**"],
                "review_scope": ["services/**"],
            },
            {
                "reviewer_id": adversarial_id,
                "session_id": self.adversarial["id"],
                "role": "adversarial",
                "output_claims": ["@audit/RUN-1/adversarial/**"],
                "review_scope": ["services/**"],
            },
        ]
        contract = {
            "schema_version": 1,
            "run_id": "RUN-1",
            "audited_commit": self.commit,
            "snapshot_id": "snapshot-1",
            "tooling_commit": self.tooling_commit,
            "trust_policy_blob_sha256": self.policy_sha,
            "trust_policy_blob_id": self.policy_blob_id,
            "spawn_journal_sha256": roster._sha(self.spawn_path.read_bytes()),
            "reviewers": reviewers,
            "reviewer_pairs": pairs if pairs is not None else [{
                "pair_id": "P-services", "reviewer_a": lead_id,
                "reviewer_b": adversarial_id,
                "output_claim_a": "@audit/RUN-1/lead/**",
                "output_claim_b": "@audit/RUN-1/adversarial/**",
                "review_scope": "services/**",
            }],
            "assignments": [
                {
                    "assignment_id": "A-services",
                    "pair_id": "P-services",
                    "reviewer_id": lead_id,
                    "role": "lead-v",
                    "pass": "A",
                    "output_claim": "@audit/RUN-1/lead/**",
                    "review_scope": "services/**",
                },
                {
                    "assignment_id": "B-services",
                    "pair_id": "P-services",
                    "reviewer_id": adversarial_id,
                    "role": "adversarial",
                    "pass": "B",
                    "output_claim": "@audit/RUN-1/adversarial/**",
                    "review_scope": "services/**",
                },
            ],
            "required_signoffs": [
                {"reviewer_id": lead_id, "role": "lead-v"},
                {"reviewer_id": adversarial_id, "role": "adversarial"},
            ],
        }
        self._resign_contract(contract)

    def _resign_contract(self, contract: dict) -> None:
        self._signed(self.contract_path, contract, roster.CONTRACT_NAMESPACE, "authority")
        binding = {
            "schema_version": 1, "tooling_commit": self.tooling_commit,
            "trust_policy_blob_sha256": self.policy_sha,
            "contract_sha256": roster._sha(self.contract_path.read_bytes()),
            "run_id": "RUN-1", "audited_commit": self.commit,
            "snapshot_id": "snapshot-1",
        }
        self._signed(self.binding_path, binding, roster.READINESS_NAMESPACE, "authority")
        self.binding_sha = roster._sha(self.binding_path.read_bytes())
        policy_raw = roster._canonical(self.policy) + b"\n"
        sources = {
            "reviewer-trust-policy": ("reviewer/trust_policy.json", policy_raw),
            "reviewer-contract": ("reviewer/contract.json", self.contract_path.read_bytes()),
            "reviewer-readiness-binding": (
                "reviewer/readiness_binding.json", self.binding_path.read_bytes()
            ),
            "reviewer-spawn-journal": (
                "reviewer/spawn_journal.json", self.spawn_path.read_bytes()
            ),
        }
        for key in sorted(roster.AUDIT_ARTIFACT_KEYS - set(sources)):
            sources[key] = (f"common/{key}.json", roster._canonical({"kind": key}) + b"\n")
        artifacts = {}
        for key, (ref, raw) in sources.items():
            digest = roster._sha(raw)
            artifacts[key] = {
                "artifact_id": f"sha256:{digest}", "ref": ref, "sha256": digest,
                "bytes": len(raw), "record_count": roster._record_count(ref, raw),
            }
        audit_contract = {
            "schema_version": 1, "plan_id": roster.PLAN_ID,
            "run_id": "RUN-1", "audited_commit": self.commit,
            "tooling_commit": self.tooling_commit, "snapshot_id": "snapshot-1",
            "frozen_at": "2026-08-15T00:00:00+00:00",
            "expires_at": "2026-08-16T00:00:00+00:00", "artifacts": artifacts,
        }
        audit_contract["contract_sha256"] = roster._sha(roster._canonical(audit_contract))
        self._signed(
            self.audit_contract_path, audit_contract,
            roster.AUDIT_CONTRACT_NAMESPACE, "authority",
        )
        self.audit_contract_sha = audit_contract["contract_sha256"]
        self.audit_contract_file_sha = roster._sha(self.audit_contract_path.read_bytes())

    def _resign_spawn_journal(self, journal: dict) -> None:
        previous = None
        for row in journal["records"]:
            row["previous_record_sha256"] = previous
            body = {
                key: row[key]
                for key in (
                    "seq", "session_id", "parent_session_id", "role", "forced",
                    "spawned_at", "previous_record_sha256",
                )
            }
            row["record_sha256"] = roster._sha(roster._canonical(body))
            previous = row["record_sha256"]
        self._signed(
            self.spawn_path, journal, roster.SPAWN_NAMESPACE, "spawn"
        )
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        contract["spawn_journal_sha256"] = roster._sha(
            self.spawn_path.read_bytes()
        )
        self._resign_contract(contract)

    def _trust_args(self) -> dict:
        return {
            "contract_path": self.contract_path,
            "contract_signature": self.contract_sig,
            "spawn_journal_path": self.spawn_path,
            "spawn_journal_signature": self.spawn_sig,
            "readiness_binding_path": self.binding_path,
            "readiness_binding_signature": self.binding_sig,
            "expected_readiness_binding_sha256": self.binding_sha,
            "tooling_commit": self.tooling_commit,
            "audit_contract_path": self.audit_contract_path,
            "audit_contract_signature": self.audit_contract_sig,
            "expected_audit_contract_sha256": self.audit_contract_sha,
            "authority_public_key_path": self.public_keys["authority"],
            "spawn_public_key_path": self.public_keys["spawn"],
            "lead_v_public_key_path": self.public_keys["lead-v"],
            "adversarial_public_key_path": self.public_keys["adversarial"],
        }

    def _cli_trust_args(self) -> list[str]:
        trust = self._trust_args()
        options = {
            "--contract": trust["contract_path"],
            "--contract-signature": trust["contract_signature"],
            "--spawn-journal": trust["spawn_journal_path"],
            "--spawn-journal-signature": trust["spawn_journal_signature"],
            "--readiness-binding": trust["readiness_binding_path"],
            "--readiness-binding-signature": trust["readiness_binding_signature"],
            "--readiness-binding-sha256": trust[
                "expected_readiness_binding_sha256"
            ],
            "--tooling-commit": trust["tooling_commit"],
            "--audit-contract": trust["audit_contract_path"],
            "--audit-contract-signature": trust["audit_contract_signature"],
            "--audit-contract-sha256": trust["expected_audit_contract_sha256"],
            "--authority-public-key": trust["authority_public_key_path"],
            "--spawn-public-key": trust["spawn_public_key_path"],
            "--lead-v-public-key": trust["lead_v_public_key_path"],
            "--adversarial-public-key": trust["adversarial_public_key_path"],
        }
        return [value for option, path in options.items() for value in (option, str(path))]

    def _enroll(self, session: dict) -> dict:
        return roster.enroll(
            root=self.repo, session_id=session["id"], receipts_dir=self.receipts,
            roster_path=self.roster_path, signing_key=self.keys["spawn"],
            **self._trust_args()
        )

    def _enroll_all(self) -> tuple[dict, dict]:
        return self._enroll(self.lead), self._enroll(self.adversarial)

    def _verify(self) -> list[str]:
        return roster.verify_roster(
            self.repo, self.roster_path, self.receipts, **self._trust_args()
        )

    def test_positive_minimal(self) -> None:
        self._enroll_all()
        self.assertEqual([], self._verify())

    def test_missing_required_rejected(self) -> None:
        self.contract_sig.unlink()
        self.assertTrue(self._verify())

    def test_tampered_binding_rejected(self) -> None:
        lead, _ = self._enroll_all()
        receipt = self.receipts / lead["session_receipt_ref"]
        value = json.loads(receipt.read_text(encoding="utf-8"))
        value["role"] = "adversarial"
        receipt.write_bytes(roster._canonical(value) + b"\n")
        self.assertTrue(self._verify())

    def test_duplicate_or_foreign_id_rejected(self) -> None:
        self._enroll_all()
        rows = self.roster_path.read_text(encoding="utf-8").splitlines()
        self.roster_path.write_text("\n".join([*rows, rows[0]]) + "\n", encoding="utf-8")
        self.assertTrue(self._verify())

    def test_same_session_or_ancestor_rejected(self) -> None:
        self._write_trust(direct_ancestor=True)
        self._enroll_all()
        errors = self._verify()
        self.assertTrue(any("Vorfahr/Nachfahre" in error for error in errors), errors)

    def test_empty_pair_contract_and_free_offline_inputs_rejected(self) -> None:
        self._write_trust(pairs=[])
        self.assertTrue(self._verify())
        with self.assertRaises(TypeError):
            roster.verify_roster(self.repo, self.roster_path, self.receipts)

    def test_registry_claim_and_forced_ancestor_rejected(self) -> None:
        raw = json.loads((self.common / "pb-agent-sessions.json").read_text(encoding="utf-8"))
        for session in raw["sessions"]:
            if session["id"] == self.lead["id"]:
                session["claims"] = ["@audit/RUN-1/wrong/**"]
        (self.common / "pb-agent-sessions.json").write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(roster.ContractError, "Registry-Claims"):
            self._enroll(self.lead)
        self._write_trust(forced_director=True)
        with self.assertRaisesRegex(roster.ContractError, "forced"):
            self._enroll(self.adversarial)

    def test_stale_session_rejected_from_canonical_registry(self) -> None:
        raw = json.loads((self.common / "pb-agent-sessions.json").read_text(encoding="utf-8"))
        for session in raw["sessions"]:
            if session["id"] == self.lead["id"]:
                session["heartbeat"] = "2000-01-01T00:00:00+00:00"
        (self.common / "pb-agent-sessions.json").write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(roster.ContractError, "stale/tot"):
            self._enroll(self.lead)

    def test_wrong_external_signing_key_cannot_publish_receipt(self) -> None:
        wrong = self.base / "wrong-anchor"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(wrong)],
            check=True, capture_output=True,
        )
        with self.assertRaises(roster.ContractError):
            roster.enroll(
                root=self.repo, session_id=self.lead["id"],
                receipts_dir=self.receipts, roster_path=self.roster_path,
                signing_key=wrong, **self._trust_args(),
            )
        self.assertFalse(self.roster_path.exists())
        self.assertFalse(any(self.receipts.glob("*")))

    def test_role_assignment_claim_scope_contract_is_exact(self) -> None:
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        contract["assignments"][0]["review_scope"] = "ui/**"
        self._resign_contract(contract)
        errors = self._verify()
        self.assertTrue(any("Claim/Scope" in error for error in errors), errors)

    def test_signed_contract_unhashable_fields_raise_contract_error(self) -> None:
        mutations = {
            "reviewer-role": lambda c: c["reviewers"][0].__setitem__("role", []),
            "reviewer-id": lambda c: c["reviewers"][0].__setitem__(
                "reviewer_id", []
            ),
            "reviewer-output-claim": lambda c: c["reviewers"][0].__setitem__(
                "output_claims", [[]]
            ),
            "reviewer-scope": lambda c: c["reviewers"][0].__setitem__(
                "review_scope", [[]]
            ),
            "pair-reviewer": lambda c: c["reviewer_pairs"][0].__setitem__(
                "reviewer_a", []
            ),
            "pair-id": lambda c: c["reviewer_pairs"][0].__setitem__("pair_id", []),
            "assignment-id": lambda c: c["assignments"][0].__setitem__(
                "assignment_id", []
            ),
            "assignment-reviewer": lambda c: c["assignments"][0].__setitem__(
                "reviewer_id", []
            ),
            "assignment-pair": lambda c: c["assignments"][0].__setitem__(
                "pair_id", []
            ),
            "assignment-pass": lambda c: c["assignments"][0].__setitem__(
                "pass", []
            ),
            "signoff-reviewer": lambda c: c["required_signoffs"][0].__setitem__(
                "reviewer_id", []
            ),
            "signoff-role": lambda c: c["required_signoffs"][0].__setitem__(
                "role", []
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                self._write_trust()
                contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
                mutate(contract)
                self._resign_contract(contract)
                with self.assertRaises(roster.ContractError):
                    self._enroll(self.lead)
                self.assertFalse(self.roster_path.exists())
                self.assertFalse(
                    self.receipts.exists() and any(self.receipts.rglob("*"))
                )

    def test_cli_enroll_unhashable_role_returns_json_exit_two(self) -> None:
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        contract["reviewers"][0]["role"] = []
        self._resign_contract(contract)
        output = io.StringIO()
        argv = [
            "enroll",
            "--root",
            str(self.repo),
            *self._cli_trust_args(),
            "--roster",
            str(self.roster_path),
            "--receipts-dir",
            str(self.receipts),
            "--session-id",
            self.lead["id"],
            "--signing-key",
            str(self.keys["spawn"]),
        ]
        with mock.patch("sys.stdout", output):
            code = roster.main(argv)
        payload = json.loads(output.getvalue())
        self.assertEqual(2, code)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["errors"])
        self.assertNotIn("Traceback", output.getvalue())
        self.assertFalse(self.roster_path.exists())

    def test_signed_spawn_unhashable_fields_raise_contract_error(self) -> None:
        mutations = {
            "role": lambda row: row.__setitem__("role", []),
            "parent_session_id": lambda row: row.__setitem__(
                "parent_session_id", []
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                self._write_trust()
                journal = json.loads(
                    self.spawn_path.read_text(encoding="utf-8")
                )
                mutate(journal["records"][1])
                self._resign_spawn_journal(journal)
                with self.assertRaises(roster.ContractError):
                    self._enroll(self.lead)
                self.assertFalse(self.roster_path.exists())
                self.assertFalse(
                    self.receipts.exists() and any(self.receipts.rglob("*"))
                )

    def test_registry_unhashable_claim_fails_before_enrollment_mutation(self) -> None:
        registry_path = self.common / "pb-agent-sessions.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        for session in registry["sessions"]:
            if session["id"] == self.lead["id"]:
                session["claims"] = [[]]
        registry_path.write_text(json.dumps(registry), encoding="utf-8")
        with self.assertRaises(roster.ContractError):
            self._enroll(self.lead)
        self.assertFalse(self.roster_path.exists())
        self.assertFalse(
            self.receipts.exists() and any(self.receipts.rglob("*"))
        )

    def test_finalize_inputs_fail_before_lock_or_attestation_mutation(self) -> None:
        base = {
            "root": self.repo,
            "session_id": self.lead["id"],
            "role": "lead-v",
            "basis_sha256": "a" * 64,
            "verdict": "pass",
            "roster_path": self.roster_path,
            "receipts_dir": self.receipts,
            "attestations_dir": self.attestations,
            "signing_key": self.keys["lead-v"],
            **self._trust_args(),
        }
        for field in ("session_id", "role", "basis_sha256", "verdict"):
            with self.subTest(field=field):
                with mock.patch.object(
                    roster, "_FileLock", side_effect=AssertionError("lock reached")
                ):
                    with self.assertRaises(roster.ContractError):
                        roster.finalize_signoff(**{**base, field: []})
                self.assertFalse(self.attestations.exists())

    def test_cli_expected_data_io_errors_return_json_exit_two(self) -> None:
        factories = {
            "os": lambda: PermissionError("permission denied"),
            "unicode": lambda: UnicodeDecodeError(
                "utf-8", b"\xff", 0, 1, "invalid byte"
            ),
            "json": lambda: json.JSONDecodeError("invalid json", "{", 1),
        }
        commands = {
            "enroll": (
                "enroll",
                [
                    "--roster", str(self.roster_path),
                    "--receipts-dir", str(self.receipts),
                    "--session-id", self.lead["id"],
                    "--signing-key", str(self.keys["spawn"]),
                ],
            ),
            "finalize": (
                "finalize_signoff",
                [
                    "--roster", str(self.roster_path),
                    "--receipts-dir", str(self.receipts),
                    "--attestations-dir", str(self.attestations),
                    "--session-id", self.lead["id"],
                    "--role", "lead-v",
                    "--basis-sha256", "a" * 64,
                    "--verdict", "pass",
                    "--signing-key", str(self.keys["lead-v"]),
                ],
            ),
        }
        for command, (target, command_args) in commands.items():
            for error_name, factory in factories.items():
                with self.subTest(command=command, error=error_name):
                    error = factory()
                    output = io.StringIO()
                    argv = [
                        command,
                        "--root", str(self.repo),
                        *self._cli_trust_args(),
                        *command_args,
                    ]
                    with (
                        mock.patch.object(roster, target, side_effect=error),
                        mock.patch("sys.stdout", output),
                    ):
                        code = roster.main(argv)
                    payload = json.loads(output.getvalue())
                    self.assertEqual(2, code)
                    self.assertFalse(payload["ok"])
                    self.assertIn(str(error), payload["errors"])
                    self.assertNotIn("Traceback", output.getvalue())
                    self.assertFalse(self.roster_path.exists())
                    self.assertFalse(self.attestations.exists())

    def test_enroll_cleanup_preserves_primary_signing_error(self) -> None:
        primary = PermissionError("primary")
        receipt = self.receipts / f"{self.lead['id']}.json"
        signature = self.receipts / f"{self.lead['id']}.json.sig"
        original_unlink = Path.unlink
        cleanup_calls: list[Path] = []

        def fail_sign(*_args, **_kwargs) -> None:
            signature.write_bytes(b"partial")
            raise primary

        def cleanup(path: Path, *args, **kwargs) -> None:
            cleanup_calls.append(path)
            if path == receipt:
                raise PermissionError("cleanup")
            original_unlink(path, *args, **kwargs)

        with (
            mock.patch.object(roster, "sign_file", side_effect=fail_sign),
            mock.patch.object(Path, "unlink", autospec=True, side_effect=cleanup),
        ):
            with self.assertRaises(PermissionError) as raised:
                self._enroll(self.lead)
        self.assertIs(primary, raised.exception)
        self.assertEqual([receipt, signature], cleanup_calls)
        self.assertTrue(receipt.exists())
        self.assertFalse(signature.exists())
        self.assertFalse(self.roster_path.exists())

    def test_finalize_cleanup_preserves_primary_signing_error(self) -> None:
        self._enroll_all()
        primary = PermissionError("primary")
        path = self.attestations / f"lead-v-{self.lead['id']}.json"
        signature = self.attestations / f"lead-v-{self.lead['id']}.json.sig"
        original_unlink = Path.unlink
        cleanup_calls: list[Path] = []

        def fail_sign(*_args, **_kwargs) -> None:
            signature.write_bytes(b"partial")
            raise primary

        def cleanup(candidate: Path, *args, **kwargs) -> None:
            cleanup_calls.append(candidate)
            if candidate == path:
                raise PermissionError("cleanup")
            original_unlink(candidate, *args, **kwargs)

        with (
            mock.patch.object(roster, "sign_file", side_effect=fail_sign),
            mock.patch.object(Path, "unlink", autospec=True, side_effect=cleanup),
        ):
            with self.assertRaises(PermissionError) as raised:
                roster.finalize_signoff(
                    root=self.repo,
                    session_id=self.lead["id"],
                    role="lead-v",
                    basis_sha256="a" * 64,
                    verdict="pass",
                    roster_path=self.roster_path,
                    receipts_dir=self.receipts,
                    attestations_dir=self.attestations,
                    signing_key=self.keys["lead-v"],
                    **self._trust_args(),
                )
        self.assertIs(primary, raised.exception)
        self.assertEqual([path, signature], cleanup_calls)
        self.assertTrue(path.exists())
        self.assertFalse(signature.exists())

    def test_nested_output_shard_prefix_overlap_rejected(self) -> None:
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        nested = "@audit/RUN-1/lead/sub/**"
        contract["reviewers"][1]["output_claims"] = [nested]
        contract["assignments"][1]["output_claim"] = nested
        self._resign_contract(contract)
        errors = self._verify()
        self.assertTrue(any("ueberlappen" in error for error in errors), errors)

    def test_stale_lock_and_signed_orphan_recovery(self) -> None:
        lead = self._enroll(self.lead)
        self.roster_path.unlink()
        lock = self.roster_path.with_name(self.roster_path.name + ".lock")
        lock.write_bytes(roster._canonical({
            "token": "dead", "pid": 999999,
            "heartbeat": time.time() - roster.LOCK_STALE_SECONDS - 5,
        }) + b"\n")
        recovered = self._enroll(self.lead)
        self.assertEqual(lead["session_receipt_sha256"], recovered["session_receipt_sha256"])

    def test_half_orphan_is_quarantined_then_retried(self) -> None:
        self.receipts.mkdir()
        orphan = self.receipts / f"{self.lead['id']}.json"
        orphan.write_text("partial", encoding="utf-8")
        enrolled = self._enroll(self.lead)
        self.assertTrue((self.receipts / enrolled["session_receipt_ref"]).is_file())
        quarantined = list((self.receipts / "quarantine").iterdir())
        self.assertEqual(1, len(quarantined))
        self.assertIn(".orphan", quarantined[0].name)

    def test_workspace_policy_cannot_replace_tooling_commit_blob(self) -> None:
        workspace_policy = self.repo / roster.TRUST_POLICY_PATH
        workspace_policy.write_text("{}\n", encoding="utf-8")
        self._enroll_all()
        self.assertEqual([], self._verify())

    def test_preflight_audit_contract_external_sha_and_artifact_fk_are_exact(self) -> None:
        bad_args = self._trust_args()
        bad_args["expected_audit_contract_sha256"] = "0" * 64
        with self.assertRaisesRegex(roster.ContractError, "extern erwarteter Body-SHA"):
            roster.enroll(
                root=self.repo, session_id=self.lead["id"], receipts_dir=self.receipts,
                roster_path=self.roster_path, signing_key=self.keys["spawn"], **bad_args,
            )
        value = json.loads(self.audit_contract_path.read_text(encoding="utf-8"))
        value["artifacts"]["reviewer-contract"]["bytes"] += 1
        body = {key: item for key, item in value.items() if key != "contract_sha256"}
        value["contract_sha256"] = roster._sha(roster._canonical(body))
        self._signed(
            self.audit_contract_path, value, roster.AUDIT_CONTRACT_NAMESPACE, "authority"
        )
        self.audit_contract_sha = value["contract_sha256"]
        self.audit_contract_file_sha = roster._sha(self.audit_contract_path.read_bytes())
        self.assertTrue(self._verify())

    def test_audit_contract_requires_exact_global_fourteen_keys(self) -> None:
        for mutation in ("missing", "extra"):
            with self.subTest(mutation=mutation):
                value = json.loads(self.audit_contract_path.read_text(encoding="utf-8"))
                if mutation == "missing":
                    del value["artifacts"]["requirements-universe"]
                else:
                    value["artifacts"]["foreign"] = dict(
                        value["artifacts"]["requirements-universe"]
                    )
                body = {key: item for key, item in value.items() if key != "contract_sha256"}
                value["contract_sha256"] = roster._sha(roster._canonical(body))
                self._signed(
                    self.audit_contract_path, value,
                    roster.AUDIT_CONTRACT_NAMESPACE, "authority",
                )
                self.audit_contract_sha = value["contract_sha256"]
                self.assertTrue(self._verify())
                self._write_trust()

    def test_external_pin_is_body_sha_not_raw_file_sha(self) -> None:
        self.assertNotEqual(self.audit_contract_sha, self.audit_contract_file_sha)
        bad = self._trust_args()
        bad["expected_audit_contract_sha256"] = self.audit_contract_file_sha
        with self.assertRaisesRegex(roster.ContractError, "Body-SHA"):
            roster.enroll(
                root=self.repo, session_id=self.lead["id"], receipts_dir=self.receipts,
                roster_path=self.roster_path, signing_key=self.keys["spawn"], **bad,
            )

    def test_descriptor_schema_and_own_bytes_are_fail_closed(self) -> None:
        mutations = (
            lambda item: item.update(extra=True),
            lambda item: item.update(sha256="0" * 64),
            lambda item: item.update(record_count=True),
            lambda item: item.update(ref="reviewer/renamed-contract.json"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                value = json.loads(self.audit_contract_path.read_text(encoding="utf-8"))
                mutate(value["artifacts"]["reviewer-contract"])
                body = {key: item for key, item in value.items() if key != "contract_sha256"}
                value["contract_sha256"] = roster._sha(roster._canonical(body))
                self._signed(
                    self.audit_contract_path, value,
                    roster.AUDIT_CONTRACT_NAMESPACE, "authority",
                )
                self.audit_contract_sha = value["contract_sha256"]
                self.assertTrue(self._verify())
                self._write_trust()

    def test_other_domain_descriptors_are_structural_not_reopened_by_reviewer(self) -> None:
        self._enroll_all()
        value = json.loads(self.audit_contract_path.read_text(encoding="utf-8"))
        descriptor = value["artifacts"]["requirements-universe"]
        descriptor["sha256"] = "1" * 64
        descriptor["artifact_id"] = "sha256:" + descriptor["sha256"]
        descriptor["bytes"] = 999
        descriptor["record_count"] = 77
        body = {key: item for key, item in value.items() if key != "contract_sha256"}
        value["contract_sha256"] = roster._sha(roster._canonical(body))
        self._signed(
            self.audit_contract_path, value,
            roster.AUDIT_CONTRACT_NAMESPACE, "authority",
        )
        self.audit_contract_sha = value["contract_sha256"]
        self.assertEqual([], self._verify())

    def test_record_count_common_matrix(self) -> None:
        cases = (
            ("x.jsonl", b'{"a":1}\n\n{"b":2}\n', 2),
            ("x.json", b"[1,2,3]", 3),
            ("x.json", b'{"records":[{},{}]}', 2),
            ("x.json", b'{"other":true}', 1),
            ("x.bin", b"not-json", 1),
        )
        for ref, raw, expected in cases:
            with self.subTest(ref=ref, raw=raw):
                self.assertEqual(expected, roster._record_count(ref, raw))
        for ref, raw in (("x.jsonl", b"[]\n"), ("x.json", b"{")):
            with self.subTest(ref=ref, raw=raw):
                with self.assertRaises(roster.ContractError):
                    roster._record_count(ref, raw)

    def test_evidence_attachment_export_has_exact_receipt_and_signoff_closure(self) -> None:
        rows = self._enroll_all()
        basis = "a" * 64
        for session, role in ((self.lead, "lead-v"), (self.adversarial, "adversarial")):
            roster.finalize_signoff(
                root=self.repo, session_id=session["id"], role=role,
                basis_sha256=basis, verdict="pass", roster_path=self.roster_path,
                receipts_dir=self.receipts, attestations_dir=self.attestations,
                signing_key=self.keys[role], **self._trust_args(),
            )
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        snapshot = self._export_attachment_snapshot(contract, basis)
        attachments = snapshot.descriptors
        expected_keys = set()
        for row in rows:
            sid = row["session_id"]
            expected_keys |= {
                f"reviewer-enrollment-receipt:{sid}",
                f"reviewer-enrollment-signature:{sid}",
            }
        for required in contract["required_signoffs"]:
            sid = next(
                spec["session_id"] for spec in contract["reviewers"]
                if spec["reviewer_id"] == required["reviewer_id"]
            )
            role = required["role"]
            expected_keys |= {
                f"reviewer-signoff:{role}:{sid}",
                f"reviewer-signoff-signature:{role}:{sid}",
            }
        self.assertEqual(expected_keys, set(attachments))
        self.assertTrue(all(set(item) == roster.DESCRIPTOR_FIELDS for item in attachments.values()))
        with self.assertRaises(roster.ContractError):
            self._export_attachment_snapshot(contract, "b" * 64)
        orphan = self.attestations / "orphan.json"
        orphan.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(roster.ContractError, "Dateimenge"):
            self._export_attachment_snapshot(contract, basis)

    def _export_attachment_snapshot(self, contract: dict, basis: str):
        trust = self._trust_args()
        return roster.export_reviewer_evidence_attachments(
            self.repo, self.tooling_commit,
            self.roster_path, self.receipts, self.attestations, contract,
            basis_sha256=basis,
            spawn_public_key_path=self.public_keys["spawn"],
            lead_v_public_key_path=self.public_keys["lead-v"],
            adversarial_public_key_path=self.public_keys["adversarial"],
            contract_path=trust["contract_path"],
            contract_signature=trust["contract_signature"],
            spawn_journal_path=trust["spawn_journal_path"],
            spawn_journal_signature=trust["spawn_journal_signature"],
            readiness_binding_path=trust["readiness_binding_path"],
            readiness_binding_signature=trust["readiness_binding_signature"],
            expected_readiness_binding_sha256=trust[
                "expected_readiness_binding_sha256"
            ],
            audit_contract_path=trust["audit_contract_path"],
            audit_contract_signature=trust["audit_contract_signature"],
            expected_audit_contract_sha256=trust[
                "expected_audit_contract_sha256"
            ],
            authority_public_key_path=trust["authority_public_key_path"],
        )

    def _signed_attachment_snapshot(self, basis: str = "a" * 64):
        rows = self._enroll_all()
        for session, role in ((self.lead, "lead-v"), (self.adversarial, "adversarial")):
            roster.finalize_signoff(
                root=self.repo, session_id=session["id"], role=role,
                basis_sha256=basis, verdict="pass", roster_path=self.roster_path,
                receipts_dir=self.receipts, attestations_dir=self.attestations,
                signing_key=self.keys[role], **self._trust_args(),
            )
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        snapshot = self._export_attachment_snapshot(contract, basis)
        return rows, contract, snapshot

    def test_attachment_export_rejects_enrollment_and_signoff_signature_tamper(self) -> None:
        self._signed_attachment_snapshot()
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        cases = (
            self.receipts / f"{self.lead['id']}.json.sig",
            self.attestations / f"lead-v-{self.lead['id']}.json.sig",
        )
        for path in cases:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
                with self.assertRaises(roster.ContractError):
                    self._export_attachment_snapshot(contract, "a" * 64)
                path.write_bytes(original)

    def test_attachment_export_hostile_roster_types_fail_closed_without_crash(self) -> None:
        self._signed_attachment_snapshot()
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        original = [json.loads(line) for line in self.roster_path.read_text().splitlines()]
        mutations: list[tuple[str, object]] = [
            (field, hostile)
            for field in sorted(roster.ROSTER_FIELDS)
            for hostile in ([], {})
        ]
        for field, hostile in mutations:
            with self.subTest(field=field, hostile=type(hostile).__name__):
                rows = [dict(row) for row in original]
                rows[0][field] = hostile
                self.roster_path.write_bytes(
                    b"".join(roster._canonical(row) + b"\n" for row in rows)
                )
                with self.assertRaises(roster.ContractError):
                    self._export_attachment_snapshot(contract, "a" * 64)
        for field in sorted(roster.ROSTER_FIELDS):
            with self.subTest(missing=field):
                rows = [dict(row) for row in original]
                rows[0].pop(field)
                self.roster_path.write_bytes(
                    b"".join(roster._canonical(row) + b"\n" for row in rows)
                )
                with self.assertRaises(roster.ContractError):
                    self._export_attachment_snapshot(contract, "a" * 64)
        rows = [dict(row) for row in original]
        rows[0]["extra"] = True
        self.roster_path.write_bytes(
            b"".join(roster._canonical(row) + b"\n" for row in rows)
        )
        with self.assertRaises(roster.ContractError):
            self._export_attachment_snapshot(contract, "a" * 64)
        self.roster_path.write_bytes(
            b"".join(roster._canonical(row) + b"\n" for row in original)
        )

    def test_forged_resealed_roster_cannot_reach_completion_closure(self) -> None:
        self._signed_attachment_snapshot()
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        original = [json.loads(line) for line in self.roster_path.read_text().splitlines()]
        for field, value in (
            ("role", "adversarial"), ("run_id", "FORGED-RUN"),
            ("audited_commit", "f" * 40), ("tooling_commit", "f" * 40),
            ("snapshot_id", "FORGED-SNAPSHOT"),
            ("contract_sha256", "f" * 64), ("reviewer_id", "REV-FORGED"),
            ("session_id", "f" * 32),
            ("session_receipt_ref", "forged.json"),
            ("session_receipt_signature_ref", "forged.json.sig"),
            ("session_receipt_sha256", "f" * 64),
        ):
            with self.subTest(field=field):
                rows = [dict(row) for row in original]
                rows[0][field] = value
                self.roster_path.write_bytes(
                    b"".join(roster._canonical(row) + b"\n" for row in rows)
                )
                with self.assertRaises(roster.ContractError):
                    self._export_attachment_snapshot(contract, "a" * 64)
        self.roster_path.write_bytes(
            b"".join(roster._canonical(row) + b"\n" for row in original)
        )

    def test_verified_snapshot_passes_real_completion_closure_without_reread(self) -> None:
        rows, contract, snapshot = self._signed_attachment_snapshot()
        receipt = self.receipts / f"{self.lead['id']}.json"
        receipt.write_bytes(b"mutated-after-export")
        bundle = self.base / "completion-closure"
        bundle.mkdir()
        for ref, payload in snapshot.payloads.items():
            target = bundle / ref
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
        contract_ref = "reviewer/contract.json"
        contract_raw = roster._canonical(contract) + b"\n"
        contract_target = bundle / contract_ref
        contract_target.parent.mkdir(parents=True)
        contract_target.write_bytes(contract_raw)
        audit_artifacts = {
            "reviewer-contract": roster.artifact_descriptor(contract_ref, contract_raw)
        }
        evidence_artifacts = {
            key: roster.artifact_descriptor(f"records/{key}.jsonl", b"")
            for key in completion.EVIDENCE_STATIC_KEYS
        }
        evidence_artifacts.update({
            key: dict(value) for key, value in snapshot.descriptors.items()
        })
        completion._validate_attachment_closure(
            bundle, audit_artifacts, evidence_artifacts,
            {
                "feature-state-evidence": [], "symbol-state-evidence": [],
                "runtime-evidence": [], "reviewer-roster": list(rows),
            },
        )

    def test_exact_pair_assignment_bijection_rejects_duplicate_reviewer(self) -> None:
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        contract["assignments"].append(dict(contract["assignments"][0], assignment_id="dup"))
        self._resign_contract(contract)
        self.assertTrue(any("doppelt" in error for error in self._verify()))

    def test_finalize_rechecks_stable_registry_and_worktree(self) -> None:
        self._enroll_all()
        raw = json.loads((self.common / "pb-agent-sessions.json").read_text(encoding="utf-8"))
        for session in raw["sessions"]:
            if session["id"] == self.lead["id"]:
                session["task"] = "drifted"
        (self.common / "pb-agent-sessions.json").write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(roster.ContractError, "drifteten"):
            roster.finalize_signoff(
                root=self.repo, session_id=self.lead["id"], role="lead-v",
                basis_sha256="a" * 64, verdict="pass", roster_path=self.roster_path,
                receipts_dir=self.receipts, attestations_dir=self.attestations,
                signing_key=self.keys["lead-v"], **self._trust_args(),
            )

    def test_role_signoff_key_is_not_interchangeable(self) -> None:
        self._enroll_all()
        with self.assertRaises(roster.ContractError):
            roster.finalize_signoff(
                root=self.repo, session_id=self.lead["id"], role="lead-v",
                basis_sha256="a" * 64, verdict="pass", roster_path=self.roster_path,
                receipts_dir=self.receipts, attestations_dir=self.attestations,
                signing_key=self.keys["adversarial"], **self._trust_args(),
            )
        self.assertFalse(any(self.attestations.glob("*")))

    def test_signoff_half_orphan_is_quarantined_then_retried(self) -> None:
        self._enroll_all()
        self.attestations.mkdir()
        orphan = self.attestations / f"lead-v-{self.lead['id']}.json"
        orphan.write_text("partial", encoding="utf-8")
        result = roster.finalize_signoff(
            root=self.repo, session_id=self.lead["id"], role="lead-v",
            basis_sha256="a" * 64, verdict="pass", roster_path=self.roster_path,
            receipts_dir=self.receipts, attestations_dir=self.attestations,
            signing_key=self.keys["lead-v"], **self._trust_args(),
        )
        self.assertTrue(result.is_file())
        quarantined = list((self.attestations / "quarantine").iterdir())
        self.assertEqual(1, len(quarantined))
        self.assertIn(".orphan", quarantined[0].name)

    def test_complete_exact_signoff_recovers_but_mismatched_pair_fails_closed(self) -> None:
        self._enroll_all()
        args = dict(
            root=self.repo, session_id=self.lead["id"], role="lead-v",
            basis_sha256="a" * 64, verdict="pass", roster_path=self.roster_path,
            receipts_dir=self.receipts, attestations_dir=self.attestations,
            signing_key=self.keys["lead-v"], **self._trust_args(),
        )
        first = roster.finalize_signoff(**args)
        self.assertEqual(first, roster.finalize_signoff(**args))
        with self.assertRaisesRegex(roster.ContractError, "existierende Signoff"):
            roster.finalize_signoff(**{**args, "basis_sha256": "b" * 64})

    def test_receipt_extra_field_and_naive_timestamp_rejected(self) -> None:
        lead = self._enroll(self.lead)
        receipt = self.receipts / lead["session_receipt_ref"]
        signature = receipt.with_name(receipt.name + ".sig")
        value = json.loads(receipt.read_text(encoding="utf-8"))
        value["enrolled_at"] = "2026-08-15T12:00:00"
        value["extra"] = True
        signature.unlink()
        receipt.write_bytes(roster._canonical(value) + b"\n")
        roster.sign_file(receipt, signature, self.keys["spawn"], roster.ENROLLMENT_NAMESPACE)
        self._enroll(self.adversarial)
        self.assertTrue(self._verify())

    def test_final_verify_after_session_and_worktree_deleted(self) -> None:
        self._enroll_all()
        for session in (self.lead, self.adversarial):
            self.assertTrue(agent_session.release(session["id"]))
            _git(self.repo, "worktree", "remove", "--force", session["worktree"])
        self.assertEqual([], self._verify())

    def test_live_finalize_and_signed_bundle(self) -> None:
        self._enroll_all()
        basis = "a" * 64
        with self.assertRaisesRegex(roster.ContractError, "required signoff"):
            roster.finalize_signoff(
                root=self.repo, session_id=self.lead["id"], role="adversarial",
                basis_sha256=basis, verdict="pass", roster_path=self.roster_path,
                receipts_dir=self.receipts, attestations_dir=self.attestations,
                signing_key=self.keys["lead-v"], **self._trust_args(),
            )
        for session, role in ((self.lead, "lead-v"), (self.adversarial, "adversarial")):
            roster.finalize_signoff(
                root=self.repo, session_id=session["id"], role=role,
                basis_sha256=basis, verdict="pass", roster_path=self.roster_path,
                receipts_dir=self.receipts, attestations_dir=self.attestations,
                signing_key=self.keys[role], **self._trust_args(),
            )
        self.assertEqual([], roster.verify_attestation_bundle(
            self.repo, self.roster_path, self.receipts, self.attestations,
            basis_sha256=basis, **self._trust_args(),
        ))
        self.assertTrue(roster.verify_attestation_bundle(
            self.repo, self.roster_path, self.receipts, self.attestations,
            basis_sha256="b" * 64, **self._trust_args(),
        ))


if __name__ == "__main__":
    unittest.main()
