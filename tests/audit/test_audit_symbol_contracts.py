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
    TOOLING = "TOOLING-SYMBOL"

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
            "class Controller(metaclass=type):\n"
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
        binding = {
            "run_id": self.RUN, "audited_commit": self.commit,
            "tooling_commit": self.TOOLING, "snapshot_id": self.SNAPSHOT,
        }
        self.feature_records = [HARNESS.seal_record({
            "catalog_id": "CATALOG-1", "feature_id": "FEAT-CONTRACT",
            "path_id": "primary", **binding,
        })]
        self.runtime_records = [HARNESS.seal_record({
            "evidence_id": "RUNTIME-EVIDENCE", **binding,
        })]
        self.reviewer_records = [HARNESS.seal_record({"reviewer_id": "REV-A", **binding})]
        self.evidence_records = [
            HARNESS.seal_record({"evidence_id": evidence_id, **binding})
            for evidence_id in ("E-SOURCE", "E-CALLER", "E-CONTRACT", "E-EDGE", "E-NONRUNTIME")
        ]
        self.trigger_records = [HARNESS.seal_record({
            "source_id": "TRIG-DUMMY", "source_kind": "support",
            "path": "unrelated.py", "detail": "unrelated", **binding,
        })]
        self.manifests = {
            kind: HARNESS.make_artifact_manifest(
                kind, records, run_id=self.RUN, audited_commit=self.commit,
                tooling_commit=self.TOOLING, snapshot_id=self.SNAPSHOT,
            )
            for kind, records in (
                ("feature-catalog", self.feature_records),
                ("runtime-evidence", self.runtime_records),
                ("reviewer-roster", self.reviewer_records),
                ("symbol-evidence", self.evidence_records),
                ("trigger-catalog", self.trigger_records),
            )
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def states(self) -> list[dict]:
        symbol_hash = HARNESS.universe_digest(self.symbols, "symbol_id")
        edge_hash = HARNESS.universe_digest(self.edges, "edge_id")
        rows = []
        for symbol in self.symbols:
            incoming = [
                edge["edge_id"] for edge in self.edges
                if edge.get("target_symbol_id") == symbol["symbol_id"]
            ]
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
                    "kind": "incoming-edges" if incoming else "unreferenced",
                    "edge_ids": incoming,
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
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
            feature_records=self.feature_records,
            feature_manifest=self.manifests["feature-catalog"],
            runtime_records=self.runtime_records,
            runtime_manifest=self.manifests["runtime-evidence"],
            reviewer_records=self.reviewer_records,
            reviewer_manifest=self.manifests["reviewer-roster"],
            evidence_records=self.evidence_records,
            evidence_manifest=self.manifests["symbol-evidence"],
            trigger_records=self.trigger_records,
            trigger_manifest=self.manifests["trigger-catalog"],
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
        self.assertIn(("class-keyword", "type"), targets)
        collector = HARNESS.Collector("meta.py", "blob", {
            "run_id": self.RUN, "audited_commit": self.commit,
            "snapshot_id": self.SNAPSHOT,
        })
        collector.visit(HARNESS.ast.parse("class C(metaclass=make_meta()):\n    pass\n"))
        self.assertIn(("class-keyword", "make_meta"), {
            (row["edge_kind"], row["target"]) for row in collector.edges
        })
        self.assertIn(("call", "make_meta"), {
            (row["edge_kind"], row["target"]) for row in collector.edges
        })

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
        self.assertTrue(any("Incoming" in error for error in errors))

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

    def test_supplied_universe_laundering_rejected(self) -> None:
        rows = copy.deepcopy(self.feature_records)
        rows[0]["feature_id"] = "LAUNDERED"
        _, errors = HARNESS.validate_artifact_universe(
            rows, self.manifests["feature-catalog"], "feature-catalog", "catalog_id",
            run_id=self.RUN, audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        self.assertTrue(any("Artefaktmanifest" in error for error in errors))
        self.assertTrue(any("record_sha256" in error for error in errors))

    def test_actual_incoming_edges_forbid_fake_entrypoint(self) -> None:
        states = self.states()
        target = next(row for row in states if row["qualified_name"] == "helper")
        target["caller_contract"] = {
            "kind": "entrypoint", "edge_ids": [], "evidence_ids": ["E-CALLER"],
        }
        errors = self.errors(states, self.edge_states())
        self.assertTrue(any("kanonische Incoming" in error for error in errors))

    def test_entrypoint_requires_explicit_canonical_trigger(self) -> None:
        states = self.states()
        target = next(
            row for row in states
            if not any(edge.get("target_symbol_id") == row["symbol_id"] for edge in self.edges)
        )
        target["caller_contract"] = {
            "kind": "entrypoint", "edge_ids": [], "evidence_ids": ["E-CALLER"],
        }
        self.assertTrue(any("ohne kanonischen Trigger" in error for error in self.errors(states, self.edge_states())))
        trigger = HARNESS.seal_record({
            "source_id": "TRIG-EXPLICIT", "source_kind": "entrypoint",
            "path": target["path"], "detail": target["qualified_name"],
            "target_symbol_id": target["symbol_id"], "run_id": self.RUN,
            "audited_commit": self.commit, "tooling_commit": self.TOOLING,
            "snapshot_id": self.SNAPSHOT,
        })
        self.trigger_records = [trigger]
        self.manifests["trigger-catalog"] = HARNESS.make_artifact_manifest(
            "trigger-catalog", self.trigger_records, run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        self.assertEqual([], self.errors(states, self.edge_states()))

    def test_powershell_calls_and_batch_call_source_are_canonical(self) -> None:
        (self.repo / "ops.ps1").write_text(
            "function B { if ($true) { Write-Output ok } }\n"
            "function A { B }\nA\n",
            encoding="utf-8",
        )
        (self.repo / "launch.cmd").write_text(
            "@echo off\n:one\ncall :two\nexit /b\n:two\necho ok\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "ops.ps1", "launch.cmd"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "script calls"], cwd=self.repo, check=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        symbols, edges = HARNESS.enumerate_contract_universe(
            self.repo, commit, self.RUN, self.SNAPSHOT
        )
        by_name = {row["qualified_name"]: row for row in symbols if row["path"] in {"ops.ps1", "launch.cmd"}}
        ps_edge = next(row for row in edges if row["edge_kind"] == "powershell-call")
        self.assertEqual(by_name["A"]["symbol_id"], ps_edge["source_symbol_id"])
        self.assertEqual(by_name["B"]["symbol_id"], ps_edge["target_symbol_id"])
        batch_edge = next(row for row in edges if row["edge_kind"] == "batch-call")
        self.assertEqual(by_name["one"]["symbol_id"], batch_edge["source_symbol_id"])
        self.assertEqual(by_name["two"]["symbol_id"], batch_edge["target_symbol_id"])

    def test_invalid_structured_inputs_and_missing_batch_label_parse_stop(self) -> None:
        cases = (
            ("<ui>", ".ui", "broken.ui"),
            ("THIS IS NOT SQL;", ".sql", "broken.sql"),
        )
        for text, suffix, path in cases:
            with self.subTest(path=path), self.assertRaisesRegex(HARNESS.ContractError, "parser_error"):
                HARNESS._parse_structured(text, suffix, path)
        with self.assertRaisesRegex(HARNESS.ContractError, "parser_error"):
            HARNESS._parse_batch_units("@echo off\ncall :missing\n", "broken.cmd")
        with self.assertRaisesRegex(HARNESS.ContractError, "parser_error"):
            HARNESS._parse_powershell("function Broken { if () { } }", "broken.ps1")


if __name__ == "__main__":
    unittest.main()
