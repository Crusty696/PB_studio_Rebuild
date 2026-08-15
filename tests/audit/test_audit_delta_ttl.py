from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.audit_delta_ttl import expected_delta, verify_delta_ttl


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


class GateContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-b", "audit")
        _git(self.repo, "config", "user.email", "audit@example.invalid")
        _git(self.repo, "config", "user.name", "Audit Test")
        (self.repo / "app.py").write_text("value = 1\n", encoding="utf-8")
        _git(self.repo, "add", "app.py")
        _git(self.repo, "commit", "-m", "base")
        self.base = _git(self.repo, "rev-parse", "HEAD")
        self.contract = {
            "schema_version": 1,
            "run_id": "RUN-001",
            "audited_commit": self.base,
            "integration_head": self.base,
            "snapshot_id": "snapshot-001",
            "frozen_at": "2026-08-15T10:00:00+00:00",
            "max_age_seconds": 3600,
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def verify(self, contract=None, rows=None, now=None) -> list[str]:
        return verify_delta_ttl(
            self.repo,
            self.contract if contract is None else contract,
            [] if rows is None else rows,
            now=now or datetime(2026, 8, 15, 10, 30, tzinfo=timezone.utc),
        )

    def test_positive_minimal(self) -> None:
        self.assertEqual([], self.verify())

    def test_missing_required_rejected(self) -> None:
        contract = dict(self.contract)
        del contract["run_id"]
        self.assertTrue(any("run_id" in error for error in self.verify(contract=contract)))

    def test_tampered_binding_rejected(self) -> None:
        contract = dict(self.contract)
        contract["audited_commit"] = "0" * 40
        self.assertTrue(any("audited_commit" in error for error in self.verify(contract=contract)))

    def test_duplicate_or_foreign_id_rejected(self) -> None:
        row = {
            "run_id": "RUN-001", "snapshot_id": "snapshot-001",
            "base_commit": self.base, "head_commit": self.base,
            "status": "M", "path": "foreign.py", "product_relevant": False,
            "decision_ref": "D-TEST", "reviewer_id": "REV-1",
        }
        errors = self.verify(rows=[row, dict(row)])
        self.assertTrue(any("doppelt" in error for error in errors), errors)
        self.assertTrue(any("Mengengleichheit" in error for error in errors), errors)

    def test_expired_ttl_or_product_delta_rejected(self) -> None:
        self.assertTrue(any(
            "TTL" in error
            for error in self.verify(now=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc))
        ))
        (self.repo / "app.py").write_text("value = 2\n", encoding="utf-8")
        _git(self.repo, "add", "app.py")
        _git(self.repo, "commit", "-m", "product delta")
        head = _git(self.repo, "rev-parse", "HEAD")
        contract = dict(self.contract, integration_head=head)
        rows = expected_delta(self.repo, self.base, head, run_id="RUN-001", snapshot_id="snapshot-001")
        rows[0].update(product_relevant=True, decision_ref="D-TEST", reviewer_id="REV-1")
        self.assertTrue(any("produktrelevant" in error for error in self.verify(contract=contract, rows=rows)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
