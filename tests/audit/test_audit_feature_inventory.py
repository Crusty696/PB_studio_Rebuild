from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
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
    TOOLING = "TOOLING-CONTRACT"
    PLAN = "PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15"
    FROZEN = "2026-08-15T00:00:00+00:00"
    SIGNED = "2026-08-15T12:00:00+00:00"
    EXPIRES = "2099-08-16T00:00:00+00:00"

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
            self.repo, self.commit, self.RUN, self.SNAPSHOT,
            tooling_commit=self.TOOLING, signed_at=self.FROZEN,
        )
        self.assertTrue(self.requirements)
        self.assertTrue(self.triggers)
        source_ids = [row["source_id"] for row in self.requirements + self.triggers]
        catalog_core = {
            "feature_id": "FEAT-EXPORT", "path_id": "primary", "name": "Export",
            "source_ids": source_ids, "run_id": self.RUN, "audited_commit": self.commit,
            "tooling_commit": self.TOOLING, "snapshot_id": self.SNAPSHOT,
            "signed_at": self.SIGNED,
        }
        catalog_core["catalog_id"] = "sha256:" + hashlib.sha256(
            json.dumps(catalog_core, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.feature_catalog = [HARNESS.seal_record(catalog_core)]
        self.reviewers = [HARNESS.seal_record({
            "reviewer_id": "REV-A", "run_id": self.RUN,
            "audited_commit": self.commit, "tooling_commit": self.TOOLING,
            "snapshot_id": self.SNAPSHOT,
            "signed_at": self.SIGNED,
        })]
        self.evidence = []
        for source in self.requirements + self.triggers:
            core = {
                "source_id": source["source_id"], "feature_id": "FEAT-EXPORT",
                "path_id": "primary", "reviewer_id": "REV-A",
                "path": source["path"],
                "source_blob_sha256": source["source_blob_sha256"],
                "evidence_kind": "source-review", "proof_ref": f"proof/{source['source_id']}.json",
                "signed_at": self.SIGNED, "run_id": self.RUN,
                "audited_commit": self.commit, "tooling_commit": self.TOOLING,
                "snapshot_id": self.SNAPSHOT,
            }
            core["evidence_id"] = "sha256:" + hashlib.sha256(
                json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            self.evidence.append(HARNESS.seal_record(core))
        self.feature_manifest = HARNESS.make_artifact_manifest(
            "feature-catalog", self.feature_catalog, run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        self.reviewer_manifest = HARNESS.make_artifact_manifest(
            "reviewer-roster", self.reviewers, run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        proof_artifacts = {}
        for row in self.evidence:
            proof = {field: row[field] for field in (
                "evidence_id", "evidence_kind", "source_id", "feature_id", "path_id",
                "reviewer_id", "path", "source_blob_sha256",
            )}
            proof["schema_version"] = 1
            data = HARNESS._canonical(proof)
            target = self.repo / row["proof_ref"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            proof_artifacts[f"feature-proof:{row['evidence_id']}"] = HARNESS.file_contract_entry(
                data, row["proof_ref"]
            )
            row["proof_sha256"] = hashlib.sha256(data).hexdigest()
            row.update(HARNESS.seal_record(row))
        self.evidence_manifest = HARNESS.make_artifact_manifest(
            "feature-state-evidence", self.evidence, run_id=self.RUN,
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
            "requirements-universe": HARNESS.artifact_contract_entry(
                self.requirements, "evidence/requirements.jsonl"
            ),
            "trigger-universe": HARNESS.artifact_contract_entry(
                self.triggers, "evidence/triggers.jsonl"
            ),
            "feature-catalog": HARNESS.artifact_contract_entry(
                self.feature_catalog, "evidence/features.jsonl"
            ),
        })
        core = {
            "schema_version": 1, "plan_id": self.PLAN, "run_id": self.RUN,
            "audited_commit": self.commit, "tooling_commit": self.TOOLING,
            "snapshot_id": self.SNAPSHOT, "frozen_at": self.FROZEN,
            "expires_at": self.EXPIRES, "artifacts": audit_artifacts,
        }
        self.audit_contract = HARNESS.seal_audit_contract(core)
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
                "feature-state": HARNESS.artifact_contract_entry(
                    self.dispositions(), "evidence/feature-state.jsonl"
                ),
                "feature-state-evidence": HARNESS.artifact_contract_entry(
                    self.evidence, "evidence/feature-state-evidence.jsonl"
                ),
                "reviewer-roster": HARNESS.artifact_contract_entry(
                    self.reviewers, "evidence/reviewers.jsonl"
                ),
                **proof_artifacts,
            },
        }
        self.evidence_contract = HARNESS.seal_evidence_contract(evidence_core)
        self.evidence_contract_sha = self.evidence_contract["evidence_contract_sha256"]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def dispositions(self) -> list[dict]:
        rows = []
        evidence = {row["source_id"]: row for row in self.evidence}
        for kind, universe in (("requirement", self.requirements), ("trigger", self.triggers)):
            digest = HARNESS.universe_digest(universe)
            for item in universe:
                rows.append({
                    "universe": kind,
                    "source_id": item["source_id"],
                    "run_id": self.RUN,
                    "audited_commit": self.commit,
                    "tooling_commit": self.TOOLING,
                    "snapshot_id": self.SNAPSHOT,
                    "universe_sha256": digest,
                    "disposition": "feature",
                    "feature_id": "FEAT-EXPORT",
                    "path_id": "primary",
                    "evidence_id": evidence[item["source_id"]]["evidence_id"],
                    "reviewer_id": "REV-A", "signed_at": self.SIGNED,
                    "source_blob_sha256": item["source_blob_sha256"],
                })
        return rows

    def errors(self, rows: list[dict]) -> list[str]:
        return HARNESS.validate_exact_set(
            self.requirements, self.triggers, rows, run_id=self.RUN,
            audited_commit=self.commit, snapshot_id=self.SNAPSHOT,
            tooling_commit=self.TOOLING, feature_catalog=self.feature_catalog,
            feature_catalog_manifest=self.feature_manifest,
            evidence_records=self.evidence, evidence_manifest=self.evidence_manifest,
            reviewer_records=self.reviewers, reviewer_manifest=self.reviewer_manifest,
            audit_contract=self.audit_contract,
            expected_contract_sha256=self.contract_sha,
            evidence_contract=self.evidence_contract,
            expected_evidence_contract_sha256=self.evidence_contract_sha,
            evidence_root=self.repo,
        )

    def test_positive_minimal(self) -> None:
        before = (self.requirements, self.triggers)
        (self.repo / "app.py").write_text("raise RuntimeError('dirty')\n", encoding="utf-8")
        after = HARNESS.enumerate_universes(
            self.repo, self.commit, self.RUN, self.SNAPSHOT,
            tooling_commit=self.TOOLING, signed_at=self.FROZEN,
        )
        self.assertEqual(before, after, "Enumerator darf Dirty-Workingtree nicht lesen")
        self.assertEqual([], self.errors(self.dispositions()))

    def test_global_contract_exact_sets_required(self) -> None:
        self.assertTrue(HARNESS.validate_audit_contract(
            [], self.contract_sha, plan_id=self.PLAN, run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        ))
        for key in HARNESS.AUDIT_ARTIFACT_KEYS:
            contract = copy.deepcopy(self.audit_contract)
            del contract["artifacts"][key]
            contract = HARNESS.seal_audit_contract({
                name: value for name, value in contract.items() if name != "contract_sha256"
            })
            errors = HARNESS.validate_audit_contract(
                contract, contract["contract_sha256"], plan_id=self.PLAN,
                run_id=self.RUN, audited_commit=self.commit, tooling_commit=self.TOOLING,
                snapshot_id=self.SNAPSHOT,
            )
            self.assertTrue(any("Exact-Set" in error for error in errors), key)
        for foreign_key in (
            "foreign-static", "reviewer-enrollment-receipt:bad:session",
        ):
            contract = copy.deepcopy(self.evidence_contract)
            contract["artifacts"][foreign_key] = HARNESS.file_contract_entry(
                b"{}", "evidence/foreign.json"
            )
            contract = HARNESS.seal_evidence_contract({
                name: value for name, value in contract.items()
                if name != "evidence_contract_sha256"
            })
            errors = HARNESS.validate_evidence_contract(
                contract, contract["evidence_contract_sha256"], self.audit_contract,
                plan_id=self.PLAN, run_id=self.RUN, audited_commit=self.commit,
                tooling_commit=self.TOOLING, snapshot_id=self.SNAPSHOT,
            )
            self.assertTrue(any("Exact-Set" in error for error in errors), foreign_key)

    def test_resealed_feature_disposition_type_matrix_rejected(self) -> None:
        base_contract = copy.deepcopy(self.evidence_contract)
        for value in ([], {}, [["feature"]], [None], True, 1, None, "", " ", "foreign"):
            rows = self.dispositions()
            rows[0]["disposition"] = value
            contract = copy.deepcopy(base_contract)
            contract["artifacts"]["feature-state"] = HARNESS.artifact_contract_entry(
                rows, "evidence/feature-state.jsonl"
            )
            contract = HARNESS.seal_evidence_contract({
                key: item for key, item in contract.items()
                if key != "evidence_contract_sha256"
            })
            errors = HARNESS.validate_exact_set(
                self.requirements, self.triggers, rows, run_id=self.RUN,
                audited_commit=self.commit, snapshot_id=self.SNAPSHOT,
                tooling_commit=self.TOOLING, feature_catalog=self.feature_catalog,
                feature_catalog_manifest=self.feature_manifest,
                evidence_records=self.evidence, evidence_manifest=self.evidence_manifest,
                reviewer_records=self.reviewers, reviewer_manifest=self.reviewer_manifest,
                audit_contract=self.audit_contract,
                expected_contract_sha256=self.contract_sha,
                evidence_contract=contract,
                expected_evidence_contract_sha256=contract["evidence_contract_sha256"],
                evidence_root=self.repo,
            )
            self.assertTrue(
                any("disposition ungueltig" in error for error in errors), repr(value)
            )

    def test_proof_binding_negative_repros(self) -> None:
        def validate(rows, contract=None):
            contract = contract or self.evidence_contract
            return HARNESS.validate_exact_set(
                self.requirements, self.triggers, self.dispositions(), run_id=self.RUN,
                audited_commit=self.commit, snapshot_id=self.SNAPSHOT,
                tooling_commit=self.TOOLING, feature_catalog=self.feature_catalog,
                feature_catalog_manifest=self.feature_manifest, evidence_records=rows,
                evidence_manifest=HARNESS.make_artifact_manifest(
                    "feature-state-evidence", rows, run_id=self.RUN,
                    audited_commit=self.commit, tooling_commit=self.TOOLING,
                    snapshot_id=self.SNAPSHOT,
                ), reviewer_records=self.reviewers, reviewer_manifest=self.reviewer_manifest,
                audit_contract=self.audit_contract, expected_contract_sha256=self.contract_sha,
                evidence_contract=contract,
                expected_evidence_contract_sha256=contract["evidence_contract_sha256"],
                evidence_root=self.repo,
            )

        for field, value, token in (
            ("evidence_kind", " ", "evidence_kind"),
            ("proof_ref", ".", "proof_ref"),
            ("proof_ref", "proof/missing.json", "Proof-Datei fehlt"),
            ("proof_sha256", "e" * 64, "proof_sha256"),
        ):
            rows = copy.deepcopy(self.evidence)
            rows[0][field] = value
            rows[0] = HARNESS.seal_record(rows[0])
            self.assertTrue(any(token in error for error in validate(rows)), value)

        rows = copy.deepcopy(self.evidence)
        (self.repo / "proof" / "directory").mkdir()
        rows[0]["proof_ref"] = "proof/directory"
        rows[0] = HARNESS.seal_record(rows[0])
        self.assertTrue(any("keine regulaere Datei" in error for error in validate(rows)))

        row = self.evidence[0]
        key = f"feature-proof:{row['evidence_id']}"
        contract = copy.deepcopy(self.evidence_contract)
        contract["artifacts"][key]["bytes"] += 1
        contract = HARNESS.seal_evidence_contract({
            name: value for name, value in contract.items()
            if name != "evidence_contract_sha256"
        })
        self.assertTrue(any("Proof bytes" in error for error in validate(self.evidence, contract)))

        target = self.repo / row["proof_ref"]
        original = target.read_bytes()
        target.write_bytes(b"{}")
        self.assertTrue(any("Proof SHA" in error for error in validate(self.evidence)))
        foreign = HARNESS.json.loads(original.decode("utf-8"))
        foreign["source_id"] = "FOREIGN-SOURCE"
        data = HARNESS._canonical(foreign)
        target.write_bytes(data)
        contract = copy.deepcopy(self.evidence_contract)
        contract["artifacts"][key] = HARNESS.file_contract_entry(data, row["proof_ref"])
        contract = HARNESS.seal_evidence_contract({
            name: value for name, value in contract.items()
            if name != "evidence_contract_sha256"
        })
        self.assertTrue(any("Proof-Semantik/FK" in error for error in validate(self.evidence, contract)))
        target.write_bytes(original)

    def test_windows_unsafe_feature_proof_refs_rejected_and_nested_allowed(self) -> None:
        original_rows, original_manifest = self.evidence, self.evidence_manifest
        original_contract, original_sha = self.evidence_contract, self.evidence_contract_sha
        source = self.evidence[0]
        original_proof = HARNESS.json.loads(
            (self.repo / source["proof_ref"]).read_text(encoding="utf-8")
        )

        def errors_for(ref: str) -> list[str]:
            rows = copy.deepcopy(original_rows)
            rows[0]["proof_ref"] = ref
            rows[0]["evidence_id"] = "sha256:" + hashlib.sha256(
                HARNESS._canonical({
                    key: value for key, value in rows[0].items()
                    if key not in {"evidence_id", "proof_sha256", "record_sha256"}
                })
            ).hexdigest()
            proof = copy.deepcopy(original_proof)
            proof["evidence_id"] = rows[0]["evidence_id"]
            proof_data = HARNESS._canonical(proof)
            rows[0]["proof_sha256"] = hashlib.sha256(proof_data).hexdigest()
            rows[0] = HARNESS.seal_record(rows[0])
            contract = copy.deepcopy(original_contract)
            contract["artifacts"]["feature-state-evidence"] = (
                HARNESS.artifact_contract_entry(
                    rows, "evidence/feature-state-evidence.jsonl"
                )
            )
            contract["artifacts"][f"feature-proof:{rows[0]['evidence_id']}"] = (
                HARNESS.file_contract_entry(proof_data, ref)
            )
            for key in list(contract["artifacts"]):
                if key.startswith("feature-proof:") and key != (
                    f"feature-proof:{rows[0]['evidence_id']}"
                ) and key.endswith(source["evidence_id"]):
                    del contract["artifacts"][key]
            self.evidence = rows
            contract["artifacts"]["feature-state"] = HARNESS.artifact_contract_entry(
                self.dispositions(), "evidence/feature-state.jsonl"
            )
            contract = HARNESS.seal_evidence_contract({
                key: value for key, value in contract.items()
                if key != "evidence_contract_sha256"
            })
            self.evidence_manifest = HARNESS.make_artifact_manifest(
                "feature-state-evidence", rows, run_id=self.RUN,
                audited_commit=self.commit, tooling_commit=self.TOOLING,
                snapshot_id=self.SNAPSHOT,
            )
            self.evidence_contract = contract
            self.evidence_contract_sha = contract["evidence_contract_sha256"]
            try:
                return self.errors(self.dispositions())
            finally:
                self.evidence, self.evidence_manifest = original_rows, original_manifest
                self.evidence_contract, self.evidence_contract_sha = original_contract, original_sha

        nested_ref = "proof/deep/nested/feature-review.json"
        nested_target = self.repo / nested_ref
        nested_target.parent.mkdir(parents=True, exist_ok=True)
        nested_rows = copy.deepcopy(original_rows)
        nested_rows[0]["proof_ref"] = nested_ref
        nested_rows[0]["evidence_id"] = "sha256:" + hashlib.sha256(
            HARNESS._canonical({
                key: value for key, value in nested_rows[0].items()
                if key not in {"evidence_id", "proof_sha256", "record_sha256"}
            })
        ).hexdigest()
        nested_proof = copy.deepcopy(original_proof)
        nested_proof["evidence_id"] = nested_rows[0]["evidence_id"]
        nested_target.write_bytes(HARNESS._canonical(nested_proof))
        self.assertEqual([], errors_for(nested_ref))
        reserved_names = [
            "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
            *(f"COM{number}" for number in range(1, 10)),
            *(f"LPT{number}" for number in range(1, 10)),
            "COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³",
        ]
        for ref in (
            "proof/deep/name:ads.json", "proof/deep/name./review.json",
            "proof/deep/name /review.json", "proof/CON/review.json",
            "proof/deep/com1.txt/review.json", "proof/LPT9/review.json",
            "proof/deep/CON .txt/review.json",
            "proof/deep/bad*/review.json", "proof/deep/bad?/review.json",
            "proof/deep/bad\"/review.json", "proof/deep/bad</review.json",
            "proof/deep/bad>/review.json", "proof/deep/bad|/review.json",
            r"proof/deep/bad\name/review.json",
            *(f"proof/deep/control-{chr(code)}/review.json" for code in range(32)),
            *(f"proof/deep/{name}.txt/review.json" for name in reserved_names),
        ):
            self.assertTrue(any("proof_ref ungueltig" in error for error in errors_for(ref)), ref)

    def test_feature_source_grouping_and_proof_key_closure_rejected(self) -> None:
        original_catalog, original_manifest = self.feature_catalog, self.feature_manifest
        for source_ids, token in (
            ([], "source_ids fehlt/leer/doppelt"),
            ([original_catalog[0]["source_ids"][0]] * 2, "source_ids fehlt/leer/doppelt"),
            (["FOREIGN-SOURCE"], "fremde source_ids"),
            (original_catalog[0]["source_ids"][1:], "unclaimed"),
        ):
            catalog = copy.deepcopy(original_catalog)
            catalog[0]["source_ids"] = source_ids
            catalog[0] = HARNESS.seal_record(catalog[0])
            self.feature_catalog = catalog
            self.feature_manifest = HARNESS.make_artifact_manifest(
                "feature-catalog", catalog, run_id=self.RUN,
                audited_commit=self.commit, tooling_commit=self.TOOLING,
                snapshot_id=self.SNAPSHOT,
            )
            try:
                errors = self.errors(self.dispositions())
            finally:
                self.feature_catalog, self.feature_manifest = original_catalog, original_manifest
            self.assertTrue(any(token in error for error in errors), token)

        catalog = copy.deepcopy(original_catalog)
        overlap = copy.deepcopy(catalog[0])
        overlap["feature_id"], overlap["path_id"] = "FEAT-OVERLAP", "secondary"
        overlap["source_ids"] = [catalog[0]["source_ids"][0]]
        overlap["catalog_id"] = "sha256:" + hashlib.sha256(
            json.dumps(
                {key: value for key, value in overlap.items() if key not in {"catalog_id", "record_sha256"}},
                sort_keys=True, separators=(",", ":"),
            ).encode()
        ).hexdigest()
        catalog.append(HARNESS.seal_record(overlap))
        self.feature_catalog = catalog
        self.feature_manifest = HARNESS.make_artifact_manifest(
            "feature-catalog", catalog, run_id=self.RUN, audited_commit=self.commit,
            tooling_commit=self.TOOLING, snapshot_id=self.SNAPSHOT,
        )
        try:
            errors = self.errors(self.dispositions())
        finally:
            self.feature_catalog, self.feature_manifest = original_catalog, original_manifest
        self.assertTrue(any("ueberlappt" in error for error in errors))
        self.assertTrue(any("unused" in error for error in errors))

        contract = copy.deepcopy(self.evidence_contract)
        descriptor = next(
            value for key, value in contract["artifacts"].items()
            if key.startswith("feature-proof:")
        )
        contract["artifacts"]["feature-proof:FOREIGN"] = copy.deepcopy(descriptor)
        contract = HARNESS.seal_evidence_contract({
            key: value for key, value in contract.items()
            if key != "evidence_contract_sha256"
        })
        old_contract, old_sha = self.evidence_contract, self.evidence_contract_sha
        self.evidence_contract, self.evidence_contract_sha = contract, contract["evidence_contract_sha256"]
        try:
            errors = self.errors(self.dispositions())
        finally:
            self.evidence_contract, self.evidence_contract_sha = old_contract, old_sha
        self.assertTrue(any("Feature-Proof-Key-Exact-Set" in error for error in errors))

    def test_resealed_feature_evidence_closure_and_exact_fields_rejected(self) -> None:
        def bind_outputs(rows, evidence=None, contract=None):
            evidence = evidence or self.evidence
            contract = copy.deepcopy(contract or self.evidence_contract)
            contract["artifacts"]["feature-state"] = HARNESS.artifact_contract_entry(
                rows, "evidence/feature-state.jsonl"
            )
            contract["artifacts"]["feature-state-evidence"] = HARNESS.artifact_contract_entry(
                evidence, "evidence/feature-state-evidence.jsonl"
            )
            return HARNESS.seal_evidence_contract({
                key: value for key, value in contract.items()
                if key != "evidence_contract_sha256"
            })

        original_contract, original_sha = self.evidence_contract, self.evidence_contract_sha
        for operation in ("extra", "missing"):
            rows = self.dispositions()
            if operation == "extra":
                rows[0]["unexpected"] = True
            else:
                rows[0].pop("reviewer_id")
            contract = bind_outputs(rows)
            self.evidence_contract, self.evidence_contract_sha = contract, contract["evidence_contract_sha256"]
            try:
                errors = self.errors(rows)
            finally:
                self.evidence_contract, self.evidence_contract_sha = original_contract, original_sha
            self.assertTrue(any("Schemafelder nicht exakt" in error for error in errors), operation)

        for operation in ("extra", "missing"):
            catalog = copy.deepcopy(self.feature_catalog)
            core = {
                key: value for key, value in catalog[0].items()
                if key not in {"catalog_id", "record_sha256"}
            }
            if operation == "extra":
                core["unexpected"] = True
            else:
                core.pop("name")
            core["catalog_id"] = "sha256:" + hashlib.sha256(
                json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            catalog = [HARNESS.seal_record(core)]
            audit = copy.deepcopy(self.audit_contract)
            audit["artifacts"]["feature-catalog"] = HARNESS.artifact_contract_entry(
                catalog, "evidence/features.jsonl"
            )
            audit = HARNESS.seal_audit_contract({
                key: value for key, value in audit.items() if key != "contract_sha256"
            })
            evidence_contract = copy.deepcopy(original_contract)
            evidence_contract["audit_contract_sha256"] = audit["contract_sha256"]
            evidence_contract = HARNESS.seal_evidence_contract({
                key: value for key, value in evidence_contract.items()
                if key != "evidence_contract_sha256"
            })
            old_catalog, old_manifest = self.feature_catalog, self.feature_manifest
            old_audit, old_audit_sha = self.audit_contract, self.contract_sha
            self.feature_catalog = catalog
            self.feature_manifest = HARNESS.make_artifact_manifest(
                "feature-catalog", catalog, run_id=self.RUN, audited_commit=self.commit,
                tooling_commit=self.TOOLING, snapshot_id=self.SNAPSHOT,
            )
            self.audit_contract, self.contract_sha = audit, audit["contract_sha256"]
            self.evidence_contract = evidence_contract
            self.evidence_contract_sha = evidence_contract["evidence_contract_sha256"]
            try:
                errors = self.errors(self.dispositions())
            finally:
                self.feature_catalog, self.feature_manifest = old_catalog, old_manifest
                self.audit_contract, self.contract_sha = old_audit, old_audit_sha
                self.evidence_contract, self.evidence_contract_sha = original_contract, original_sha
            self.assertTrue(any("Featurekatalog: Schemafelder nicht exakt" in error for error in errors), operation)

        evidence = copy.deepcopy(self.evidence)
        core = {
            key: value for key, value in evidence[0].items()
            if key not in {"evidence_id", "record_sha256"}
        }
        core["proof_ref"] = "proof/orphan-feature.json"
        core["evidence_id"] = "sha256:" + hashlib.sha256(
            json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        orphan = HARNESS.seal_record(core)
        evidence.append(orphan)
        proof = {field: orphan[field] for field in (
            "evidence_id", "evidence_kind", "source_id", "feature_id", "path_id",
            "reviewer_id", "path", "source_blob_sha256",
        )}
        proof["schema_version"] = 1
        data = HARNESS._canonical(proof)
        (self.repo / orphan["proof_ref"]).write_bytes(data)
        rows = self.dispositions()
        contract = copy.deepcopy(original_contract)
        contract["artifacts"][f"feature-proof:{orphan['evidence_id']}"] = (
            HARNESS.file_contract_entry(data, orphan["proof_ref"])
        )
        contract = bind_outputs(rows, evidence, contract)
        old_evidence, old_manifest = self.evidence, self.evidence_manifest
        self.evidence = evidence
        self.evidence_manifest = HARNESS.make_artifact_manifest(
            "feature-state-evidence", evidence, run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        self.evidence_contract, self.evidence_contract_sha = contract, contract["evidence_contract_sha256"]
        try:
            errors = self.errors(rows)
        finally:
            self.evidence, self.evidence_manifest = old_evidence, old_manifest
            self.evidence_contract, self.evidence_contract_sha = original_contract, original_sha
        self.assertTrue(any("Feature-Evidence-Consumer-Closure" in error for error in errors))

        for operation in ("multi", "foreign"):
            rows = self.dispositions()
            rows[1]["evidence_id"] = (
                rows[0]["evidence_id"] if operation == "multi" else "EVIDENCE-FOREIGN"
            )
            contract = bind_outputs(rows)
            self.evidence_contract, self.evidence_contract_sha = contract, contract["evidence_contract_sha256"]
            try:
                errors = self.errors(rows)
            finally:
                self.evidence_contract, self.evidence_contract_sha = original_contract, original_sha
            self.assertTrue(any("Feature-Evidence-Consumer-Closure" in error for error in errors), operation)

    def test_missing_required_rejected(self) -> None:
        rows = self.dispositions()
        rows[0].pop("evidence_id")
        self.assertTrue(any("evidence_id fehlt" in error for error in self.errors(rows)))

        (self.repo / "bad.md").write_bytes(b"Pflicht: \xff\n")
        subprocess.run(["git", "add", "bad.md"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "non-utf8"], cwd=self.repo, check=True)
        bad_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=self.repo, text=True
        ).strip()
        with self.assertRaises(HARNESS.ContractError):
            HARNESS.enumerate_universes(
                self.repo, bad_commit, self.RUN, self.SNAPSHOT,
                tooling_commit=self.TOOLING, signed_at=self.FROZEN,
            )

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
            snapshot_id=self.SNAPSHOT, tooling_commit=self.TOOLING,
            feature_catalog=self.feature_catalog,
            feature_catalog_manifest=self.feature_manifest,
            evidence_records=self.evidence, evidence_manifest=self.evidence_manifest,
            reviewer_records=self.reviewers, reviewer_manifest=self.reviewer_manifest,
            audit_contract=self.audit_contract,
            expected_contract_sha256=self.contract_sha,
            evidence_contract=self.evidence_contract,
            expected_evidence_contract_sha256=self.evidence_contract_sha,
            evidence_root=self.repo,
        )
        self.assertTrue(any("leer" in error for error in errors))

    def test_relevant_non_python_surfaces_cannot_be_skipped(self) -> None:
        files = {
            "ops.ps1": "param([switch]$Force)\nfunction Invoke-Audit { Write-Output ok }\nInvoke-Audit\n",
            "launch.bat": "@echo off\ncall :run\n:run\necho ok\n",
            "schema.sql": (
                "-- representative SQLite migration\n"
                "CREATE TABLE audit(id INTEGER PRIMARY KEY);\n"
                "CREATE INDEX ix_audit_id ON audit(id);\n"
                "CREATE TRIGGER audit_insert AFTER INSERT ON audit BEGIN SELECT 1; END;\n"
            ),
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
            self.repo, commit, self.RUN, self.SNAPSHOT,
            tooling_commit=self.TOOLING, signed_at=self.FROZEN,
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
        requirements, _ = HARNESS.enumerate_universes(
            self.repo, commit, self.RUN, self.SNAPSHOT,
            tooling_commit=self.TOOLING, signed_at=self.FROZEN,
        )
        self.assertTrue(any(row["path"] == "latin.py" and "Über" in row["detail"] for row in requirements))

    def test_foreign_feature_and_truthy_evidence_rejected(self) -> None:
        rows = self.dispositions()
        rows[0]["feature_id"] = "FOREIGN-FEATURE"
        rows[0]["evidence_id"] = "truthy"
        errors = self.errors(rows)
        self.assertTrue(any("Featurekatalog" in error for error in errors))
        self.assertTrue(any("Evidence" in error for error in errors))

    def test_resealed_catalog_with_stale_content_id_is_rejected(self) -> None:
        catalog = copy.deepcopy(self.feature_catalog)
        catalog[0]["feature_id"] = "LAUNDERED"
        catalog[0] = HARNESS.seal_record(catalog[0])
        manifest = HARNESS.make_artifact_manifest(
            "feature-catalog", catalog, run_id=self.RUN, audited_commit=self.commit,
            tooling_commit=self.TOOLING, snapshot_id=self.SNAPSHOT,
        )
        _, errors = HARNESS.validate_artifact(
            catalog, manifest, "feature-catalog", "catalog_id", run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        self.assertTrue(any("nicht inhaltsadressiert" in error for error in errors))

    def test_invalid_json_is_parse_stop(self) -> None:
        (self.repo / "broken.json").write_text("{invalid", encoding="utf-8")
        subprocess.run(["git", "add", "broken.json"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "broken json"], cwd=self.repo, check=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        with self.assertRaisesRegex(HARNESS.ContractError, "parser_error"):
            HARNESS.enumerate_universes(
                self.repo, commit, self.RUN, self.SNAPSHOT,
                tooling_commit=self.TOOLING, signed_at=self.FROZEN,
            )

    def test_unbalanced_powershell_is_parse_stop(self) -> None:
        (self.repo / "broken.ps1").write_text("function Broken { if ($true) {\n", encoding="utf-8")
        subprocess.run(["git", "add", "broken.ps1"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "broken ps"], cwd=self.repo, check=True)
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=self.repo, text=True).strip()
        with self.assertRaisesRegex(HARNESS.ContractError, "parser_error"):
            HARNESS.enumerate_universes(
                self.repo, commit, self.RUN, self.SNAPSHOT,
                tooling_commit=self.TOOLING, signed_at=self.FROZEN,
            )

    def test_contract_pin_future_ttl_and_evidence_schema_rejected(self) -> None:
        evidence = copy.deepcopy(self.evidence)
        evidence[0].pop("proof_ref")
        evidence[0] = HARNESS.seal_record(evidence[0])
        manifest = HARNESS.make_artifact_manifest(
            "feature-state-evidence", evidence, run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        errors = HARNESS.validate_exact_set(
            self.requirements, self.triggers, self.dispositions(), run_id=self.RUN,
            audited_commit=self.commit, snapshot_id=self.SNAPSHOT,
            tooling_commit=self.TOOLING, feature_catalog=self.feature_catalog,
            feature_catalog_manifest=self.feature_manifest, evidence_records=evidence,
            evidence_manifest=manifest, reviewer_records=self.reviewers,
            reviewer_manifest=self.reviewer_manifest, audit_contract=self.audit_contract,
            expected_contract_sha256=self.contract_sha,
            evidence_contract=self.evidence_contract,
            expected_evidence_contract_sha256=self.evidence_contract_sha,
            evidence_root=self.repo,
        )
        self.assertTrue(any("proof_ref" in error for error in errors))
        future = self.dispositions()
        future[0]["signed_at"] = "2100-01-01T00:00:00+00:00"
        self.assertTrue(any("Zeitgrenze" in error for error in self.errors(future)))
        expired = copy.deepcopy(self.audit_contract)
        expired["frozen_at"] = "1999-01-01T00:00:00+00:00"
        expired["expires_at"] = "2000-01-01T00:00:00+00:00"
        expired = HARNESS.seal_audit_contract({
            key: value for key, value in expired.items() if key != "contract_sha256"
        })
        contract_errors = HARNESS.validate_audit_contract(
            expired, expired["contract_sha256"], plan_id=self.PLAN,
            run_id=self.RUN, audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        self.assertTrue(any("abgelaufen" in error for error in contract_errors))

    def test_simultaneous_records_manifest_and_contract_substitution_rejected(self) -> None:
        catalog = copy.deepcopy(self.feature_catalog)
        catalog[0]["name"] = "Substituted"
        catalog[0]["catalog_id"] = "sha256:" + hashlib.sha256(HARNESS._canonical(
            {key: value for key, value in catalog[0].items() if key not in {"catalog_id", "record_sha256"}}
        )).hexdigest()
        catalog[0] = HARNESS.seal_record(catalog[0])
        contract = copy.deepcopy(self.audit_contract)
        contract["artifacts"]["feature-catalog"] = HARNESS.artifact_contract_entry(
            catalog, "evidence/features.jsonl"
        )
        contract = HARNESS.seal_audit_contract({
            key: value for key, value in contract.items() if key != "contract_sha256"
        })
        errors = HARNESS.validate_audit_contract(
            contract, self.contract_sha, plan_id=self.PLAN, run_id=self.RUN,
            audited_commit=self.commit, tooling_commit=self.TOOLING,
            snapshot_id=self.SNAPSHOT,
        )
        self.assertTrue(any("externe Contract-SHA" in error for error in errors))

    def test_invalid_xml_and_sql_are_parse_stops(self) -> None:
        with self.assertRaisesRegex(HARNESS.ContractError, "parser_error"):
            HARNESS._parse_xml("<ui>", "broken.ui")
        with self.assertRaisesRegex(HARNESS.ContractError, "parser_error"):
            HARNESS._parse_sql("THIS IS NOT SQL;", "broken.sql")

    def test_missing_batch_label_is_parse_stop(self) -> None:
        with self.assertRaisesRegex(HARNESS.ContractError, "parser_error"):
            HARNESS._parse_batch("@echo off\ncall :missing\n", "broken.cmd")

    def test_powershell_comment_brace_does_not_break_parser(self) -> None:
        HARNESS._validate_balanced(
            "function Good { # unmatched } in comment\nWrite-Output ok\n}\n",
            "good.ps1", braces=True,
        )

    def test_balanced_but_invalid_powershell_is_parse_stop(self) -> None:
        with self.assertRaisesRegex(HARNESS.ContractError, "parser_error"):
            HARNESS._parse_powershell("function Broken { if () { } }", "broken.ps1")

    def test_cli_requires_externally_pinned_contracts(self) -> None:
        files = {
            "requirements": self.requirements, "triggers": self.triggers,
            "dispositions": self.dispositions(), "features": self.feature_catalog,
            "evidence": self.evidence, "reviewers": self.reviewers,
        }
        paths = {name: self.repo / f"{name}.jsonl" for name in files}
        for name, rows in files.items():
            HARNESS._write_jsonl(paths[name], rows)
        json_files = {
            "feature-manifest": self.feature_manifest,
            "evidence-manifest": self.evidence_manifest,
            "reviewer-manifest": self.reviewer_manifest,
            "audit-contract": self.audit_contract,
            "evidence-contract": self.evidence_contract,
        }
        json_paths = {name: self.repo / f"{name}.json" for name in json_files}
        for name, value in json_files.items():
            json_paths[name].write_text(json.dumps(value), encoding="utf-8")
        args = [
            "validate", "--root", str(self.repo), "--audited-commit", self.commit,
            "--run-id", self.RUN, "--snapshot-id", self.SNAPSHOT,
            "--requirements", str(paths["requirements"]), "--triggers", str(paths["triggers"]),
            "--dispositions", str(paths["dispositions"]), "--tooling-commit", self.TOOLING,
            "--feature-catalog", str(paths["features"]),
            "--feature-catalog-manifest", str(json_paths["feature-manifest"]),
            "--evidence-records", str(paths["evidence"]),
            "--evidence-manifest", str(json_paths["evidence-manifest"]),
            "--reviewer-records", str(paths["reviewers"]),
            "--reviewer-manifest", str(json_paths["reviewer-manifest"]),
            "--audit-contract", str(json_paths["audit-contract"]),
            "--expected-audit-contract-sha256", self.contract_sha,
            "--evidence-contract", str(json_paths["evidence-contract"]),
            "--expected-evidence-contract-sha256", self.evidence_contract_sha,
            "--evidence-root", str(self.repo),
        ]
        self.assertEqual(0, HARNESS.main(args))
        missing_external_pin = args.copy()
        index = missing_external_pin.index("--expected-audit-contract-sha256")
        del missing_external_pin[index:index + 2]
        with self.assertRaises(SystemExit):
            HARNESS.main(missing_external_pin)


if __name__ == "__main__":
    unittest.main()
