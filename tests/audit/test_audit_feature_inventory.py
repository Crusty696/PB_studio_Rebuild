from __future__ import annotations

import copy
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "audit_feature_inventory", ROOT / "tools" / "audit_feature_inventory.py"
)
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HARNESS
SPEC.loader.exec_module(HARNESS)


class GateContractTests(unittest.TestCase):
    RUN = "RUN-CONTRACT"
    SNAPSHOT = "SNAPSHOT-CONTRACT"

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="pb-feature-contract-")
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "audit@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Audit Contract"], cwd=self.repo, check=True)
        (self.repo / "contract.md").write_text(
            "# Contract\nExport muss Ergebnis speichern.\n", encoding="utf-8"
        )
        (self.repo / "app.py").write_text(
            "from PyQt6.QtWidgets import QPushButton\n"
            "def run():\n    return 1\n"
            "def main():\n"
            "    button = QPushButton('Run export')\n"
            "    button.clicked.connect(run)\n"
            "if __name__ == '__main__':\n    main()\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "contract.md", "app.py"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.repo, check=True)
        self.commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        self.requirements, self.triggers = HARNESS.enumerate_universes(
            self.repo, self.commit, self.RUN, self.SNAPSHOT
        )
        self.assertTrue(self.requirements)
        self.assertTrue(self.triggers)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def dispositions(self) -> list[dict]:
        rows = []
        for kind, universe in (("requirement", self.requirements), ("trigger", self.triggers)):
            digest = HARNESS.universe_digest(universe)
            for item in universe:
                rows.append({
                    "universe": kind,
                    "source_id": item["source_id"],
                    "run_id": self.RUN,
                    "audited_commit": self.commit,
                    "snapshot_id": self.SNAPSHOT,
                    "universe_sha256": digest,
                    "disposition": "feature",
                    "feature_id": "FEAT-EXPORT",
                    "path_id": "primary",
                    "evidence": {"kind": "source", "ref": f"{item['path']}:{item['line']}"},
                })
        return rows

    def errors(self, rows: list[dict]) -> list[str]:
        return HARNESS.validate_exact_set(
            self.requirements, self.triggers, rows, run_id=self.RUN,
            audited_commit=self.commit, snapshot_id=self.SNAPSHOT,
        )

    def test_positive_minimal(self) -> None:
        before = (self.requirements, self.triggers)
        (self.repo / "app.py").write_text("raise RuntimeError('dirty')\n", encoding="utf-8")
        after = HARNESS.enumerate_universes(self.repo, self.commit, self.RUN, self.SNAPSHOT)
        self.assertEqual(before, after, "Enumerator darf Dirty-Workingtree nicht lesen")
        self.assertEqual([], self.errors(self.dispositions()))

    def test_missing_required_rejected(self) -> None:
        rows = self.dispositions()
        rows[0].pop("evidence")
        self.assertTrue(any("evidence fehlt" in error for error in self.errors(rows)))

    def test_tampered_binding_rejected(self) -> None:
        rows = self.dispositions()
        rows[0]["audited_commit"] = "0" * 40
        rows[1]["universe_sha256"] = "f" * 64
        errors = self.errors(rows)
        self.assertTrue(any("Commit" in error for error in errors))
        self.assertTrue(any("Universumshash" in error for error in errors))

    def test_duplicate_or_foreign_id_rejected(self) -> None:
        rows = self.dispositions()
        rows.append(copy.deepcopy(rows[0]))
        foreign = copy.deepcopy(rows[0])
        foreign["source_id"] = "REQ-FOREIGN"
        rows.append(foreign)
        errors = self.errors(rows)
        self.assertTrue(any("doppelte ID" in error for error in errors))
        self.assertTrue(any("fremde ID" in error for error in errors))

    def test_exact_set_missing_extra_duplicate_rejected(self) -> None:
        base = self.dispositions()
        cases = {
            "missing": base[1:],
            "extra": base + [{**copy.deepcopy(base[0]), "source_id": "TRIG-EXTRA"}],
            "duplicate": base + [copy.deepcopy(base[0])],
        }
        for label, rows in cases.items():
            with self.subTest(label=label):
                self.assertNotEqual([], self.errors(rows))


if __name__ == "__main__":
    unittest.main()
