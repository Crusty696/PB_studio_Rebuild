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
    DELTA_FIELDS,
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
            integration_head=self.current_head() if head is None else head,
            expected_audit_contract_sha256=(
                selected.get("contract_sha256", "") if pin is None else pin
            ),
            now=now or datetime(2026, 8, 15, 10, 30, tzinfo=timezone.utc),
        )

    def current_head(self) -> str:
        return git(self.repo, "rev-parse", "HEAD")

    @staticmethod
    def disposition(row: dict, *, product_relevant: bool = False) -> dict:
        return {
            **row, "product_relevant": product_relevant,
            "disposition": "reaudit-required" if product_relevant else "report-only",
            "reviewer_id": "REV-A", "signed_at": "2026-08-15T10:20:00+00:00",
        }

    def make_delta(self, content: str = "value = 2\n") -> tuple[str, dict]:
        (self.repo / "app.py").write_text(content, encoding="utf-8")
        git(self.repo, "add", "app.py")
        git(self.repo, "commit", "-m", "delta")
        head = self.current_head()
        row = expected_delta(self.repo, self.base, head, run_id="RUN-001")[0]
        return head, self.disposition(row)

    # Stable commit-materialized entry points required by readiness.
    def test_positive_minimal(self) -> None:
        self.test_positive_global_contract_no_delta()

    def test_missing_required_rejected(self) -> None:
        self.test_missing_id_tampered_commit_and_noncurrent_head_rejected()

    def test_tampered_binding_rejected(self) -> None:
        self.test_global_contract_missing_extra_and_raw_file_sha_rejected()

    def test_duplicate_or_foreign_id_rejected(self) -> None:
        self.test_exact_delta_duplicate_foreign_and_missing_rejected()

    def test_expired_ttl_or_product_delta_rejected(self) -> None:
        self.test_expired_ttl_product_delta_and_naive_now_rejected()

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

    def test_missing_id_tampered_commit_and_noncurrent_head_rejected(self) -> None:
        contract = dict(self.contract)
        del contract["run_id"]
        self.assertTrue(any("run_id" in error or "Feldmenge" in error for error in self.verify(contract=contract)))
        contract = dict(self.contract, audited_commit="0" * 40)
        self.assertTrue(any("audited_commit" in error for error in self.verify(contract=contract)))
        self.make_delta()
        self.assertTrue(any("Current HEAD" in error for error in self.verify(head=self.base)))

    def test_exact_delta_duplicate_foreign_and_missing_rejected(self) -> None:
        head, row = self.make_delta()
        self.assertEqual([], self.verify(rows=[row], head=head))
        errors = self.verify(rows=[row, dict(row)], head=head)
        self.assertTrue(any("doppelt" in error for error in errors), errors)
        foreign = dict(row, path="foreign.py")
        self.assertTrue(any("Mengengleichheit" in error for error in self.verify(rows=[foreign], head=head)))
        self.assertTrue(any("Mengengleichheit" in error for error in self.verify(rows=[], head=head)))

    def test_delta_exact_fields_disposition_reviewer_and_timestamp(self) -> None:
        head, row = self.make_delta()
        self.assertEqual(DELTA_FIELDS, set(row))
        variants = []
        missing = dict(row)
        missing.pop("signed_at")
        variants.append(missing)
        variants.append({**row, "extra": True})
        variants.append({**row, "disposition": "accepted"})
        variants.append({**row, "reviewer_id": " "})
        variants.append({**row, "signed_at": "2026-08-15T10:20:00"})
        for value in variants:
            with self.subTest(value=value):
                self.assertTrue(self.verify(rows=[value], head=head))

    def test_expired_ttl_product_delta_and_naive_now_rejected(self) -> None:
        self.assertTrue(any(
            "TTL" in error
            for error in self.verify(now=datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc))
        ))
        self.assertTrue(any("timezone-aware" in error for error in self.verify(now=datetime(2026, 8, 15, 10, 30))))
        head, row = self.make_delta()
        row.update(product_relevant=True, disposition="reaudit-required")
        self.assertTrue(any("produktrelevant" in error for error in self.verify(rows=[row], head=head)))

    def test_rename_uses_schema_path_and_change_without_extra_fields(self) -> None:
        git(self.repo, "mv", "app.py", "renamed.py")
        git(self.repo, "commit", "-m", "rename")
        head = self.current_head()
        row = self.disposition(expected_delta(self.repo, self.base, head, run_id="RUN-001")[0])
        self.assertEqual("renamed", row["change"])
        self.assertEqual("renamed.py", row["path"])
        self.assertEqual(DELTA_FIELDS, set(row))
        self.assertEqual([], self.verify(rows=[row], head=head))

    def test_git_replace_objects_are_ignored(self) -> None:
        head, row = self.make_delta()
        git(self.repo, "replace", self.base, head)
        expected = expected_delta(self.repo, self.base, head, run_id="RUN-001")
        self.assertEqual(["modified"], [item["change"] for item in expected])
        self.assertEqual([], self.verify(rows=[row], head=head))

    def test_membership_type_matrix_never_crashes(self) -> None:
        hostile = [[], {}, {"nested": []}, True, 1, None, "", " "]
        for value in hostile:
            with self.subTest(value=value):
                errors = self.verify(rows=[{
                    "run_id": "RUN-001", "base_commit": self.base,
                    "head_commit": self.base, "path": "app.py", "change": "modified",
                    "product_relevant": False, "disposition": value,
                    "reviewer_id": "REV-A", "signed_at": "2026-08-15T10:20:00+00:00",
                }])
                self.assertTrue(errors)

    def test_production_cli_has_no_now_override(self) -> None:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[2] / "tools/audit_delta_ttl.py"), "--help"],
            check=True, capture_output=True, text=True,
        )
        self.assertNotIn("--now", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
