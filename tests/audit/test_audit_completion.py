from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.audit_completion import CompletionError, import_bundle


RUN = "RUN-001"
COMMIT = "a" * 40
TOOLING = "b" * 40
SNAPSHOT = "sha256:snapshot"
PLAN = "PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15"


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _seal(value: dict, field: str) -> tuple[dict, str]:
    sealed = dict(value)
    digest = hashlib.sha256(_canonical_json(sealed)).hexdigest()
    sealed[field] = digest
    return sealed, digest


class GateContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bundle = self.root / "bundle"
        self.master = self.root / "master"
        self.bundle.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_bundle(self, *, unknown: bool = False, foreign_ref: bool = False) -> tuple[Path, Path, Path, str, str]:
        requirements_path = self.bundle / "requirements_universe.jsonl"
        requirements_payload = _canonical_json({"requirement_id": "REQ-1"}) + b"\n"
        requirements_path.write_bytes(requirements_payload)
        features = [{
            "run_id": RUN,
            "audited_commit": COMMIT,
            "snapshot_id": SNAPSHOT,
            "feature_id": "FEAT-1",
            "path_id": "ui",
            "states": {"declared": {"value": "UNKNOWN" if unknown else "YES"}},
        }]
        findings = [{
            "run_id": RUN,
            "audited_commit": COMMIT,
            "snapshot_id": SNAPSHOT,
            "finding_id": "F-1",
            "feature_key": ["FEAT-X" if foreign_ref else "FEAT-1", "ui"],
        }]
        shard_specs = []
        for artifact_key, name, rows, primary_key, foreign_keys in (
            ("feature-state", "feature_states", features, ["feature_id", "path_id"], []),
            (
                "findings",
                "findings",
                findings,
                ["finding_id"],
                [{"field": "feature_key", "target_shard": "feature_states", "target_fields": ["feature_id", "path_id"]}],
            ),
        ):
            path = self.bundle / f"{name}.jsonl"
            payload = b"".join(_canonical_json(row) + b"\n" for row in rows)
            path.write_bytes(payload)
            shard_specs.append({
                "artifact_key": artifact_key,
                "name": name,
                "path": path.name,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "record_count": len(rows),
                "primary_key": primary_key,
                "foreign_keys": foreign_keys,
            })
        audit_contract, audit_sha = _seal({
            "schema_version": 1,
            "plan_id": PLAN,
            "run_id": RUN,
            "audited_commit": COMMIT,
            "tooling_commit": TOOLING,
            "snapshot_id": SNAPSHOT,
            "frozen_at": "2026-08-15T10:00:00+00:00",
            "expires_at": "2026-08-16T10:00:00+00:00",
            "artifacts": {
                "requirements-universe": {
                    "artifact_id": f"sha256:{hashlib.sha256(requirements_payload).hexdigest()}",
                    "ref": requirements_path.name,
                    "sha256": hashlib.sha256(requirements_payload).hexdigest(),
                    "bytes": len(requirements_payload),
                    "record_count": 1,
                }
            },
        }, "contract_sha256")
        audit_path = self.bundle / "audit_contract.json"
        audit_path.write_bytes(_canonical_json(audit_contract))

        evidence_artifacts = {}
        for spec in shard_specs:
            payload = (self.bundle / spec["path"]).read_bytes()
            evidence_artifacts[spec["artifact_key"]] = {
                "artifact_id": f"sha256:{spec['sha256']}",
                "ref": spec["path"],
                "sha256": spec["sha256"],
                "bytes": len(payload),
                "record_count": spec["record_count"],
            }
        evidence_contract, evidence_sha = _seal({
            "schema_version": 1,
            "plan_id": PLAN,
            "run_id": RUN,
            "audited_commit": COMMIT,
            "tooling_commit": TOOLING,
            "snapshot_id": SNAPSHOT,
            "audit_contract_sha256": audit_sha,
            "completed_at": "2026-08-15T11:00:00+00:00",
            "artifacts": evidence_artifacts,
        }, "evidence_contract_sha256")
        evidence_path = self.bundle / "evidence_contract.json"
        evidence_path.write_bytes(_canonical_json(evidence_contract))
        contract = {
            "schema_version": 1,
            "import_id": "IMPORT-001",
            "run_id": RUN,
            "audited_commit": COMMIT,
            "snapshot_id": SNAPSHOT,
            "tooling_commit": TOOLING,
            "audit_contract_sha256": audit_sha,
            "evidence_contract_sha256": evidence_sha,
            "qualification": "unqualified",
            "required_gate_results": {
                "feature_inventory": True,
                "symbol_contracts": True,
                "runtime_evidence": True,
                "reviewer_roster": True,
                "delta_ttl": True,
                "completion": True,
            },
            "shards": shard_specs,
        }
        contract_path = self.bundle / "atomic_import.json"
        contract_path.write_bytes(_canonical_json(contract))
        return contract_path, audit_path, evidence_path, audit_sha, evidence_sha

    def _import(self, bundle: tuple[Path, Path, Path, str, str]):
        contract, audit, evidence, audit_sha, evidence_sha = bundle
        return import_bundle(
            self.bundle,
            contract,
            self.master,
            audit_contract_path=audit,
            evidence_contract_path=evidence,
            expected_audit_contract_sha256=audit_sha,
            expected_evidence_contract_sha256=evidence_sha,
        )

    def test_positive_minimal(self) -> None:
        bundle = self._write_bundle()
        result = self._import(bundle)
        self.assertEqual(result["status"], "imported")
        current = (self.master / "CURRENT").read_text(encoding="utf-8")
        self.assertEqual(current, "IMPORT-001\n")
        self.assertTrue((self.master / "versions" / "IMPORT-001" / "feature_states.jsonl").is_file())

    def test_missing_required_rejected(self) -> None:
        bundle = self._write_bundle()
        contract = bundle[0]
        data = json.loads(contract.read_text(encoding="utf-8"))
        del data["snapshot_id"]
        contract.write_bytes(_canonical_json(data))
        with self.assertRaisesRegex(CompletionError, "snapshot_id"):
            self._import(bundle)

    def test_tampered_binding_rejected(self) -> None:
        bundle = self._write_bundle()
        with (self.bundle / "findings.jsonl").open("ab") as handle:
            handle.write(b"{}\n")
        with self.assertRaisesRegex(CompletionError, "SHA256"):
            self._import(bundle)

    def test_duplicate_or_foreign_id_rejected(self) -> None:
        bundle = self._write_bundle(foreign_ref=True)
        with self.assertRaisesRegex(CompletionError, "Fremdschluessel"):
            self._import(bundle)

    def test_unknown_blocks_completion(self) -> None:
        bundle = self._write_bundle(unknown=True)
        with self.assertRaisesRegex(CompletionError, "UNKNOWN"):
            self._import(bundle)

    def test_unsafe_import_id_or_staging_collision_rejected(self) -> None:
        bundle = self._write_bundle()
        contract = bundle[0]
        data = json.loads(contract.read_text(encoding="utf-8"))
        data["import_id"] = "../escape"
        contract.write_bytes(_canonical_json(data))
        with self.assertRaisesRegex(CompletionError, "import_id"):
            self._import(bundle)

        bundle = self._write_bundle()
        contract = bundle[0]
        data = json.loads(contract.read_text(encoding="utf-8"))
        original = self.bundle / "findings.jsonl"
        nested = self.bundle / "nested" / "feature_states.jsonl"
        nested.parent.mkdir()
        nested.write_bytes(original.read_bytes())
        data["shards"][1]["path"] = "nested/feature_states.jsonl"
        contract.write_bytes(_canonical_json(data))
        with self.assertRaisesRegex(CompletionError, "Zielname"):
            self._import(bundle)

    def test_contract_substitution_rejected(self) -> None:
        bundle = self._write_bundle()
        audit = bundle[1]
        value = json.loads(audit.read_text(encoding="utf-8"))
        value["audited_commit"] = "c" * 40
        value, _replacement_sha = _seal({k: v for k, v in value.items() if k != "contract_sha256"}, "contract_sha256")
        audit.write_bytes(_canonical_json(value))
        with self.assertRaisesRegex(CompletionError, "Auditcontract-SHA"):
            self._import(bundle)

    def test_failed_import_keeps_master_byteidentical(self) -> None:
        bundle = self._write_bundle()
        contract = bundle[0]
        self._import(bundle)
        before = {p.relative_to(self.master).as_posix(): p.read_bytes() for p in self.master.rglob("*") if p.is_file()}
        data = json.loads(contract.read_text(encoding="utf-8"))
        data["import_id"] = "IMPORT-002"
        contract.write_bytes(_canonical_json(data))
        with mock.patch("tools.audit_completion.os.replace", side_effect=OSError("injected")):
            with self.assertRaisesRegex(CompletionError, "Atomarer Pointerwechsel"):
                self._import(bundle)
        after = {p.relative_to(self.master).as_posix(): p.read_bytes() for p in self.master.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
