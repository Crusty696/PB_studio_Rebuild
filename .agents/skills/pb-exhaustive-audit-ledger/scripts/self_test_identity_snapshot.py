from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from build_inventory import build
from verify_line_coverage import verify


def _run(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


class IdentityAndSnapshotTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.repo = base / "repo"
        self.evidence = base / "evidence"
        self.repo.mkdir()
        _run(self.repo, "init", "-b", "audit")
        _run(self.repo, "config", "user.email", "audit@example.invalid")
        _run(self.repo, "config", "user.name", "Audit Test")
        (self.repo / "sample.py").write_text("value = 1\n", encoding="utf-8")
        _run(self.repo, "add", "sample.py")
        _run(self.repo, "commit", "-m", "audited source")
        self.audited_commit = _run(self.repo, "rev-parse", "HEAD")
        build(self.repo, self.evidence, run_id="RUN-ID")

        self.roster = self.evidence / "reviewer_roster.jsonl"
        self.roster_rows = [
            {
                "run_id": "RUN-ID",
                "audited_commit": self.audited_commit,
                "reviewer_id": "reviewer-a",
                "session_id": "session-a",
                "parent_id": "director-a",
                "lineage_ids": ["root-a", "director-a"],
                "worktree": "C:/audit/a",
                "branch": "audit/a",
                "commit_sha": self.audited_commit,
                "claims": ["sample.py"],
            },
            {
                "run_id": "RUN-ID",
                "audited_commit": self.audited_commit,
                "reviewer_id": "reviewer-b",
                "session_id": "session-b",
                "parent_id": "director-b",
                "lineage_ids": ["root-b", "director-b"],
                "worktree": "C:/audit/b",
                "branch": "audit/b",
                "commit_sha": self.audited_commit,
                "claims": ["sample.py"],
            },
        ]
        _write_jsonl(self.roster, self.roster_rows)
        snapshot_path = self.evidence / "snapshot.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot["audited_commit"] = self.audited_commit
        snapshot["reviewer_roster_sha256"] = hashlib.sha256(
            self.roster.read_bytes()
        ).hexdigest()
        snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

        inventory = [
            json.loads(line)
            for line in (self.evidence / "files.jsonl").read_text().splitlines()
        ]
        item = inventory[0]
        for reviewer in self.roster_rows:
            reviewer["snapshot_id"] = item["snapshot_id"]
        _write_jsonl(self.roster, self.roster_rows)
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot["reviewer_roster_sha256"] = hashlib.sha256(
            self.roster.read_bytes()
        ).hexdigest()
        snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
        common = {
            "run_id": "RUN-ID",
            "snapshot_id": item["snapshot_id"],
            "path": "sample.py",
            "file_sha256": item["sha256"],
            "checks": {
                "semantics": "done",
                "errors": "done",
                "state": "done",
                "threading": "done",
                "io_db_gpu": "done",
                "wiring": "done",
            },
            "finding_ids": [],
            "verdict": "reviewed",
            "signed_at": "2026-08-15T00:00:00Z",
            "start_line": 1,
            "end_line": 1,
        }
        _write_jsonl(
            self.evidence / "pass_a.jsonl",
            [{**common, "pass": "A", "reviewer_id": "reviewer-a"}],
        )
        _write_jsonl(
            self.evidence / "pass_b.jsonl",
            [{**common, "pass": "B", "reviewer_id": "reviewer-b"}],
        )
        unit_common = {
            "run_id": "RUN-ID",
            "snapshot_id": item["snapshot_id"],
            "path": "sample.py",
            "unit_kind": "metadata",
            "file_sha256": item["sha256"],
            "checks": {
                "identity": "done",
                "format": "done",
                "provenance": "done",
                "consumer": "done",
                "integrity": "done",
            },
            "verdict": "reviewed",
            "signed_at": "2026-08-15T00:00:00Z",
        }
        _write_jsonl(
            self.evidence / "non_line.jsonl",
            [
                {**unit_common, "pass": "A", "reviewer_id": "reviewer-a"},
                {**unit_common, "pass": "B", "reviewer_id": "reviewer-b"},
            ],
        )
        _write_jsonl(self.evidence / "exclusions.jsonl", [])

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _verify(self) -> list[str]:
        return verify(
            self.repo,
            self.evidence / "snapshot.json",
            self.evidence / "files.jsonl",
            self.evidence / "pass_a.jsonl",
            self.evidence / "pass_b.jsonl",
            self.evidence / "non_line.jsonl",
            self.evidence / "exclusions.jsonl",
            self.evidence / "workspace_units.jsonl",
            self.roster,
        )

    def test_report_commit_does_not_invalidate_audited_commit(self) -> None:
        (self.repo / "report.md").write_text("report\n", encoding="utf-8")
        (self.repo / "sample.py").write_text("value = 2\n", encoding="utf-8")
        _run(self.repo, "add", "report.md", "sample.py")
        _run(self.repo, "commit", "-m", "publish report")

        self.assertEqual([], self._verify())

    def test_shared_parent_lineage_is_not_independent(self) -> None:
        self.roster_rows[1]["lineage_ids"] = ["root-a", "director-b"]
        _write_jsonl(self.roster, self.roster_rows)
        snapshot_path = self.evidence / "snapshot.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot["reviewer_roster_sha256"] = hashlib.sha256(
            self.roster.read_bytes()
        ).hexdigest()
        snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

        errors = self._verify()

        self.assertTrue(any("Lineage" in error for error in errors), errors)

    def test_roster_hash_is_bound(self) -> None:
        self.roster_rows[0]["claims"] = ["other.py"]
        _write_jsonl(self.roster, self.roster_rows)

        errors = self._verify()

        self.assertTrue(any("Roster-Hash" in error for error in errors), errors)

    def test_same_session_is_not_independent(self) -> None:
        self.roster_rows[1]["session_id"] = "session-a"
        _write_jsonl(self.roster, self.roster_rows)
        snapshot_path = self.evidence / "snapshot.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot["reviewer_roster_sha256"] = hashlib.sha256(
            self.roster.read_bytes()
        ).hexdigest()
        snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

        errors = self._verify()

        self.assertTrue(any("session_id" in error for error in errors), errors)
        self.assertTrue(any("Identity/Lineage" in error for error in errors), errors)

    def test_unknown_reviewer_is_rejected(self) -> None:
        rows = [
            json.loads(line)
            for line in (self.evidence / "pass_b.jsonl").read_text().splitlines()
        ]
        rows[0]["reviewer_id"] = "invented-reviewer"
        _write_jsonl(self.evidence / "pass_b.jsonl", rows)

        errors = self._verify()

        self.assertTrue(any("fehlt im Reviewer-Roster" in error for error in errors), errors)

    def test_reviewer_must_claim_reviewed_path(self) -> None:
        self.roster_rows[1]["claims"] = ["other/**"]
        _write_jsonl(self.roster, self.roster_rows)
        snapshot_path = self.evidence / "snapshot.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot["reviewer_roster_sha256"] = hashlib.sha256(
            self.roster.read_bytes()
        ).hexdigest()
        snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

        errors = self._verify()

        self.assertTrue(any("Claims decken Pfad nicht ab" in error for error in errors), errors)

    def test_workspace_drift_after_snapshot_is_rejected(self) -> None:
        (self.repo / "untracked.txt").write_text("drift\n", encoding="utf-8")

        errors = self._verify()

        self.assertIn("Current Working Tree ist nicht clean", errors)
        self.assertTrue(any("Scopewurzeln weichen" in error for error in errors), errors)

    def test_invalid_audited_commit_fails_without_crash(self) -> None:
        snapshot_path = self.evidence / "snapshot.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        snapshot["audited_commit"] = "not-a-commit"
        snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

        errors = self._verify()

        self.assertTrue(any("40-stellige" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
