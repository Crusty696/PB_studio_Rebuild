from __future__ import annotations

import copy
import hashlib
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
    PLAN = "PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15"
    FROZEN = "2026-08-15T00:00:00+00:00"
    SIGNED = "2026-08-15T12:00:00+00:00"
    EXPIRES = "2099-08-16T00:00:00+00:00"

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
            self.repo, self.commit, self.RUN, self.SNAPSHOT,
            tooling_commit=self.TOOLING, signed_at=self.FROZEN,
        )
        self.assertEqual(4, len(self.symbols))
        self.assertTrue(self.edges)
        binding = {
            "run_id": self.RUN, "audited_commit": self.commit,
            "tooling_commit": self.TOOLING, "snapshot_id": self.SNAPSHOT,
            "signed_at": self.SIGNED,
        }
        self.feature_records = [HARNESS.seal_record({
            "catalog_id": "CATALOG-1", "feature_id": "FEAT-CONTRACT",
            "path_id": "primary", **binding,
        })]
        covered_symbols = sorted(symbol["symbol_id"] for symbol in self.symbols[:2])
        self.runtime_receipt = {
            "plan_id": self.PLAN, "run_id": self.RUN,
            "runtime_run_id": "LIVE-CONTRACT", "audited_commit": self.commit,
            "tooling_commit": self.TOOLING, "snapshot_id": self.SNAPSHOT,
            "scenario_id": "SCN-CONTRACT", "scenario_sha256": "a" * 64,
            "timestamp": self.SIGNED,
            "covered_feature_paths": ["FEAT-CONTRACT/primary"],
            "covered_symbol_ids": covered_symbols,
            "covered_axes": ["executed", "live_evidence", "result"],
            "authority": {}, "audit_contract": {}, "scenario_catalog": {},
            "sealed_contract_inputs": [], "materialization": {}, "runner": {},
            "environment": {}, "observer": {}, "input": {}, "inputs": [],
            "harness": {}, "target": {}, "stdout": {}, "stderr": {}, "exit": {},
            "trace": {}, "postcondition": {}, "artifacts": [],
            "final_integrity_sha256": "b" * 64,
        }
        self.runtime_receipt["evidence_id"] = "sha256:" + hashlib.sha256(
            HARNESS._canonical({
                key: value for key, value in self.runtime_receipt.items()
                if key != "evidence_id"
            })
        ).hexdigest()
        runtime_data = HARNESS._canonical(self.runtime_receipt) + b"\n"
        runtime_ref = "proof/runtime.json"
        runtime_target = self.repo / runtime_ref
        runtime_target.parent.mkdir(parents=True, exist_ok=True)
        runtime_target.write_bytes(runtime_data)
        self.runtime_records = [HARNESS.seal_record({
            "evidence_id": self.runtime_receipt["evidence_id"],
            "evidence_kind": "runtime", "runtime_run_id": "LIVE-CONTRACT",
            "covered_feature_paths": ["FEAT-CONTRACT/primary"],
            "covered_symbol_ids": covered_symbols,
            "covered_axes": ["executed", "live_evidence", "result"],
            "proof_ref": runtime_ref,
            "proof_sha256": hashlib.sha256(runtime_data).hexdigest(),
            "run_id": self.RUN, "audited_commit": self.commit,
            "tooling_commit": self.TOOLING, "snapshot_id": self.SNAPSHOT,
            "timestamp": self.SIGNED,
        })]
        self.reviewer_records = [HARNESS.seal_record({"reviewer_id": "REV-A", **binding})]
        self.evidence_records = []
        for symbol in self.symbols:
            self.evidence_records.append(HARNESS.seal_record({
                "evidence_id": self.symbol_evidence_id(symbol["symbol_id"]),
                "evidence_kind": "symbol-review", "symbol_id": symbol["symbol_id"],
                "reviewer_id": "REV-A", "path": symbol["path"],
                "source_blob_sha256": symbol["source_blob_sha256"],
                "proof_ref": f"proof/{symbol['symbol_id']}.json", **binding,
            }))
        for edge in self.edges:
            self.evidence_records.append(HARNESS.seal_record({
                "evidence_id": self.edge_evidence_id(edge["edge_id"]),
                "evidence_kind": "edge-review", "edge_id": edge["edge_id"],
                "reviewer_id": "REV-A", "path": edge["path"],
                "source_blob_sha256": edge["source_blob_sha256"],
                "proof_ref": f"proof/{edge['edge_id']}.json", **binding,
            }))
        trigger_core = {
            "source_kind": "entrypoint", "path": "unrelated.py",
            "line": 1, "column": 0, "detail": "unrelated",
            "source_blob_sha256": "a" * 64, **binding,
        }
        trigger_core["source_id"] = HARNESS._trigger_source_id(
            trigger_core["source_kind"], trigger_core["path"], trigger_core["line"],
            trigger_core["column"], trigger_core["detail"],
        )
        self.trigger_records = [HARNESS.seal_record(trigger_core)]
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
        proof_artifacts = {
            f"runtime-proof:{self.runtime_records[0]['evidence_id']}": (
                HARNESS.file_contract_entry(runtime_data, runtime_ref)
            )
        }
        for row in self.evidence_records:
            fields = [
                "evidence_id", "evidence_kind", "reviewer_id", "path",
                "source_blob_sha256",
            ]
            fields.append("symbol_id" if "symbol_id" in row else "edge_id")
            proof = {field: row[field] for field in fields}
            proof["schema_version"] = 1
            data = HARNESS._canonical(proof)
            target = self.repo / row["proof_ref"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            row["proof_sha256"] = hashlib.sha256(data).hexdigest()
            row.update(HARNESS.seal_record(row))
            proof_artifacts[f"symbol-proof:{row['evidence_id']}"] = (
                HARNESS.file_contract_entry(data, row["proof_ref"])
            )
        self.manifests["symbol-evidence"] = HARNESS.make_artifact_manifest(
            "symbol-evidence", self.evidence_records, run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        self.manifests["runtime-evidence"] = HARNESS.make_artifact_manifest(
            "runtime-evidence", self.runtime_records, run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        audit_artifacts = {
            key: HARNESS.file_contract_entry(
                b"{}", f"evidence/global/audit/{key}.json"
            )
            for key in HARNESS.AUDIT_ARTIFACT_KEYS
        }
        audit_artifacts.update({
            "feature-catalog": HARNESS.artifact_contract_entry(
                self.feature_records, "evidence/features.jsonl"
            ),
            "symbol-catalog": HARNESS.artifact_contract_entry(
                self.symbols, "evidence/symbols.jsonl"
            ),
            "edge-catalog": HARNESS.artifact_contract_entry(
                self.edges, "evidence/edges.jsonl"
            ),
            "trigger-universe": HARNESS.artifact_contract_entry(
                self.trigger_records, "evidence/triggers.jsonl"
            ),
        })
        audit_core = {
            "schema_version": 1, "plan_id": self.PLAN, "run_id": self.RUN,
            "audited_commit": self.commit, "tooling_commit": self.TOOLING,
            "snapshot_id": self.SNAPSHOT, "frozen_at": self.FROZEN,
            "expires_at": self.EXPIRES,
            "artifacts": audit_artifacts,
        }
        self.audit_contract = HARNESS.seal_audit_contract(audit_core)
        self.contract_sha = self.audit_contract["contract_sha256"]
        evidence_core = {
            "schema_version": 1, "plan_id": self.PLAN, "run_id": self.RUN,
            "audited_commit": self.commit, "tooling_commit": self.TOOLING,
            "snapshot_id": self.SNAPSHOT,
            "audit_contract_sha256": self.contract_sha,
            "completed_at": self.SIGNED,
            "artifacts": {
                **{
                    key: HARNESS.file_contract_entry(
                        b"{}", f"evidence/global/evidence/{key}.json"
                    )
                    for key in HARNESS.EVIDENCE_ARTIFACT_KEYS
                },
                "symbol-state": HARNESS.artifact_contract_entry(
                    self.states(), "evidence/symbol-state.jsonl"
                ),
                "edge-state": HARNESS.artifact_contract_entry(
                    self.edge_states(), "evidence/edge-state.jsonl"
                ),
                "symbol-state-evidence": HARNESS.artifact_contract_entry(
                    self.evidence_records, "evidence/symbol-state-evidence.jsonl"
                ),
                "reviewer-roster": HARNESS.artifact_contract_entry(
                    self.reviewer_records, "evidence/reviewers.jsonl"
                ),
                "runtime-evidence": HARNESS.artifact_contract_entry(
                    self.runtime_records, "evidence/runtime.jsonl"
                ),
                **proof_artifacts,
            },
        }
        self.evidence_contract = HARNESS.seal_evidence_contract(evidence_core)
        self.evidence_contract_sha = self.evidence_contract["evidence_contract_sha256"]

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def symbol_evidence_id(symbol_id: str) -> str:
        return f"E-SYMBOL-{symbol_id}"

    @staticmethod
    def edge_evidence_id(edge_id: str) -> str:
        return f"E-EDGE-{edge_id}"

    def states(self) -> list[dict]:
        symbol_hash = HARNESS.universe_digest(self.symbols, "symbol_id")
        edge_hash = HARNESS.universe_digest(self.edges, "edge_id")
        rows = []
        for symbol in self.symbols:
            evidence_id = self.symbol_evidence_id(symbol["symbol_id"])
            is_runtime = symbol["symbol_id"] in self.runtime_records[0]["covered_symbol_ids"]
            incoming = [
                edge["edge_id"] for edge in self.edges
                if edge.get("target_symbol_id") == symbol["symbol_id"]
            ]
            contracts = {
                key: {"status": "reviewed", "evidence_ids": [evidence_id]}
                for key in HARNESS.CONTRACT_KEYS
            }
            row = {
                **symbol,
                "symbols_sha256": symbol_hash,
                "edges_sha256": edge_hash,
                "role": "support",
                "feature_ids": ["FEAT-CONTRACT"],
                "reviewer_id": "REV-A",
                "caller_contract": {
                    "kind": "incoming-edges" if incoming else "unreferenced",
                    "edge_ids": incoming,
                    "evidence_ids": [evidence_id],
                },
                "contracts": contracts,
                "disposition": "runtime" if is_runtime else "non-runtime",
                "runtime_evidence_ids": [self.runtime_records[0]["evidence_id"]] if is_runtime else [],
                "signed_at": self.SIGNED,
            }
            if not is_runtime:
                row["non_runtime_contract"] = {
                    "kind": "static-contract", "evidence_id": evidence_id,
                    "reason": "Contractfixture ohne Runtimebehauptung",
                }
            rows.append(row)
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
            "evidence_ids": [self.edge_evidence_id(edge["edge_id"])],
            "signed_at": self.SIGNED,
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
            audit_contract=self.audit_contract,
            expected_contract_sha256=self.contract_sha,
            evidence_contract=self.evidence_contract,
            expected_evidence_contract_sha256=self.evidence_contract_sha,
            evidence_root=self.repo,
        )

    def test_positive_minimal(self) -> None:
        before = (self.symbols, self.edges)
        (self.repo / "app.py").write_text("raise RuntimeError('dirty')\n", encoding="utf-8")
        after = HARNESS.enumerate_contract_universe(
            self.repo, self.commit, self.RUN, self.SNAPSHOT,
            tooling_commit=self.TOOLING, signed_at=self.FROZEN,
        )
        self.assertEqual(before, after, "Enumerator darf Dirty-Workingtree nicht lesen")
        self.assertEqual([], self.errors(self.states(), self.edge_states()))

    def test_global_contract_exact_sets_required(self) -> None:
        self.assertTrue(HARNESS.validate_evidence_contract(
            [], self.evidence_contract_sha, self.audit_contract, plan_id=self.PLAN,
            run_id=self.RUN, audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        ))
        for key in HARNESS.EVIDENCE_ARTIFACT_KEYS:
            contract = copy.deepcopy(self.evidence_contract)
            del contract["artifacts"][key]
            contract = HARNESS.seal_evidence_contract({
                name: value for name, value in contract.items()
                if name != "evidence_contract_sha256"
            })
            errors = HARNESS.validate_evidence_contract(
                contract, contract["evidence_contract_sha256"], self.audit_contract,
                plan_id=self.PLAN, run_id=self.RUN, audited_commit=self.commit,
                tooling_commit=self.TOOLING, snapshot_id=self.SNAPSHOT,
            )
            self.assertTrue(any("Exact-Set" in error for error in errors), key)
        contract = copy.deepcopy(self.audit_contract)
        contract["artifacts"]["foreign-static"] = HARNESS.file_contract_entry(
            b"{}", "evidence/foreign.json"
        )
        contract = HARNESS.seal_audit_contract({
            name: value for name, value in contract.items() if name != "contract_sha256"
        })
        errors = HARNESS.validate_audit_contract(
            contract, contract["contract_sha256"], plan_id=self.PLAN,
            run_id=self.RUN, audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        self.assertTrue(any("Exact-Set" in error for error in errors))
        evidence = copy.deepcopy(self.evidence_contract)
        evidence["artifacts"]["reviewer-signoff:bad role:session"] = (
            HARNESS.file_contract_entry(b"{}", "evidence/invalid-signoff.json")
        )
        evidence = HARNESS.seal_evidence_contract({
            name: value for name, value in evidence.items()
            if name != "evidence_contract_sha256"
        })
        errors = HARNESS.validate_evidence_contract(
            evidence, evidence["evidence_contract_sha256"], self.audit_contract,
            plan_id=self.PLAN, run_id=self.RUN, audited_commit=self.commit,
            tooling_commit=self.TOOLING, snapshot_id=self.SNAPSHOT,
        )
        self.assertTrue(any("Exact-Set" in error for error in errors))

    def test_resealed_trigger_schema_and_source_kind_matrix_rejected(self) -> None:
        base_triggers = copy.deepcopy(self.trigger_records)
        base_audit = copy.deepcopy(self.audit_contract)
        base_evidence = copy.deepcopy(self.evidence_contract)

        def validate(triggers):
            manifest = HARNESS.make_artifact_manifest(
                "trigger-catalog", triggers, run_id=self.RUN,
                audited_commit=self.commit, tooling_commit=self.TOOLING,
                snapshot_id=self.SNAPSHOT,
            )
            audit = copy.deepcopy(base_audit)
            audit["artifacts"]["trigger-universe"] = HARNESS.artifact_contract_entry(
                triggers, "evidence/triggers.jsonl"
            )
            audit = HARNESS.seal_audit_contract({
                key: value for key, value in audit.items() if key != "contract_sha256"
            })
            evidence = copy.deepcopy(base_evidence)
            evidence["audit_contract_sha256"] = audit["contract_sha256"]
            evidence = HARNESS.seal_evidence_contract({
                key: value for key, value in evidence.items()
                if key != "evidence_contract_sha256"
            })
            return HARNESS.validate_contracts(
                self.symbols, self.edges, self.states(), self.edge_states(),
                run_id=self.RUN, audited_commit=self.commit,
                tooling_commit=self.TOOLING, snapshot_id=self.SNAPSHOT,
                feature_records=self.feature_records,
                feature_manifest=self.manifests["feature-catalog"],
                runtime_records=self.runtime_records,
                runtime_manifest=self.manifests["runtime-evidence"],
                reviewer_records=self.reviewer_records,
                reviewer_manifest=self.manifests["reviewer-roster"],
                evidence_records=self.evidence_records,
                evidence_manifest=self.manifests["symbol-evidence"],
                trigger_records=triggers, trigger_manifest=manifest,
                audit_contract=audit,
                expected_contract_sha256=audit["contract_sha256"],
                evidence_contract=evidence,
                expected_evidence_contract_sha256=evidence["evidence_contract_sha256"],
                evidence_root=self.repo,
            )

        for value in ([], {}, [["entrypoint"]], [None], True, 1, None, "", " ", "foreign"):
            triggers = copy.deepcopy(base_triggers)
            triggers[0]["source_kind"] = value
            triggers[0] = HARNESS.seal_record(triggers[0])
            self.assertTrue(
                any("source_kind ungueltig" in error for error in validate(triggers)),
                repr(value),
            )

        for operation in ("extra", "missing"):
            triggers = copy.deepcopy(base_triggers)
            if operation == "extra":
                triggers[0]["foreign"] = {"nested": ["field"]}
            else:
                triggers[0].pop("detail")
            triggers[0] = HARNESS.seal_record(triggers[0])
            self.assertTrue(
            any("Schemafelder nicht exakt" in error for error in validate(triggers)),
                operation,
            )

    def test_resealed_trigger_locator_field_matrix_and_all_generator_kinds(self) -> None:
        base_audit = copy.deepcopy(self.audit_contract)
        base_evidence = copy.deepcopy(self.evidence_contract)

        def validate(triggers):
            manifest = HARNESS.make_artifact_manifest(
                "trigger-catalog", triggers, run_id=self.RUN,
                audited_commit=self.commit, tooling_commit=self.TOOLING,
                snapshot_id=self.SNAPSHOT,
            )
            audit = copy.deepcopy(base_audit)
            audit["artifacts"]["trigger-universe"] = HARNESS.artifact_contract_entry(
                triggers, "evidence/triggers.jsonl"
            )
            audit = HARNESS.seal_audit_contract({
                key: value for key, value in audit.items() if key != "contract_sha256"
            })
            evidence = copy.deepcopy(base_evidence)
            evidence["audit_contract_sha256"] = audit["contract_sha256"]
            evidence = HARNESS.seal_evidence_contract({
                key: value for key, value in evidence.items()
                if key != "evidence_contract_sha256"
            })
            return HARNESS.validate_contracts(
                self.symbols, self.edges, self.states(), self.edge_states(),
                run_id=self.RUN, audited_commit=self.commit,
                tooling_commit=self.TOOLING, snapshot_id=self.SNAPSHOT,
                feature_records=self.feature_records,
                feature_manifest=self.manifests["feature-catalog"],
                runtime_records=self.runtime_records,
                runtime_manifest=self.manifests["runtime-evidence"],
                reviewer_records=self.reviewer_records,
                reviewer_manifest=self.manifests["reviewer-roster"],
                evidence_records=self.evidence_records,
                evidence_manifest=self.manifests["symbol-evidence"],
                trigger_records=triggers, trigger_manifest=manifest,
                audit_contract=audit,
                expected_contract_sha256=audit["contract_sha256"],
                evidence_contract=evidence,
                expected_evidence_contract_sha256=evidence["evidence_contract_sha256"],
                evidence_root=self.repo,
            )

        base = copy.deepcopy(self.trigger_records[0])
        matrices = {
            "source_id": (" ", [], {}, None, True, 1, "TRIG-" + "0" * 24),
            "path": (
                [], {}, None, True, 1, "", " ", "/abs.py", "C:/abs.py",
                "../x.py", "a\\b.py", "./a.py", "a\0b.py",
            ),
            "line": ([], {}, None, True, 0, -1, 1.5, "1"),
            "column": ([], {}, None, True, -1, 1.5, "0"),
            "detail": ([], {}, None, True, 1, "", " ", " padded "),
            "source_blob_sha256": ([], {}, None, True, 1, "", "A" * 64, "g" * 64, "a" * 63),
        }
        tokens = {
            "source_id": "source_id nicht deterministisch",
            "path": "path ungueltig", "line": "line ungueltig",
            "column": "column ungueltig", "detail": "detail ungueltig",
            "source_blob_sha256": "source_blob_sha256 ungueltig",
        }
        for field, values in matrices.items():
            for value in values:
                triggers = [copy.deepcopy(base)]
                triggers[0][field] = value
                triggers[0] = HARNESS.seal_record(triggers[0])
                self.assertTrue(
                    any(tokens[field] in error for error in validate(triggers)),
                    f"{field}={value!r}",
                )

        source = self.symbols[0]
        core = {
            "source_kind": "entrypoint", "path": source["path"],
            "line": source["line_start"], "column": 0,
            "detail": source["qualified_name"], "source_blob_sha256": "f" * 64,
            "run_id": self.RUN, "audited_commit": self.commit,
            "tooling_commit": self.TOOLING, "snapshot_id": self.SNAPSHOT,
            "signed_at": self.SIGNED,
        }
        core["source_id"] = HARNESS._trigger_source_id(
            core["source_kind"], core["path"], core["line"], core["column"], core["detail"]
        )
        errors = validate([HARNESS.seal_record(core)])
        self.assertTrue(any("kanonischen Sourcekatalog" in error for error in errors))

        binding = {
            "run_id": self.RUN, "audited_commit": self.commit,
            "tooling_commit": self.TOOLING, "snapshot_id": self.SNAPSHOT,
            "signed_at": self.SIGNED,
        }
        triggers = []
        for index, kind in enumerate(sorted(HARNESS.TRIGGER_SOURCE_KINDS), 1):
            core = {
                "source_kind": kind, "path": f"triggers/{index}.py",
                "line": index, "column": index - 1, "detail": f"trigger-{kind}",
                "source_blob_sha256": f"{index:064x}", **binding,
            }
            core["source_id"] = HARNESS._trigger_source_id(
                kind, core["path"], core["line"], core["column"], core["detail"]
            )
            triggers.append(HARNESS.seal_record(core))
        self.assertEqual(24, len(triggers))
        self.assertEqual([], validate(triggers))

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
            self.repo, commit, self.RUN, self.SNAPSHOT,
            tooling_commit=self.TOOLING, signed_at=self.FROZEN,
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

    def test_fully_resealed_foreign_runtime_package_is_rejected(self) -> None:
        states = self.states()
        original_data = (self.repo / self.runtime_records[0]["proof_ref"]).read_bytes()
        receipt = copy.deepcopy(self.runtime_receipt)
        receipt["covered_symbol_ids"] = ["FOREIGN-SYMBOL"]
        receipt["evidence_id"] = "sha256:" + hashlib.sha256(HARNESS._canonical({
            key: value for key, value in receipt.items() if key != "evidence_id"
        })).hexdigest()
        data = HARNESS._canonical(receipt) + b"\n"
        runtime = copy.deepcopy(self.runtime_records)
        runtime[0]["evidence_id"] = receipt["evidence_id"]
        runtime[0]["covered_symbol_ids"] = receipt["covered_symbol_ids"]
        runtime[0]["proof_sha256"] = hashlib.sha256(data).hexdigest()
        runtime[0] = HARNESS.seal_record(runtime[0])
        manifest = HARNESS.make_artifact_manifest(
            "runtime-evidence", runtime, run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        (self.repo / runtime[0]["proof_ref"]).write_bytes(data)
        contract = copy.deepcopy(self.evidence_contract)
        contract["artifacts"]["runtime-evidence"] = HARNESS.artifact_contract_entry(
            runtime, "evidence/runtime.jsonl"
        )
        for key in list(contract["artifacts"]):
            if key.startswith("runtime-proof:"):
                del contract["artifacts"][key]
        contract["artifacts"][f"runtime-proof:{runtime[0]['evidence_id']}"] = (
            HARNESS.file_contract_entry(data, runtime[0]["proof_ref"])
        )
        contract = HARNESS.seal_evidence_contract({
            key: value for key, value in contract.items()
            if key != "evidence_contract_sha256"
        })
        old_runtime, old_manifest = self.runtime_records, self.manifests["runtime-evidence"]
        old_contract, old_sha = self.evidence_contract, self.evidence_contract_sha
        self.runtime_records, self.manifests["runtime-evidence"] = runtime, manifest
        self.evidence_contract, self.evidence_contract_sha = (
            contract, contract["evidence_contract_sha256"]
        )
        try:
            errors = self.errors(states, self.edge_states())
        finally:
            (self.repo / runtime[0]["proof_ref"]).write_bytes(original_data)
            self.runtime_records, self.manifests["runtime-evidence"] = old_runtime, old_manifest
            self.evidence_contract, self.evidence_contract_sha = old_contract, old_sha
        self.assertTrue(any("covered_symbol_ids" in error for error in errors))

    def test_runtime_evidence_schema_fks_and_exact_consumption_rejected(self) -> None:
        states = self.states()
        runtime_state = next(row for row in states if row["disposition"] == "runtime")
        runtime_state["disposition"] = "non-runtime"
        runtime_state["runtime_evidence_ids"] = []
        runtime_state["non_runtime_contract"] = {
            "kind": "static-contract",
            "evidence_id": self.symbol_evidence_id(runtime_state["symbol_id"]),
            "reason": "orphan repro",
        }
        self.assertTrue(any("Runtime-Evidence-Exact-Set" in error for error in self.errors(states, self.edge_states())))

        states = self.states()
        other = next(row for row in states if row["disposition"] != "runtime")
        other["disposition"] = "runtime"
        other["runtime_evidence_ids"] = [self.runtime_records[0]["evidence_id"]]
        other.pop("non_runtime_contract")
        errors = self.errors(states, self.edge_states())
        self.assertTrue(any("fremd" in error for error in errors))
        self.assertTrue(any("Runtime-Evidence-Symbol-FK" in error for error in errors))

        for field, value, token in (
            ("evidence_id", "sha256:" + "f" * 64, "evidence_id"),
            ("runtime_run_id", "LIVE-FOREIGN", "runtime_run_id"),
            ("covered_feature_paths", ["FEAT-FOREIGN/primary"], "covered_feature_paths"),
            ("covered_symbol_ids", ["FOREIGN-SYMBOL"], "covered_symbol_ids"),
            ("covered_axes", ["unknown-axis"], "covered_axes"),
            ("proof_sha256", "e" * 64, "proof_sha256"),
            ("proof_ref", "proof/missing-runtime.json", "Rich-Receipt"),
            ("timestamp", "2026-08-15T13:00:00+00:00", "timestamp"),
            ("evidence_kind", "runtime ", "evidence_kind"),
        ):
            runtime = copy.deepcopy(self.runtime_records)
            runtime[0][field] = value
            runtime[0] = HARNESS.seal_record(runtime[0])
            old_runtime, old_manifest = self.runtime_records, self.manifests["runtime-evidence"]
            self.runtime_records = runtime
            self.manifests["runtime-evidence"] = HARNESS.make_artifact_manifest(
                "runtime-evidence", runtime, run_id=self.RUN,
                audited_commit=self.commit, tooling_commit=self.TOOLING,
                snapshot_id=self.SNAPSHOT,
            )
            try:
                errors = self.errors(self.states(), self.edge_states())
            finally:
                self.runtime_records, self.manifests["runtime-evidence"] = old_runtime, old_manifest
            self.assertTrue(any(token in error for error in errors), field)

        runtime = copy.deepcopy(self.runtime_records)
        runtime[0]["extra"] = "not-allowed"
        runtime[0] = HARNESS.seal_record(runtime[0])
        old_runtime, old_manifest = self.runtime_records, self.manifests["runtime-evidence"]
        self.runtime_records = runtime
        self.manifests["runtime-evidence"] = HARNESS.make_artifact_manifest(
            "runtime-evidence", runtime, run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        try:
            errors = self.errors(self.states(), self.edge_states())
        finally:
            self.runtime_records, self.manifests["runtime-evidence"] = old_runtime, old_manifest
        self.assertTrue(any("Schemafelder nicht exakt" in error for error in errors))

    def test_symbol_proof_sha256_is_mandatory_and_byte_bound(self) -> None:
        records = copy.deepcopy(self.evidence_records)
        records[0]["proof_sha256"] = "f" * 64
        records[0] = HARNESS.seal_record(records[0])
        old_records, old_manifest = self.evidence_records, self.manifests["symbol-evidence"]
        self.evidence_records = records
        self.manifests["symbol-evidence"] = HARNESS.make_artifact_manifest(
            "symbol-evidence", records, run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        try:
            errors = self.errors(self.states(), self.edge_states())
        finally:
            self.evidence_records, self.manifests["symbol-evidence"] = old_records, old_manifest
        self.assertTrue(any("proof_sha256" in error for error in errors))

    def test_runtime_mini_proof_cannot_pose_as_rich_receipt(self) -> None:
        original = (self.repo / self.runtime_records[0]["proof_ref"]).read_bytes()
        mini = {
            key: self.runtime_receipt[key]
            for key in (
                "evidence_id", "run_id", "runtime_run_id", "audited_commit",
                "tooling_commit", "snapshot_id", "timestamp", "covered_feature_paths",
                "covered_symbol_ids", "covered_axes",
            )
        }
        data = HARNESS._canonical(mini) + b"\n"
        runtime = copy.deepcopy(self.runtime_records)
        runtime[0]["proof_sha256"] = hashlib.sha256(data).hexdigest()
        runtime[0] = HARNESS.seal_record(runtime[0])
        contract = copy.deepcopy(self.evidence_contract)
        contract["artifacts"]["runtime-evidence"] = HARNESS.artifact_contract_entry(
            runtime, "evidence/runtime.jsonl"
        )
        contract["artifacts"][f"runtime-proof:{runtime[0]['evidence_id']}"] = (
            HARNESS.file_contract_entry(data, runtime[0]["proof_ref"])
        )
        contract = HARNESS.seal_evidence_contract({
            key: value for key, value in contract.items()
            if key != "evidence_contract_sha256"
        })
        old_runtime, old_manifest = self.runtime_records, self.manifests["runtime-evidence"]
        old_contract, old_sha = self.evidence_contract, self.evidence_contract_sha
        (self.repo / runtime[0]["proof_ref"]).write_bytes(data)
        self.runtime_records = runtime
        self.manifests["runtime-evidence"] = HARNESS.make_artifact_manifest(
            "runtime-evidence", runtime, run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        self.evidence_contract = contract
        self.evidence_contract_sha = contract["evidence_contract_sha256"]
        try:
            errors = self.errors(self.states(), self.edge_states())
        finally:
            (self.repo / runtime[0]["proof_ref"]).write_bytes(original)
            self.runtime_records, self.manifests["runtime-evidence"] = old_runtime, old_manifest
            self.evidence_contract, self.evidence_contract_sha = old_contract, old_sha
        self.assertTrue(any("Rich-Receipt Schemafelder" in error for error in errors))

    def test_evidence_inverse_closure_unique_lists_and_state_fks_rejected(self) -> None:
        states = self.states()
        evidence_id = states[0]["caller_contract"]["evidence_ids"][0]
        states[0]["caller_contract"]["evidence_ids"] = [evidence_id, evidence_id]
        self.assertTrue(any("Duplikat" in error for error in self.errors(states, self.edge_states())))

        states = self.states()
        states[0]["reviewer_id"] = "REV-FOREIGN"
        states[0]["signed_at"] = "2026-08-15T13:00:00+00:00"
        errors = self.errors(states, self.edge_states())
        self.assertTrue(any("Evidence-Reviewer-FK" in error for error in errors))
        self.assertTrue(any("Evidence-signed_at-FK" in error for error in errors))

        edges = self.edge_states()
        edges[0]["reviewer_id"] = "REV-FOREIGN"
        edges[0]["signed_at"] = "2026-08-15T13:00:00+00:00"
        errors = self.errors(self.states(), edges)
        self.assertTrue(any("Evidence-Reviewer-FK" in error for error in errors))
        self.assertTrue(any("Evidence-signed_at-FK" in error for error in errors))

        states = self.states()
        runtime_state = next(row for row in states if row["disposition"] == "runtime")
        runtime_state["reviewer_id"] = "REV-FOREIGN"
        runtime_state["signed_at"] = "2026-08-15T13:00:00+00:00"
        errors = self.errors(states, self.edge_states())
        self.assertTrue(any("unbekannter Reviewer" in error for error in errors))
        self.assertTrue(any("signed_at ausser Zeitgrenze" in error for error in errors))

        orphan = copy.deepcopy(self.evidence_records[0])
        orphan["evidence_id"], orphan["proof_ref"] = "E-ORPHAN", "proof/orphan.json"
        orphan = HARNESS.seal_record(orphan)
        records = [*self.evidence_records, orphan]
        proof = {field: orphan[field] for field in (
            "evidence_id", "evidence_kind", "reviewer_id", "path",
            "source_blob_sha256", "symbol_id",
        )}
        proof["schema_version"] = 1
        data = HARNESS._canonical(proof)
        (self.repo / orphan["proof_ref"]).write_bytes(data)
        contract = copy.deepcopy(self.evidence_contract)
        contract["artifacts"]["symbol-state-evidence"] = HARNESS.artifact_contract_entry(
            records, "evidence/symbol-state-evidence.jsonl"
        )
        contract["artifacts"]["symbol-proof:E-ORPHAN"] = HARNESS.file_contract_entry(
            data, orphan["proof_ref"]
        )
        contract = HARNESS.seal_evidence_contract({
            key: value for key, value in contract.items()
            if key != "evidence_contract_sha256"
        })
        old_records, old_manifest = self.evidence_records, self.manifests["symbol-evidence"]
        old_contract, old_sha = self.evidence_contract, self.evidence_contract_sha
        self.evidence_records = records
        self.manifests["symbol-evidence"] = HARNESS.make_artifact_manifest(
            "symbol-evidence", records, run_id=self.RUN, audited_commit=self.commit,
            tooling_commit=self.TOOLING, snapshot_id=self.SNAPSHOT,
        )
        self.evidence_contract, self.evidence_contract_sha = contract, contract["evidence_contract_sha256"]
        try:
            errors = self.errors(self.states(), self.edge_states())
        finally:
            self.evidence_records, self.manifests["symbol-evidence"] = old_records, old_manifest
            self.evidence_contract, self.evidence_contract_sha = old_contract, old_sha
        self.assertTrue(any("Evidence-Closure" in error for error in errors))

        for prefix in ("symbol-proof", "runtime-proof"):
            contract = copy.deepcopy(self.evidence_contract)
            descriptor = next(
                value for key, value in contract["artifacts"].items()
                if key.startswith(f"{prefix}:")
            )
            contract["artifacts"][f"{prefix}:FOREIGN"] = copy.deepcopy(descriptor)
            contract = HARNESS.seal_evidence_contract({
                key: value for key, value in contract.items()
                if key != "evidence_contract_sha256"
            })
            self.evidence_contract, self.evidence_contract_sha = (
                contract, contract["evidence_contract_sha256"]
            )
            try:
                errors = self.errors(self.states(), self.edge_states())
            finally:
                self.evidence_contract, self.evidence_contract_sha = old_contract, old_sha
            self.assertTrue(any(f"{prefix}-Key-Exact-Set" in error for error in errors))

    def test_resealed_state_edge_and_contract_exact_fields_rejected(self) -> None:
        original_contract, original_sha = self.evidence_contract, self.evidence_contract_sha

        def validate(states, edges):
            contract = copy.deepcopy(original_contract)
            contract["artifacts"]["symbol-state"] = HARNESS.artifact_contract_entry(
                states, "evidence/symbol-state.jsonl"
            )
            contract["artifacts"]["edge-state"] = HARNESS.artifact_contract_entry(
                edges, "evidence/edge-state.jsonl"
            )
            contract = HARNESS.seal_evidence_contract({
                key: value for key, value in contract.items()
                if key != "evidence_contract_sha256"
            })
            self.evidence_contract, self.evidence_contract_sha = (
                contract, contract["evidence_contract_sha256"]
            )
            try:
                return self.errors(states, edges)
            finally:
                self.evidence_contract, self.evidence_contract_sha = original_contract, original_sha

        for operation in ("extra", "missing"):
            states, edges = self.states(), self.edge_states()
            if operation == "extra":
                states[0]["unexpected"] = True
            else:
                states[0].pop("role")
            self.assertTrue(any("Schemafelder nicht exakt" in error for error in validate(states, edges)), operation)

        for operation in ("extra", "missing"):
            states, edges = self.states(), self.edge_states()
            if operation == "extra":
                edges[0]["unexpected"] = True
            else:
                edges[0].pop("column")
            self.assertTrue(any("Schemafelder nicht exakt" in error for error in validate(states, edges)), operation)

            states, edges = self.states(), self.edge_states()
            if operation == "extra":
                states[0]["contracts"]["unexpected"] = {
                    "status": "reviewed", "evidence_ids": [
                        self.symbol_evidence_id(states[0]["symbol_id"])
                    ],
                }
            else:
                states[0]["contracts"].pop(HARNESS.CONTRACT_KEYS[0])
            self.assertTrue(any("Contract-Objekt Felder nicht exakt" in error for error in validate(states, edges)), operation)

            states, edges = self.states(), self.edge_states()
            cell = states[0]["contracts"][HARNESS.CONTRACT_KEYS[0]]
            if operation == "extra":
                cell["unexpected"] = True
            else:
                cell.pop("evidence_ids")
            self.assertTrue(any("Schemafelder nicht exakt" in error for error in validate(states, edges)), operation)

    def test_resealed_caller_incoming_and_non_runtime_contract_rejected(self) -> None:
        original_contract, original_sha = self.evidence_contract, self.evidence_contract_sha

        def validate(states):
            contract = copy.deepcopy(original_contract)
            contract["artifacts"]["symbol-state"] = HARNESS.artifact_contract_entry(
                states, "evidence/symbol-state.jsonl"
            )
            contract = HARNESS.seal_evidence_contract({
                key: value for key, value in contract.items()
                if key != "evidence_contract_sha256"
            })
            self.evidence_contract, self.evidence_contract_sha = (
                contract, contract["evidence_contract_sha256"]
            )
            try:
                return self.errors(states, self.edge_states())
            finally:
                self.evidence_contract, self.evidence_contract_sha = original_contract, original_sha

        for operation in ("extra", "missing"):
            states = self.states()
            caller = states[0]["caller_contract"]
            if operation == "extra":
                caller["unexpected"] = True
            else:
                caller.pop("edge_ids")
            self.assertTrue(any("Caller-Contract Schemafelder" in error for error in validate(states)), operation)

        states = self.states()
        incoming_state = next(
            row for row in states if row["caller_contract"]["kind"] == "incoming-edges"
        )
        incoming_id = incoming_state["caller_contract"]["edge_ids"][0]
        incoming_state["caller_contract"]["edge_ids"] = [incoming_id, incoming_id]
        self.assertTrue(any("Caller-edge_ids" in error and "doppelt" in error for error in validate(states)))

        for operation in ("extra", "missing", "fabricated"):
            states = self.states()
            state = next(row for row in states if row["disposition"] == "non-runtime")
            contract = state["non_runtime_contract"]
            if operation == "extra":
                contract["unexpected"] = True
            elif operation == "missing":
                contract.pop("reason")
            else:
                contract["kind"] = "fabricated-contract"
            errors = validate(states)
            self.assertTrue(any("Non-Runtime-Vertrag" in error for error in errors), operation)

    def test_resealed_non_runtime_types_and_feature_id_matrix_rejected(self) -> None:
        original_contract, original_sha = self.evidence_contract, self.evidence_contract_sha

        def validate(states):
            contract = copy.deepcopy(original_contract)
            contract["artifacts"]["symbol-state"] = HARNESS.artifact_contract_entry(
                states, "evidence/symbol-state.jsonl"
            )
            contract = HARNESS.seal_evidence_contract({
                key: value for key, value in contract.items()
                if key != "evidence_contract_sha256"
            })
            self.evidence_contract, self.evidence_contract_sha = (
                contract, contract["evidence_contract_sha256"]
            )
            try:
                return self.errors(states, self.edge_states())
            finally:
                self.evidence_contract, self.evidence_contract_sha = original_contract, original_sha

        for field, values in (
            ("reason", ([], {}, "", " ")),
            ("evidence_id", ([], {}, "", " ")),
        ):
            for value in values:
                states = self.states()
                state = next(row for row in states if row["disposition"] == "non-runtime")
                state["non_runtime_contract"][field] = value
                errors = validate(states)
                self.assertTrue(
                    any(f"Non-Runtime-Vertrag {field}" in error for error in errors),
                    f"{field}={value!r}",
                )

        for feature_ids in (
            [["FEAT-CONTRACT"]], [{"id": "FEAT-CONTRACT"}],
            ["FEAT-CONTRACT", "FEAT-CONTRACT"], [""], [" "],
        ):
            states = self.states()
            states[0]["feature_ids"] = feature_ids
            errors = validate(states)
            self.assertTrue(any("feature_ids" in error for error in errors), repr(feature_ids))

    def test_resealed_discriminator_and_unknown_reason_type_matrix_rejected(self) -> None:
        original_contract, original_sha = self.evidence_contract, self.evidence_contract_sha

        def validate(states, edges=None):
            edges = edges or self.edge_states()
            contract = copy.deepcopy(original_contract)
            contract["artifacts"]["symbol-state"] = HARNESS.artifact_contract_entry(
                states, "evidence/symbol-state.jsonl"
            )
            contract["artifacts"]["edge-state"] = HARNESS.artifact_contract_entry(
                edges, "evidence/edge-state.jsonl"
            )
            contract = HARNESS.seal_evidence_contract({
                key: value for key, value in contract.items()
                if key != "evidence_contract_sha256"
            })
            self.evidence_contract, self.evidence_contract_sha = (
                contract, contract["evidence_contract_sha256"]
            )
            try:
                return self.errors(states, edges)
            finally:
                self.evidence_contract, self.evidence_contract_sha = original_contract, original_sha

        for value in ([], {}, "", " "):
            mutations = (
                ("caller kind", lambda rows: rows[0]["caller_contract"].__setitem__("kind", value)),
                ("contract status", lambda rows: rows[0]["contracts"][HARNESS.CONTRACT_KEYS[0]].__setitem__("status", value)),
                ("non-runtime kind", lambda rows: next(row for row in rows if row["disposition"] == "non-runtime")["non_runtime_contract"].__setitem__("kind", value)),
                ("role", lambda rows: rows[0].__setitem__("role", value)),
                ("symbol disposition", lambda rows: rows[0].__setitem__("disposition", value)),
            )
            for label, mutate in mutations:
                states = self.states()
                mutate(states)
                errors = validate(states)
                self.assertTrue(
                    any(
                        "ungueltig" in error
                        or (label == "caller kind" and "Caller-/Frameworkvertrag" in error)
                        for error in errors
                    ),
                    label,
                )

            edges = self.edge_states()
            edges[0]["disposition"] = value
            self.assertTrue(any("disposition ungueltig" in error for error in validate(self.states(), edges)))

        for value in ([], {}, "", " "):
            states = self.states()
            state = next(row for row in states if row["disposition"] == "non-runtime")
            state["disposition"] = "unknown"
            state.pop("non_runtime_contract")
            state["unknown_reason"] = value
            self.assertTrue(any("UNKNOWN" in error for error in validate(states)), repr(value))

            edges = self.edge_states()
            edges[0]["disposition"] = "unknown"
            edges[0]["unknown_reason"] = value
            self.assertTrue(any("UNKNOWN" in error for error in validate(self.states(), edges)), repr(value))

    def test_incoming_edge_must_target_symbol(self) -> None:
        states = self.states()
        target = states[0]
        wrong = next(edge for edge in self.edges if edge.get("target_symbol_id") != target["symbol_id"])
        target["caller_contract"] = {
            "kind": "incoming-edges", "edge_ids": [wrong["edge_id"]],
            "evidence_ids": [self.symbol_evidence_id(target["symbol_id"])],
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
            self.repo, commit, self.RUN, self.SNAPSHOT,
            tooling_commit=self.TOOLING, signed_at=self.FROZEN,
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
            "kind": "entrypoint", "edge_ids": [],
            "evidence_ids": [self.symbol_evidence_id(target["symbol_id"])],
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
            "kind": "entrypoint", "edge_ids": [],
            "evidence_ids": [self.symbol_evidence_id(target["symbol_id"])],
        }
        self.assertTrue(any("ohne kanonischen Trigger" in error for error in self.errors(states, self.edge_states())))
        trigger_core = {
            "source_kind": "entrypoint",
            "path": target["path"], "line": target["line_start"], "column": 0,
            "detail": target["qualified_name"],
            "source_blob_sha256": target["source_blob_sha256"], "run_id": self.RUN,
            "audited_commit": self.commit, "tooling_commit": self.TOOLING,
            "snapshot_id": self.SNAPSHOT, "signed_at": self.SIGNED,
        }
        trigger_core["source_id"] = HARNESS._trigger_source_id(
            trigger_core["source_kind"], trigger_core["path"], trigger_core["line"],
            trigger_core["column"], trigger_core["detail"],
        )
        trigger = HARNESS.seal_record(trigger_core)
        self.trigger_records = [trigger]
        self.manifests["trigger-catalog"] = HARNESS.make_artifact_manifest(
            "trigger-catalog", self.trigger_records, run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        audit = copy.deepcopy(self.audit_contract)
        audit["artifacts"]["trigger-universe"] = HARNESS.artifact_contract_entry(
            self.trigger_records, "evidence/triggers.jsonl"
        )
        self.audit_contract = HARNESS.seal_audit_contract({
            key: value for key, value in audit.items() if key != "contract_sha256"
        })
        self.contract_sha = self.audit_contract["contract_sha256"]
        evidence = copy.deepcopy(self.evidence_contract)
        evidence["audit_contract_sha256"] = self.contract_sha
        evidence["artifacts"]["symbol-state"] = HARNESS.artifact_contract_entry(
            states, "evidence/symbol-state.jsonl"
        )
        self.evidence_contract = HARNESS.seal_evidence_contract({
            key: value for key, value in evidence.items()
            if key != "evidence_contract_sha256"
        })
        self.evidence_contract_sha = self.evidence_contract["evidence_contract_sha256"]
        self.assertEqual([], self.errors(states, self.edge_states()))

    def test_powershell_calls_and_batch_call_source_are_canonical(self) -> None:
        (self.repo / "ops.ps1").write_text(
            "function B { if ($true) { Write-Output ok } }\n"
            "function A { $(B) }\nA\n",
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
            self.repo, commit, self.RUN, self.SNAPSHOT,
            tooling_commit=self.TOOLING, signed_at=self.FROZEN,
        )
        by_name = {row["qualified_name"]: row for row in symbols if row["path"] in {"ops.ps1", "launch.cmd"}}
        ps_edge = next(
            row for row in edges
            if row["edge_kind"] == "powershell-call"
            and row["target_symbol_id"] == by_name["B"]["symbol_id"]
        )
        self.assertEqual(by_name["A"]["symbol_id"], ps_edge["source_symbol_id"])
        self.assertEqual(by_name["B"]["symbol_id"], ps_edge["target_symbol_id"])
        batch_edge = next(row for row in edges if row["edge_kind"] == "batch-call")
        self.assertEqual(by_name["one"]["symbol_id"], batch_edge["source_symbol_id"])
        self.assertEqual(by_name["two"]["symbol_id"], batch_edge["target_symbol_id"])

    def test_invalid_structured_inputs_and_missing_batch_label_parse_stop(self) -> None:
        cases = (
            ("<ui>", ".ui", "broken.ui"),
            ("CREATE BANANA nope;", ".sql", "broken.sql"),
        )
        for text, suffix, path in cases:
            with self.subTest(path=path), self.assertRaisesRegex(HARNESS.ContractError, "parser_error"):
                HARNESS._parse_structured(text, suffix, path)
        with self.assertRaisesRegex(HARNESS.ContractError, "parser_error"):
            HARNESS._parse_batch_units("@echo off\ncall :missing\n", "broken.cmd")
        with self.assertRaisesRegex(HARNESS.ContractError, "parser_error"):
            HARNESS._parse_powershell("function Broken { if () { } }", "broken.ps1")
        HARNESS._parse_structured(
            "-- SQLite migration\n"
            "CREATE TABLE project(id INTEGER PRIMARY KEY, name TEXT NOT NULL);\n"
            "CREATE INDEX ix_project_name ON project(name);\n"
            "ALTER TABLE project ADD COLUMN active INTEGER NOT NULL DEFAULT 1;\n",
            ".sql", "migration.sql",
        )

    def test_id_only_evidence_future_state_and_contract_substitution_rejected(self) -> None:
        records = copy.deepcopy(self.evidence_records)
        records[0] = HARNESS.seal_record({
            "evidence_id": records[0]["evidence_id"], "run_id": self.RUN,
            "audited_commit": self.commit, "tooling_commit": self.TOOLING,
            "snapshot_id": self.SNAPSHOT, "signed_at": self.SIGNED,
        })
        manifest = HARNESS.make_artifact_manifest(
            "symbol-evidence", records, run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        old_records, old_manifest = self.evidence_records, self.manifests["symbol-evidence"]
        self.evidence_records, self.manifests["symbol-evidence"] = records, manifest
        try:
            errors = self.errors(self.states(), self.edge_states())
        finally:
            self.evidence_records, self.manifests["symbol-evidence"] = old_records, old_manifest
        self.assertTrue(any("evidence_kind" in error or "proof_ref" in error for error in errors))
        states = self.states()
        states[0]["signed_at"] = "2100-01-01T00:00:00+00:00"
        self.assertTrue(any("Zeitgrenze" in error for error in self.errors(states, self.edge_states())))
        substituted = copy.deepcopy(self.audit_contract)
        substituted["artifacts"]["symbol-catalog"]["ref"] = "evidence/substitute.jsonl"
        substituted = HARNESS.seal_audit_contract({
            key: value for key, value in substituted.items() if key != "contract_sha256"
        })
        errors = HARNESS.validate_audit_contract(
            substituted, self.contract_sha, plan_id=self.PLAN, run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        self.assertTrue(any("externe Contract-SHA" in error for error in errors))

    def test_cli_requires_externally_pinned_contracts(self) -> None:
        files = {
            "symbols": self.symbols, "edges": self.edges,
            "symbol-states": self.states(), "edge-states": self.edge_states(),
            "features": self.feature_records, "runtime": self.runtime_records,
            "reviewers": self.reviewer_records, "evidence": self.evidence_records,
            "triggers": self.trigger_records,
        }
        paths = {name: self.repo / f"{name}.jsonl" for name in files}
        for name, rows in files.items():
            HARNESS._write_jsonl(paths[name], rows)
        manifest_names = {
            "feature": "feature-catalog", "runtime": "runtime-evidence",
            "reviewer": "reviewer-roster", "evidence": "symbol-evidence",
            "trigger": "trigger-catalog",
        }
        manifest_paths = {}
        for name, key in manifest_names.items():
            path = self.repo / f"{name}-manifest.json"
            path.write_text(HARNESS.json.dumps(self.manifests[key]), encoding="utf-8")
            manifest_paths[name] = path
        audit_path, evidence_contract_path = self.repo / "audit-contract.json", self.repo / "evidence-contract.json"
        audit_path.write_text(HARNESS.json.dumps(self.audit_contract), encoding="utf-8")
        evidence_contract_path.write_text(HARNESS.json.dumps(self.evidence_contract), encoding="utf-8")
        args = [
            "validate", "--root", str(self.repo), "--audited-commit", self.commit,
            "--run-id", self.RUN, "--snapshot-id", self.SNAPSHOT,
            "--symbols", str(paths["symbols"]), "--edges", str(paths["edges"]),
            "--symbol-states", str(paths["symbol-states"]), "--edge-states", str(paths["edge-states"]),
            "--feature-universe", str(paths["features"]), "--runtime-universe", str(paths["runtime"]),
            "--reviewer-roster", str(paths["reviewers"]), "--evidence-universe", str(paths["evidence"]),
            "--trigger-universe", str(paths["triggers"]), "--feature-manifest", str(manifest_paths["feature"]),
            "--runtime-manifest", str(manifest_paths["runtime"]), "--reviewer-manifest", str(manifest_paths["reviewer"]),
            "--evidence-manifest", str(manifest_paths["evidence"]), "--trigger-manifest", str(manifest_paths["trigger"]),
            "--tooling-commit", self.TOOLING, "--audit-contract", str(audit_path),
            "--expected-audit-contract-sha256", self.contract_sha,
            "--evidence-contract", str(evidence_contract_path),
            "--expected-evidence-contract-sha256", self.evidence_contract_sha,
            "--evidence-root", str(self.repo),
        ]
        self.assertEqual(0, HARNESS.main(args))
        missing_external_pin = args.copy()
        index = missing_external_pin.index("--expected-evidence-contract-sha256")
        del missing_external_pin[index:index + 2]
        with self.assertRaises(SystemExit):
            HARNESS.main(missing_external_pin)


if __name__ == "__main__":
    unittest.main()
