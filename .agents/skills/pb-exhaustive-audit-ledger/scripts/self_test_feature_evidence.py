from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from verify_feature_matrix import AXES, canonical_id, verify_feature_contract
from verify_symbol_states import verify_symbol_contract


COMMIT = "a" * 40
RUN_ID = "RUN-001"
SNAPSHOT_ID = "snapshot-001"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runtime_run(root: Path) -> dict:
    input_path = root / "input.json"
    post_path = root / "post.json"
    log_path = root / "run.log"
    input_path.write_text('{"input": 1}\n', encoding="utf-8")
    post_path.write_text('{"ok": true}\n', encoding="utf-8")
    log_path.write_text("exit=0\n", encoding="utf-8")
    row = {
        "run_id": RUN_ID,
        "runtime_run_id": "LIVE-001",
        "audited_commit": COMMIT,
        "timestamp": "2026-08-15T14:00:00+00:00",
        "input": {"ref": "input.json", "sha256": _sha(input_path)},
        "command": {"argv": ["python", "verify.py"], "cwd": "."},
        "exit": {"code": 0, "ref": "run.log", "sha256": _sha(log_path)},
        "postcondition": {"ref": "post.json", "sha256": _sha(post_path), "result": "pass"},
        "artifacts": [],
        "covered_feature_paths": ["FEAT-001/ui"],
        "covered_symbol_ids": ["SYM-1"],
        "covered_axes": list(AXES),
    }
    row["evidence_id"] = canonical_id(row)
    return row


def _states(evidence_id: str) -> dict:
    runtime_evidence = [{
        "kind": "runtime",
        "evidence_id": evidence_id,
        "ref": "runtime_runs.jsonl",
        "commit_sha": COMMIT,
        "run_id": RUN_ID,
        "timestamp": "2026-08-15T14:00:00+00:00",
    }]
    return {
        axis: {"value": "YES", "evidence": runtime_evidence}
        for axis in AXES
    }


def _feature(evidence_id: str) -> dict:
    return {
        "run_id": RUN_ID,
        "feature_id": "FEAT-001",
        "path_id": "ui",
        "name": "Analyse",
        "user_surface": "ui",
        "trigger": "button",
        "handler": "ui/x.py:10",
        "service": "services/x.py:20",
        "worker": "workers/x.py:30",
        "state_store": "database/models.py:1",
        "config_keys": [],
        "expected_result": "sichtbar",
        "evidence_age": "current-head",
        "verdict": "verified",
        "blockers": [],
        "not_checked": [],
        "snapshot_id": SNAPSHOT_ID,
        "commit_sha": COMMIT,
        "reviewer_id": "reviewer-1",
        "signed_at": "2026-08-15T14:01:00+00:00",
        "states": _states(evidence_id),
        "overall_state": "verified",
    }


def _requirement() -> dict:
    return {
        "run_id": RUN_ID,
        "snapshot_id": SNAPSHOT_ID,
        "audited_commit": COMMIT,
        "feature_id": "FEAT-001",
        "path_id": "ui",
        "source_kind": "ui-trigger",
        "source_ref": "ui/x.py:10",
        "required_runtime_axes": ["executed", "result", "live_evidence"],
    }


class FeatureEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = _runtime_run(self.root)
        self.feature = _feature(self.runtime["evidence_id"])
        self.requirement = _requirement()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def verify(self, *, matrix=None, requirements=None, runtime=None) -> list[str]:
        return verify_feature_contract(
            [self.feature] if matrix is None else matrix,
            [self.requirement] if requirements is None else requirements,
            [self.runtime] if runtime is None else runtime,
            evidence_root=self.root,
            audited_commit=COMMIT,
            snapshot_id=SNAPSHOT_ID,
            run_id=RUN_ID,
        )

    def test_valid_contract_passes(self) -> None:
        self.assertEqual([], self.verify())

    def test_missing_required_feature_fails_exact_set(self) -> None:
        errors = self.verify(matrix=[])
        self.assertTrue(any("Feature-Mengengleichheit" in error for error in errors), errors)

    def test_unknown_required_runtime_axis_blocks_completion(self) -> None:
        row = json.loads(json.dumps(self.feature))
        row["states"]["executed"] = {"value": "UNKNOWN", "evidence": [{
            "kind": "not-checked", "ref": "missing", "reason": "nicht ausgefuehrt",
            "commit_sha": COMMIT, "run_id": RUN_ID, "timestamp": "2026-08-15T14:00:00+00:00",
        }]}
        row["not_checked"] = ["executed"]
        row["overall_state"] = "not-checked"
        errors = self.verify(matrix=[row])
        self.assertTrue(any("Pflicht-Runtimeachse executed ist UNKNOWN" in error for error in errors), errors)

    def test_overall_state_is_derived(self) -> None:
        row = json.loads(json.dumps(self.feature))
        row["overall_state"] = "failed"
        errors = self.verify(matrix=[row])
        self.assertTrue(any("overall_state" in error for error in errors), errors)

    def test_runtime_evidence_requires_existing_content_addressed_run(self) -> None:
        row = json.loads(json.dumps(self.feature))
        row["states"]["executed"]["evidence"][0]["evidence_id"] = "sha256:deadbeef"
        errors = self.verify(matrix=[row])
        self.assertTrue(any("unbekannte Runtime-evidence_id" in error for error in errors), errors)

    def test_runtime_run_for_other_feature_cannot_support_yes(self) -> None:
        runtime = json.loads(json.dumps(self.runtime))
        runtime["covered_feature_paths"] = ["FEAT-OTHER/ui"]
        runtime["evidence_id"] = canonical_id(runtime)
        row = _feature(runtime["evidence_id"])
        errors = self.verify(matrix=[row], runtime=[runtime])
        self.assertTrue(any("deckt Featurepfad nicht" in error for error in errors), errors)

    def test_runtime_artifact_hash_mismatch_fails(self) -> None:
        runtime = json.loads(json.dumps(self.runtime))
        runtime["postcondition"]["sha256"] = "0" * 64
        runtime["evidence_id"] = canonical_id(runtime)
        row = _feature(runtime["evidence_id"])
        errors = self.verify(matrix=[row], runtime=[runtime])
        self.assertTrue(any("SHA256 stimmt nicht" in error for error in errors), errors)

    def test_failed_runtime_run_cannot_support_yes(self) -> None:
        runtime = json.loads(json.dumps(self.runtime))
        runtime["postcondition"]["result"] = "fail"
        runtime["evidence_id"] = canonical_id(runtime)
        row = _feature(runtime["evidence_id"])
        errors = self.verify(matrix=[row], runtime=[runtime])
        self.assertTrue(any("kein erfolgreicher Runtimebeleg" in error for error in errors), errors)


