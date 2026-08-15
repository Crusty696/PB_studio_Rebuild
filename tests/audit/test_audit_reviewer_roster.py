from __future__ import annotations

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
from tools import audit_reviewer_roster as roster


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


class GateContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-b", "main")
        _git(self.repo, "config", "user.email", "audit@example.invalid")
        _git(self.repo, "config", "user.name", "Audit Test")
        (self.repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        _git(self.repo, "add", "seed.txt")
        _git(self.repo, "commit", "-m", "seed")
        self.commit = _git(self.repo, "rev-parse", "HEAD")
        self.common = self.repo / ".git"
        self.registry_patch = mock.patch.object(
            agent_session, "_git_common_dir", return_value=self.common
        )
        self.registry_patch.start()
        self.key = self.base / "anchor"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.key)],
            check=True, capture_output=True,
        )
        self.public_key = self.key.with_suffix(".pub")
        self.pin = roster.public_key_sha256(self.public_key)
        self.receipts = self.base / "receipts"
        self.attestations = self.base / "attestations"
        self.roster_path = self.base / "reviewer_roster.jsonl"
        self.contract_path = self.base / "contract.json"
        self.contract_sig = self.base / "contract.json.sig"
        self.spawn_path = self.base / "spawn.json"
        self.spawn_sig = self.base / "spawn.json.sig"
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

    def _signed(self, path: Path, value: dict, namespace: str) -> None:
        path.write_bytes(roster._canonical(value) + b"\n")
        signature = path.with_name(path.name + ".sig")
        signature.unlink(missing_ok=True)
        roster.sign_file(path, signature, self.key, namespace)

    def _write_trust(
        self, *, direct_ancestor: bool = False, forced_director: bool = False,
        pairs: list[list[str]] | None = None,
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
            roster.SPAWN_NAMESPACE,
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
            "public_key_sha256": self.pin,
            "spawn_journal_sha256": roster._sha(self.spawn_path.read_bytes()),
            "reviewers": reviewers,
            "reviewer_pairs": pairs if pairs is not None else [[lead_id, adversarial_id]],
            "assignments": [
                {
                    "assignment_id": "A-services",
                    "reviewer_id": lead_id,
                    "role": "lead-v",
                    "pass": "A",
                    "output_claim": "@audit/RUN-1/lead/**",
                    "review_scope": "services/**",
                },
                {
                    "assignment_id": "B-services",
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
        self._signed(self.contract_path, contract, roster.CONTRACT_NAMESPACE)

    def _trust_args(self) -> dict:
        return {
            "contract_path": self.contract_path,
            "contract_signature": self.contract_sig,
            "spawn_journal_path": self.spawn_path,
            "spawn_journal_signature": self.spawn_sig,
            "public_key_path": self.public_key,
            "expected_public_key_sha256": self.pin,
        }

    def _enroll(self, session: dict) -> dict:
        return roster.enroll(
            root=self.repo, session_id=session["id"], receipts_dir=self.receipts,
            roster_path=self.roster_path, signing_key=self.key, **self._trust_args()
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
        self._signed(self.contract_path, contract, roster.CONTRACT_NAMESPACE)
        errors = self._verify()
        self.assertTrue(any("Claim/Scope" in error for error in errors), errors)

    def test_nested_output_shard_prefix_overlap_rejected(self) -> None:
        contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
        nested = "@audit/RUN-1/lead/sub/**"
        contract["reviewers"][1]["output_claims"] = [nested]
        contract["assignments"][1]["output_claim"] = nested
        self._signed(self.contract_path, contract, roster.CONTRACT_NAMESPACE)
        errors = self._verify()
        self.assertTrue(any("ueberlappen" in error for error in errors), errors)

    def test_stale_lock_and_signed_orphan_recovery(self) -> None:
        lead = self._enroll(self.lead)
        self.roster_path.unlink()
        lock = self.roster_path.with_name(self.roster_path.name + ".lock")
        lock.write_text("stale", encoding="utf-8")
        old = time.time() - roster.LOCK_STALE_SECONDS - 5
        os.utime(lock, (old, old))
        recovered = self._enroll(self.lead)
        self.assertEqual(lead["session_receipt_sha256"], recovered["session_receipt_sha256"])

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
                signing_key=self.key, **self._trust_args(),
            )
        for session, role in ((self.lead, "lead-v"), (self.adversarial, "adversarial")):
            roster.finalize_signoff(
                root=self.repo, session_id=session["id"], role=role,
                basis_sha256=basis, verdict="pass", roster_path=self.roster_path,
                receipts_dir=self.receipts, attestations_dir=self.attestations,
                signing_key=self.key, **self._trust_args(),
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
