from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.audit_delta_ttl import (  # noqa: E402
    AUDIT_ARTIFACT_KEYS,
    expected_delta,
    verify_delta_ttl,
)


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def seal(value: dict) -> dict:
    return {**value, "contract_sha256": hashlib.sha256(canonical(value)).hexdigest()}


class GateContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "audit")
        git(self.repo, "config", "user.email", "audit@example.invalid")
        git(self.repo, "config", "user.name", "Audit Test")
        (self.repo / "app.py").write_text("value = 1\n", encoding="utf-8")
        git(self.repo, "add", "app.py")
        git(self.repo, "commit", "-m", "base")
        self.base = git(self.repo, "rev-parse", "HEAD")
        descriptor = {
            "artifact_id": "sha256:" + "1" * 64, "ref": "placeholder.bin",
            "sha256": "1" * 64, "bytes": 1, "record_count": 1,
        }
        self.contract = seal({
            "schema_version": 1,
            "plan_id": "PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15",
            "run_id": "RUN-001", "audited_commit": self.base,
            "tooling_commit": "b" * 40, "snapshot_id": "snapshot-001",
            "frozen_at": "2026-08-15T10:00:00+00:00",
            "expires_at": "2026-08-15T11:00:00+00:00",
            "artifacts": {key: dict(descriptor, ref=f"{key}.bin") for key in AUDIT_ARTIFACT_KEYS},
        })

    def tearDown(self) -> None:
        self.temp.cleanup()

    def verify(self, contract=None, rows=None, head=None, pin=None, now=None) -> list[str]:
        selected = self.contract if contract is None else contract
        return verify_delta_ttl(
            self.repo, selected, [] if rows is None else rows,
            integration_head=head or self.base,
            expected_audit_contract_sha256=pin or selected.get("contract_sha256", ""),
            now=now or datetime(2026, 8, 15, 10, 30, tzinfo=timezone.utc),
        )

    def test_positive_global_contract_no_delta(self) -> None:
        self.assertEqual([], self.verify())

    def test_global_contract_missing_extra_and_raw_file_sha_rejected(self) -> None:
        contract = dict(self.contract)
        contract["integration_head"] = self.base
        self.assertTrue(any("Feldmenge" in error for error in self.verify(contract=contract)))
        contract = json.loads(json.dumps(self.contract))
        contract["artifacts"].pop("edge-catalog")
        contract = seal({key: value for key, value in contract.items() if key != "contract_sha256"})
        self.assertTrue(any("14er-Union" in error for error in self.verify(contract=contract)))
        raw_file_sha = hashlib.sha256(canonical(self.contract)).hexdigest()
        self.assertNotEqual(raw_file_sha, self.contract["contract_sha256"])
        self.assertTrue(any("Body-SHA" in error for error in self.verify(pin=raw_file_sha)))

    def test_missing_id_and_tampered_commit_rejected(self) -> None:
        contract = dict(self.contract)
        del contract["run_id"]
        self.assertTrue(any("run_id" in error or "Feldmenge" in error for error in self.verify(contract=contract)))
        contract = dict(self.contract, audited_commit="0" * 40)
        self.assertTrue(any("audited_commit" in error for error in self.verify(contract=contract)))

    def test_exact_delta_duplicate_foreign_and_missing_rejected(self) -> None:
        (self.repo / "app.py").write_text("value = 2\n", encoding="utf-8")
        git(self.repo, "add", "app.py")
        git(self.repo, "commit", "-m", "report delta")
        head = git(self.repo, "rev-parse", "HEAD")
        expected = expected_delta(self.repo, self.base, head, run_id="RUN-001", snapshot_id="snapshot-001")
        row = {**expected[0], "product_relevant": False, "decision_ref": "D-090", "reviewer_id": "REV-A"}
        self.assertEqual([], self.verify(rows=[row], head=head))
        errors = self.verify(rows=[row, dict(row)], head=head)
        self.assertTrue(any("doppelt" in error for error in errors), errors)
        foreign = dict(row, path="foreign.py")
        self.assertTrue(any("Mengengleichheit" in error for error in self.verify(rows=[foreign], head=head)))
        self.assertTrue(any("Mengengleichheit" in error for error in self.verify(rows=[], head=head)))

    def test_expired_ttl_product_delta_and_naive_now_rejected(self) -> None:
        self.assertTrue(any(
            "TTL" in error
            for error in self.verify(now=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc))
        ))
        self.assertTrue(any("timezone-aware" in error for error in self.verify(now=datetime(2026, 8, 15, 10, 30))))
        (self.repo / "app.py").write_text("value = 2\n", encoding="utf-8")
        git(self.repo, "add", "app.py")
        git(self.repo, "commit", "-m", "product delta")
        head = git(self.repo, "rev-parse", "HEAD")
        row = expected_delta(self.repo, self.base, head, run_id="RUN-001", snapshot_id="snapshot-001")[0]
        row.update(product_relevant=True, decision_ref="D-090", reviewer_id="REV-A")
        self.assertTrue(any("produktrelevant" in error for error in self.verify(rows=[row], head=head)))

    def test_rename_old_path_is_part_of_exact_identity(self) -> None:
        git(self.repo, "mv", "app.py", "renamed.py")
        git(self.repo, "commit", "-m", "rename")
        head = git(self.repo, "rev-parse", "HEAD")
        row = expected_delta(self.repo, self.base, head, run_id="RUN-001", snapshot_id="snapshot-001")[0]
        row.update(product_relevant=False, decision_ref="D-090", reviewer_id="REV-A")
        self.assertEqual([], self.verify(rows=[row], head=head))
        row["old_path"] = "wrong.py"
        self.assertTrue(any("Mengengleichheit" in error for error in self.verify(rows=[row], head=head)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
