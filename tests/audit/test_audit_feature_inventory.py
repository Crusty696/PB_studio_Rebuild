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

        (self.repo / "bad.md").write_bytes(b"Pflicht: \xff\n")
        subprocess.run(["git", "add", "bad.md"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "non-utf8"], cwd=self.repo, check=True)
        bad_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.repo, text=True
        ).strip()
        with self.assertRaises(HARNESS.ContractError):
            HARNESS.enumerate_universes(self.repo, bad_commit, self.RUN, self.SNAPSHOT)

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

    def test_empty_universes_rejected(self) -> None:
        errors = HARNESS.validate_exact_set(
            [], [], [], run_id=self.RUN, audited_commit=self.commit,
            snapshot_id=self.SNAPSHOT,
        )
        self.assertTrue(any("leer" in error for error in errors))

    def test_relevant_non_python_surfaces_cannot_be_skipped(self) -> None:
        files = {
            "ops.ps1": "param([switch]$Force)\nfunction Invoke-Audit { Write-Output ok }\nInvoke-Audit\n",
            "launch.bat": "@echo off\ncall :run\n:run\necho ok\n",
            "schema.sql": "CREATE TRIGGER audit_insert AFTER INSERT ON audit BEGIN SELECT 1; END;\n",
            "panel.ui": "<ui><widget class='QPushButton' name='runButton'><property name='text'><string>Run</string></property></widget><connections><connection><sender>runButton</sender><signal>clicked()</signal><receiver>window</receiver><slot>run()</slot></connection></connections></ui>",
            "de.ts": "<TS><context><message><source>Run export</source><translation>Export starten</translation></message></context></TS>",
            "config.json": '{"feature": {"enabled": true}}\n',
            "config.yaml": "feature:\n  enabled: true\n",
            "config.toml": "[feature]\nenabled = true\n",
        }
        for name, text in files.items():
            (self.repo / name).write_text(text, encoding="utf-8")
        subprocess.run(["git", "add", *files], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "non-python surfaces"], cwd=self.repo, check=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        requirements, triggers = HARNESS.enumerate_universes(
            self.repo, commit, self.RUN, self.SNAPSHOT
        )
        covered = {row["path"] for row in requirements + triggers}
        self.assertEqual(set(files), set(files) & covered)
        kinds = {row["source_kind"] for row in requirements + triggers}
        self.assertTrue({
            "powershell-entrypoint", "batch-entrypoint", "sql-trigger", "qt-ui-signal",
            "translation-contract", "structured-config-unit",
        }.issubset(kinds))

    def test_pep263_python_decoding(self) -> None:
        source = "# -*- coding: latin-1 -*-\nfrom PyQt6.QtWidgets import QPushButton\nbutton = QPushButton('Über')\n"
        (self.repo / "latin.py").write_bytes(source.encode("latin-1"))
        subprocess.run(["git", "add", "latin.py"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "pep263"], cwd=self.repo, check=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        requirements, _ = HARNESS.enumerate_universes(self.repo, commit, self.RUN, self.SNAPSHOT)
        self.assertTrue(any(row["path"] == "latin.py" and "Über" in row["detail"] for row in requirements))


if __name__ == "__main__":
    unittest.main()
