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
SNAPSHOT = "sha256:snapshot"


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


class GateContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bundle = self.root / "bundle"
        self.master = self.root / "master"
        self.bundle.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_bundle(self, *, unknown: bool = False, foreign_ref: bool = False) -> Path:
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
        for name, rows, primary_key, foreign_keys in (
            ("feature_states", features, ["feature_id", "path_id"], []),
            (
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
                "name": name,
                "path": path.name,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "record_count": len(rows),
                "primary_key": primary_key,
                "foreign_keys": foreign_keys,
            })
        contract = {
            "schema_version": 1,
            "import_id": "IMPORT-001",
            "run_id": RUN,
            "audited_commit": COMMIT,
            "snapshot_id": SNAPSHOT,
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
        return contract_path

    def test_positive_minimal(self) -> None:
        contract = self._write_bundle()
        result = import_bundle(self.bundle, contract, self.master)
        self.assertEqual(result["status"], "imported")
        current = (self.master / "CURRENT").read_text(encoding="utf-8")
        self.assertEqual(current, "IMPORT-001\n")
        self.assertTrue((self.master / "versions" / "IMPORT-001" / "feature_states.jsonl").is_file())

    def test_missing_required_rejected(self) -> None:
        contract = self._write_bundle()
        data = json.loads(contract.read_text(encoding="utf-8"))
        del data["snapshot_id"]
        contract.write_bytes(_canonical_json(data))
        with self.assertRaisesRegex(CompletionError, "snapshot_id"):
            import_bundle(self.bundle, contract, self.master)

    def test_tampered_binding_rejected(self) -> None:
        contract = self._write_bundle()
        with (self.bundle / "findings.jsonl").open("ab") as handle:
            handle.write(b"{}\n")
        with self.assertRaisesRegex(CompletionError, "SHA256"):
            import_bundle(self.bundle, contract, self.master)

    def test_duplicate_or_foreign_id_rejected(self) -> None:
        contract = self._write_bundle(foreign_ref=True)
        with self.assertRaisesRegex(CompletionError, "Fremdschluessel"):
            import_bundle(self.bundle, contract, self.master)

    def test_unknown_blocks_completion(self) -> None:
        contract = self._write_bundle(unknown=True)
        with self.assertRaisesRegex(CompletionError, "UNKNOWN"):
            import_bundle(self.bundle, contract, self.master)

    def test_failed_import_keeps_master_byteidentical(self) -> None:
        contract = self._write_bundle()
        import_bundle(self.bundle, contract, self.master)
        before = {p.relative_to(self.master).as_posix(): p.read_bytes() for p in self.master.rglob("*") if p.is_file()}
        data = json.loads(contract.read_text(encoding="utf-8"))
        data["import_id"] = "IMPORT-002"
        contract.write_bytes(_canonical_json(data))
        with mock.patch("tools.audit_completion.os.replace", side_effect=OSError("injected")):
            with self.assertRaisesRegex(CompletionError, "Atomarer Pointerwechsel"):
                import_bundle(self.bundle, contract, self.master)
        after = {p.relative_to(self.master).as_posix(): p.read_bytes() for p in self.master.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
