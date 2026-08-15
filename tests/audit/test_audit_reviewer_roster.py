from __future__ import annotations

import json
import subprocess
import sys
import tempfile
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
        self.worktrees = self.base / "worktrees"
        self.repo.mkdir()
        self.worktrees.mkdir()
        _git(self.repo, "init", "-b", "main")
        _git(self.repo, "config", "user.email", "audit@example.invalid")
        _git(self.repo, "config", "user.name", "Audit Test")
        (self.repo / "seed.txt").write_text("seed\n", encoding="utf-8")
        _git(self.repo, "add", "seed.txt")
        _git(self.repo, "commit", "-m", "seed")
        self.commit = _git(self.repo, "rev-parse", "HEAD")
        self.registry_dir = self.base / "registry"
        self.registry_dir.mkdir()
        self.registry_patch = mock.patch.object(
            agent_session, "_git_common_dir", return_value=self.registry_dir
        )
        self.registry_patch.start()
        self.receipts = self.base / "receipts"
        self.roster = self.base / "reviewer_roster.jsonl"

    def tearDown(self) -> None:
        self.registry_patch.stop()
        self.temp.cleanup()

    def _worktree(self, name: str) -> Path:
        path = self.worktrees / name
        _git(self.repo, "worktree", "add", "--detach", str(path), self.commit)
        return path

    def _claim(
        self, name: str, *, parent: str | None = None, force: bool = False
    ) -> dict:
        worktree = self._worktree(name)
        session, conflicts = agent_session.claim(
            name,
            "audit",
            [],
            branch="HEAD",
            worktree=str(worktree),
            parent_session_id=parent,
            force=force,
        )
        self.assertTrue(session)
        self.assertFalse(conflicts)
        return session

    def _enroll(
        self,
        session: dict,
        *,
        claim: str,
        scope: str = "services/**",
        roster_path: Path | None = None,
    ) -> dict:
        return roster.enroll(
            root=self.repo,
            session_id=session["id"],
            run_id="RUN-1",
            audited_commit=self.commit,
            snapshot_id="snapshot-1",
            output_claims=[claim],
            review_scope=[scope],
            receipts_dir=self.receipts,
            roster_path=roster_path or self.roster,
        )

    def test_positive_minimal(self) -> None:
        director = self._claim("director")
        a = self._claim("review-a", parent=director["id"])
        b = self._claim("review-b", parent=director["id"])
        row_a = self._enroll(a, claim="@audit/RUN-1/a/**")
        row_b = self._enroll(b, claim="@audit/RUN-1/b/**")

        errors = roster.verify_roster(
            self.repo,
            self.roster,
            self.receipts,
            run_id="RUN-1",
            audited_commit=self.commit,
            snapshot_id="snapshot-1",
            reviewer_pairs=[(row_a["reviewer_id"], row_b["reviewer_id"])],
        )
        self.assertEqual([], errors)
        self.assertEqual(row_a["ancestor_session_ids"], [director["id"]])
        self.assertEqual(row_b["ancestor_session_ids"], [director["id"]])
        self.assertNotEqual(row_a["reviewer_id"], row_b["reviewer_id"])

    def test_missing_required_rejected(self) -> None:
        with self.assertRaises(roster.EnrollmentError):
            roster.enroll(
                root=self.repo,
                session_id="forged-session",
                run_id="RUN-1",
                audited_commit=self.commit,
                snapshot_id="snapshot-1",
                output_claims=["@audit/RUN-1/a/**"],
                review_scope=["services/**"],
                receipts_dir=self.receipts,
                roster_path=self.roster,
            )

    def test_tampered_binding_rejected(self) -> None:
        row = self._enroll(self._claim("review-a"), claim="@audit/RUN-1/a/**")
        receipt_path = self.receipts / f"{row['session_id']}.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["worktree"]["head"] = "0" * 40
        receipt_path.write_text(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        errors = roster.verify_roster(
            self.repo,
            self.roster,
            self.receipts,
            run_id="RUN-1",
            audited_commit=self.commit,
            snapshot_id="snapshot-1",
        )
        self.assertTrue(any("Receipt-Hash" in error for error in errors), errors)

    def test_duplicate_or_foreign_id_rejected(self) -> None:
        row = self._enroll(self._claim("review-a"), claim="@audit/RUN-1/a/**")
        forged = dict(row)
        forged["reviewer_id"] = "REV-FORGED"
        with self.roster.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(forged, sort_keys=True, separators=(",", ":")) + "\n")
        errors = roster.verify_roster(
            self.repo,
            self.roster,
            self.receipts,
            run_id="RUN-1",
            audited_commit=self.commit,
            snapshot_id="snapshot-1",
        )
        self.assertTrue(any("session_id doppelt" in error for error in errors), errors)
        self.assertTrue(any("deterministisch" in error for error in errors), errors)

    def test_same_session_or_ancestor_rejected(self) -> None:
        a = self._claim("review-a")
        b = self._claim("review-b", parent=a["id"])
        row_a = self._enroll(a, claim="@audit/RUN-1/a/**")
        row_b = self._enroll(b, claim="@audit/RUN-1/b/**")
        errors = roster.verify_roster(
            self.repo,
            self.roster,
            self.receipts,
            run_id="RUN-1",
            audited_commit=self.commit,
            snapshot_id="snapshot-1",
            reviewer_pairs=[(row_a["reviewer_id"], row_b["reviewer_id"])],
        )
        self.assertTrue(any("Vorfahr/Nachfahre" in error for error in errors), errors)

    def test_shared_director_is_only_allowed_without_signoff(self) -> None:
        director = self._claim("director")
        a = self._claim("review-a", parent=director["id"])
        b = self._claim("review-b", parent=director["id"])
        self._enroll(director, claim="@audit/RUN-1/director/**")
        row_a = self._enroll(a, claim="@audit/RUN-1/a/**")
        row_b = self._enroll(b, claim="@audit/RUN-1/b/**")
        errors = roster.verify_roster(
            self.repo, self.roster, self.receipts, run_id="RUN-1",
            audited_commit=self.commit, snapshot_id="snapshot-1",
            reviewer_pairs=[(row_a["reviewer_id"], row_b["reviewer_id"])],
        )
        self.assertTrue(any("gemeinsamer Director" in error for error in errors), errors)

    def test_overlap_claims_red_but_review_scope_overlap_allowed(self) -> None:
        a = self._claim("review-a")
        b = self._claim("review-b")
        self._enroll(a, claim="@audit/RUN-1/shared/**")
        with self.assertRaisesRegex(roster.EnrollmentError, "Output-Claims"):
            self._enroll(b, claim="@audit/RUN-1/shared/file.jsonl")

        # Same source scope is intentional for independent Pass A/B.
        independent_roster = self.base / "independent_roster.jsonl"
        independent_receipts = self.base / "independent_receipts"
        row_a = roster.enroll(
            root=self.repo, session_id=a["id"], run_id="RUN-2",
            audited_commit=self.commit, snapshot_id="snapshot-2",
            output_claims=["@audit/RUN-2/a/**"], review_scope=["services/**"],
            receipts_dir=independent_receipts, roster_path=independent_roster,
        )
        row_b = roster.enroll(
            root=self.repo, session_id=b["id"], run_id="RUN-2",
            audited_commit=self.commit, snapshot_id="snapshot-2",
            output_claims=["@audit/RUN-2/b/**"], review_scope=["services/**"],
            receipts_dir=independent_receipts, roster_path=independent_roster,
        )
        self.assertEqual([], roster.verify_roster(
            self.repo, independent_roster, independent_receipts,
            run_id="RUN-2", audited_commit=self.commit, snapshot_id="snapshot-2",
            reviewer_pairs=[(row_a["reviewer_id"], row_b["reviewer_id"])],
        ))

    def test_forced_session_rejected(self) -> None:
        session = self._claim("forced", force=True)
        with self.assertRaisesRegex(roster.EnrollmentError, "forced"):
            self._enroll(session, claim="@audit/RUN-1/a/**")

    def test_dirty_and_forged_worktree_rejected(self) -> None:
        dirty = self._claim("dirty")
        marker = Path(dirty["worktree"]) / "untracked.txt"
        marker.write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(roster.EnrollmentError, "nicht clean"):
            self._enroll(dirty, claim="@audit/RUN-1/dirty/**")
        marker.unlink()

        forged = self._claim("forged")
        raw = json.loads(agent_session.registry_path().read_text(encoding="utf-8"))
        for session in raw["sessions"]:
            if session["id"] == forged["id"]:
                session["worktree"] = str(self.base / "does-not-exist")
        agent_session.registry_path().write_text(json.dumps(raw), encoding="utf-8")
        with self.assertRaisesRegex(roster.EnrollmentError, "Worktree fehlt"):
            self._enroll(forged, claim="@audit/RUN-1/forged/**")

    def test_final_verify_after_session_and_worktree_deleted(self) -> None:
        session = self._claim("review-a")
        row = self._enroll(session, claim="@audit/RUN-1/a/**")
        self.assertTrue(agent_session.release(session["id"]))
        _git(self.repo, "worktree", "remove", "--force", session["worktree"])
        self.assertFalse(Path(session["worktree"]).exists())

        errors = roster.verify_roster(
            self.repo,
            self.roster,
            self.receipts,
            run_id="RUN-1",
            audited_commit=self.commit,
            snapshot_id="snapshot-1",
        )
        self.assertEqual([], errors)


if __name__ == "__main__":
    unittest.main()