class SymbolStateTests(unittest.TestCase):
    def test_exact_set_and_disposition_contract(self) -> None:
        manifest = [{
            "run_id": RUN_ID, "snapshot_id": SNAPSHOT_ID, "audited_commit": COMMIT,
            "symbol_id": "SYM-1", "path": "services/x.py", "qualified_name": "x.run",
            "kind": "function", "line_start": 1, "line_end": 3,
        }]
        valid = [{
            **manifest[0], "feature_ids": ["FEAT-001"], "disposition": "non-runtime",
            "runtime_evidence_ids": [],
            "non_runtime_contract": {"kind": "pure-function", "ref": "tests/test_x.py:1", "reason": "deterministisch"},
        }]
        self.assertEqual([], verify_symbol_contract(
            valid, manifest, runtime_symbol_coverage={}, known_feature_ids={"FEAT-001"}, audited_commit=COMMIT,
            snapshot_id=SNAPSHOT_ID, run_id=RUN_ID,
        ))
        errors = verify_symbol_contract(
            [], manifest, runtime_symbol_coverage={}, known_feature_ids={"FEAT-001"}, audited_commit=COMMIT,
            snapshot_id=SNAPSHOT_ID, run_id=RUN_ID,
        )
        self.assertTrue(any("Symbol-Mengengleichheit" in error for error in errors), errors)

    def test_unknown_feature_fk_fails(self) -> None:
        manifest = [{
            "run_id": RUN_ID, "snapshot_id": SNAPSHOT_ID, "audited_commit": COMMIT,
            "symbol_id": "SYM-1", "path": "services/x.py", "qualified_name": "x.run",
            "kind": "function", "line_start": 1, "line_end": 3,
        }]
        states = [{
            **manifest[0], "feature_ids": ["FEAT-MISSING"], "disposition": "non-runtime",
            "runtime_evidence_ids": [],
            "non_runtime_contract": {"kind": "pure-function", "ref": "tests/test_x.py:1", "reason": "deterministisch"},
        }]
        errors = verify_symbol_contract(
            states, manifest, runtime_symbol_coverage={}, known_feature_ids={"FEAT-001"},
            audited_commit=COMMIT, snapshot_id=SNAPSHOT_ID, run_id=RUN_ID,
        )
        self.assertTrue(any("unbekannte feature_id" in error for error in errors), errors)

    def test_runtime_evidence_must_cover_symbol(self) -> None:
        manifest = [{
            "run_id": RUN_ID, "snapshot_id": SNAPSHOT_ID, "audited_commit": COMMIT,
            "symbol_id": "SYM-1", "path": "services/x.py", "qualified_name": "x.run",
            "kind": "function", "line_start": 1, "line_end": 3,
        }]
        states = [{
            **manifest[0], "feature_ids": ["FEAT-001"], "disposition": "runtime",
            "runtime_evidence_ids": ["sha256:run"], "non_runtime_contract": None,
        }]
        errors = verify_symbol_contract(
            states, manifest, runtime_symbol_coverage={"sha256:run": {"SYM-OTHER"}},
            known_feature_ids={"FEAT-001"}, audited_commit=COMMIT,
            snapshot_id=SNAPSHOT_ID, run_id=RUN_ID,
        )
        self.assertTrue(any("deckt Symbol nicht" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
