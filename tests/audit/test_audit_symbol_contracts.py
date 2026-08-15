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
    "audit_symbol_contracts", ROOT / "tools" / "audit_symbol_contracts.py"
)
assert SPEC and SPEC.loader
HARNESS = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HARNESS
SPEC.loader.exec_module(HARNESS)


class GateContractTests(unittest.TestCase):
    RUN = "RUN-SYMBOL"
    SNAPSHOT = "SNAPSHOT-SYMBOL"
    FEATURES = {"FEAT-CONTRACT"}
    RUNTIME = {"RUNTIME-EVIDENCE"}
    REVIEWERS = {"REV-A"}
    EVIDENCE = {"E-SOURCE", "E-CALLER", "E-CONTRACT", "E-EDGE", "E-NONRUNTIME"}

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="pb-symbol-contract-")
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "audit@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Audit Contract"], cwd=self.repo, check=True)
        (self.repo / "app.py").write_text(
            "import json\n"
            "from importlib import import_module\n"
            "def deco(fn):\n    return fn\n"
            "@deco\n"
            "def helper(value: dict = dict()) -> str:\n    return json.dumps(value)\n"
            "class Controller:\n"
            "    def execute(self, signal):\n"
            "        signal.connect(helper)\n"
            "        import_module('plugin')\n"
            "        return helper({'ok': True})\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "app.py"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.repo, check=True)
        self.commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        self.symbols, self.edges = HARNESS.enumerate_contract_universe(
            self.repo, self.commit, self.RUN, self.SNAPSHOT
        )
        self.assertEqual(4, len(self.symbols))
        self.assertTrue(self.edges)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def states(self) -> list[dict]:
        symbol_hash = HARNESS.universe_digest(self.symbols, "symbol_id")
        edge_hash = HARNESS.universe_digest(self.edges, "edge_id")
        rows = []
        for symbol in self.symbols:
            contracts = {
                key: {"status": "reviewed", "evidence_ids": ["E-CONTRACT"]}
                for key in HARNESS.CONTRACT_KEYS
            }
            rows.append({
                **symbol,
                "symbols_sha256": symbol_hash,
                "edges_sha256": edge_hash,
                "role": "support",
                "feature_ids": ["FEAT-CONTRACT"],
                "reviewer_id": "REV-A",
                "caller_contract": {
                    "kind": "entrypoint",
                    "edge_ids": [],
                    "evidence_ids": ["E-CALLER"],
                },
                "contracts": contracts,
                "disposition": "non-runtime",
                "runtime_evidence_ids": [],
                "non_runtime_contract": {
                    "kind": "static-contract",
                    "evidence_id": "E-NONRUNTIME",
                    "reason": "Contractfixture ohne Runtimebehauptung",
                },
            })
        return rows

    def edge_states(self) -> list[dict]:
        symbol_hash = HARNESS.universe_digest(self.symbols, "symbol_id")
        edge_hash = HARNESS.universe_digest(self.edges, "edge_id")
        return [{
            **edge,
            "symbols_sha256": symbol_hash,
            "edges_sha256": edge_hash,
            "disposition": "resolved",
            "reviewer_id": "REV-A",
            "evidence_ids": ["E-EDGE"],
        } for edge in self.edges]

    def errors(self, states: list[dict], edges: list[dict]) -> list[str]:
        return HARNESS.validate_contracts(
            self.symbols, self.edges, states, edges, run_id=self.RUN,
            audited_commit=self.commit, snapshot_id=self.SNAPSHOT,
            known_feature_ids=self.FEATURES, runtime_evidence_ids=self.RUNTIME,
            reviewer_ids=self.REVIEWERS, evidence_ids=self.EVIDENCE,
        )

    def test_positive_minimal(self) -> None:
        before = (self.symbols, self.edges)
        (self.repo / "app.py").write_text("raise RuntimeError('dirty')\n", encoding="utf-8")
        after = HARNESS.enumerate_contract_universe(self.repo, self.commit, self.RUN, self.SNAPSHOT)
        self.assertEqual(before, after, "Enumerator darf Dirty-Workingtree nicht lesen")
        self.assertEqual([], self.errors(self.states(), self.edge_states()))

    def test_missing_required_rejected(self) -> None:
        states = self.states()
        states[0]["contracts"].pop("persistence")
        states[1].pop("caller_contract")
        errors = self.errors(states, self.edge_states())
        self.assertTrue(any("persistence" in error for error in errors))
        self.assertTrue(any("Caller" in error for error in errors))

    def test_tampered_binding_rejected(self) -> None:
        states = self.states()
        edge_states = self.edge_states()
        states[0]["audited_commit"] = "0" * 40
        edge_states[0]["source_blob_sha256"] = "f" * 64
        errors = self.errors(states, edge_states)
        self.assertTrue(any("Commit" in error for error in errors))
        self.assertTrue(any("source_blob_sha256" in error for error in errors))

    def test_duplicate_or_foreign_id_rejected(self) -> None:
        states = self.states()
        edge_states = self.edge_states()
        states.append(copy.deepcopy(states[0]))
        foreign = copy.deepcopy(edge_states[0])
        foreign["edge_id"] = "EDGE-FOREIGN"
        edge_states.append(foreign)
        errors = self.errors(states, edge_states)
        self.assertTrue(any("doppelte symbol_id" in error for error in errors))
        self.assertTrue(any("fremde edge_id" in error for error in errors))

    def test_missing_symbol_state_or_edge_rejected(self) -> None:
        cases = (
            (self.states()[1:], self.edge_states()),
            (self.states(), self.edge_states()[1:]),
        )
        for states, edges in cases:
            with self.subTest(symbols=len(states), edges=len(edges)):
                self.assertNotEqual([], self.errors(states, edges))

    def test_class_decorator_default_annotation_and_dynamic_targets_enumerated(self) -> None:
        kinds = {row["kind"] for row in self.symbols}
        self.assertIn("class", kinds)
        targets = {(row["edge_kind"], row["target"]) for row in self.edges}
        self.assertIn(("dynamic-import", "plugin"), targets)
        self.assertIn(("qt-connect", "helper"), targets)
        self.assertTrue(any(row["edge_kind"] == "decorator" for row in self.edges))
        self.assertTrue(any(row["edge_kind"] == "default" for row in self.edges))
        self.assertTrue(any(row["edge_kind"] == "annotation" for row in self.edges))

    def test_non_python_functions_and_schema_units_are_exact_set(self) -> None:
        files = {
            "ops.ps1": "function Invoke-Audit { Write-Output ok }\nInvoke-Audit\n",
            "launch.cmd": "@echo off\ncall :run\n:run\necho ok\n",
            "schema.sql": "CREATE TABLE audit(id INTEGER);\n",
            "config.toml": "[audit]\nenabled=true\n",
        }
        for name, text in files.items():
            (self.repo / name).write_text(text, encoding="utf-8")
        subprocess.run(["git", "add", *files], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "non-python symbols"], cwd=self.repo, check=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        symbols, _ = HARNESS.enumerate_contract_universe(
            self.repo, commit, self.RUN, self.SNAPSHOT
        )
        by_path = {row["path"]: row["kind"] for row in symbols}
        self.assertEqual("powershell-function", by_path["ops.ps1"])
        self.assertEqual("batch-label", by_path["launch.cmd"])
        self.assertEqual("schema-unit", by_path["schema.sql"])
        self.assertEqual("config-unit", by_path["config.toml"])
        self.assertLessEqual(
            next(row["line_end"] for row in symbols if row["path"] == "launch.cmd"),
            len(files["launch.cmd"].splitlines()),
        )

    def test_state_foreign_feature_runtime_reviewer_evidence_rejected(self) -> None:
        states = self.states()
        edge_states = self.edge_states()
        states[0]["feature_ids"] = ["FEAT-FOREIGN"]
        states[0]["reviewer_id"] = "REV-FOREIGN"
        states[0]["contracts"]["inputs"]["evidence_ids"] = ["E-FOREIGN"]
        states[1]["disposition"] = "runtime"
        states[1]["runtime_evidence_ids"] = ["RUNTIME-FOREIGN"]
        errors = self.errors(states, edge_states)
        self.assertTrue(any("feature_id" in error for error in errors))
        self.assertTrue(any("Reviewer" in error for error in errors))
        self.assertTrue(any("Evidence" in error for error in errors))
        self.assertTrue(any("Runtime" in error for error in errors))

    def test_incoming_edge_must_target_symbol(self) -> None:
        states = self.states()
        target = states[0]
        wrong = next(edge for edge in self.edges if edge.get("target_symbol_id") != target["symbol_id"])
        target["caller_contract"] = {
            "kind": "incoming-edges", "edge_ids": [wrong["edge_id"]],
            "evidence_ids": ["E-CALLER"],
        }
        errors = self.errors(states, self.edge_states())
        self.assertTrue(any("Zielsymbol" in error for error in errors))

    def test_pep263_python_decoding(self) -> None:
        source = "# -*- coding: latin-1 -*-\ndef grüssen(name: str = 'Welt') -> str:\n    return 'Hallo ' + name\n"
        (self.repo / "latin.py").write_bytes(source.encode("latin-1"))
        subprocess.run(["git", "add", "latin.py"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "pep263 symbol"], cwd=self.repo, check=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        symbols, edges = HARNESS.enumerate_contract_universe(
            self.repo, commit, self.RUN, self.SNAPSHOT
        )
        self.assertTrue(any(row["qualified_name"] == "grüssen" for row in symbols))
        self.assertTrue(any(row["edge_kind"] == "annotation" for row in edges if row["path"] == "latin.py"))

    def test_supplied_universe_binding_and_duplicates_rejected(self) -> None:
        rows = [{
            "feature_id": "FEAT-CONTRACT", "run_id": self.RUN,
            "audited_commit": self.commit, "snapshot_id": self.SNAPSHOT,
        }]
        valid_ids, valid_errors = HARNESS.validate_reference_universe(
            rows, "feature_id", "Featureuniversum", run_id=self.RUN,
            audited_commit=self.commit, snapshot_id=self.SNAPSHOT,
        )
        self.assertEqual({"FEAT-CONTRACT"}, valid_ids)
        self.assertEqual([], valid_errors)
        invalid = [copy.deepcopy(rows[0]), copy.deepcopy(rows[0])]
        invalid[0]["audited_commit"] = "0" * 40
        _, errors = HARNESS.validate_reference_universe(
            invalid, "feature_id", "Featureuniversum", run_id=self.RUN,
            audited_commit=self.commit, snapshot_id=self.SNAPSHOT,
        )
        self.assertTrue(any("doppelt" in error for error in errors))
        self.assertTrue(any("commit" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
