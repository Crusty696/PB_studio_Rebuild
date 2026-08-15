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

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="pb-symbol-contract-")
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "audit@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Audit Contract"], cwd=self.repo, check=True)
        (self.repo / "app.py").write_text(
            "import json\n"
            "from importlib import import_module\n"
            "def helper(value):\n    return json.dumps(value)\n"
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
        self.assertEqual(2, len(self.symbols))
        self.assertTrue(self.edges)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def states(self) -> list[dict]:
        symbol_hash = HARNESS.universe_digest(self.symbols, "symbol_id")
        edge_hash = HARNESS.universe_digest(self.edges, "edge_id")
        rows = []
        for symbol in self.symbols:
            contracts = {
                key: {"status": "reviewed", "evidence": [f"{symbol['path']}:{symbol['line_start']}"]}
                for key in HARNESS.CONTRACT_KEYS
            }
            rows.append({
                **symbol,
                "symbols_sha256": symbol_hash,
                "edges_sha256": edge_hash,
                "role": "support",
                "feature_ids": ["FEAT-CONTRACT"],
                "caller_contract": {
                    "kind": "entrypoint",
                    "evidence": [f"{symbol['path']}:{symbol['line_start']}"],
                },
                "contracts": contracts,
                "disposition": "non-runtime",
                "runtime_evidence_ids": [],
                "non_runtime_contract": {
                    "kind": "static-contract",
                    "ref": f"{symbol['path']}:{symbol['line_start']}",
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
            "evidence": [f"{edge['path']}:{edge['line']}"],
        } for edge in self.edges]

    def errors(self, states: list[dict], edges: list[dict]) -> list[str]:
        return HARNESS.validate_contracts(
            self.symbols, self.edges, states, edges, run_id=self.RUN,
            audited_commit=self.commit, snapshot_id=self.SNAPSHOT,
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


if __name__ == "__main__":
    unittest.main()
