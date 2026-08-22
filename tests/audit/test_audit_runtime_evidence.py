from __future__ import annotations

import copy
import ctypes
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "audit_runtime_evidence.py"

GLOBAL_ARTIFACT_KEYS = {
    "requirements-universe", "trigger-universe", "feature-catalog",
    "symbol-catalog", "edge-catalog", "runtime-scenario-catalog",
    "runtime-feature-universe", "runtime-symbol-universe",
    "runtime-executor-manifest", "runtime-dependency-manifest",
    "reviewer-trust-policy", "reviewer-contract",
    "reviewer-readiness-binding", "reviewer-spawn-journal",
}


def _load_tool():
    spec = importlib.util.spec_from_file_location("audit_runtime_evidence", TOOL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Runtime-Evidence-Modul nicht ladbar")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


EMITTER = '''from pathlib import Path
import os
run_dir = Path(os.environ["PB_AUDIT_RUN_DIR"])
(run_dir / "artifact.txt").write_text("result\\n", encoding="utf-8")
print("scenario-ok")
'''

HARNESS = r'''import hashlib,json,os,runpy,sys,time,pkgutil,typing,weakref,_weakrefset
from pathlib import Path
descriptor_path, report_path = map(Path, sys.argv[1:3])
descriptor_bytes = descriptor_path.read_bytes()
descriptor = json.loads(descriptor_bytes)
before = set(sys.modules)
started = time.time_ns()
exit_code = 0
try:
    target_path = Path(os.environ["PB_AUDIT_ROOT"]) / descriptor["target_path"]
    runpy.run_path(target_path, run_name="__main__")
except SystemExit as exc:
    exit_code = int(exc.code or 0)
loaded = []
for name in sorted(set(sys.modules) - before):
    origin = getattr(sys.modules[name], "__file__", None)
    if origin and Path(origin).is_file():
        data = Path(origin).read_bytes()
        loaded.append({"name": name, "origin": str(Path(origin).resolve()), "sha256": hashlib.sha256(data).hexdigest()})
report = {"schema_version":1,"descriptor_sha256":hashlib.sha256(descriptor_bytes).hexdigest(),"target_exit_code":exit_code,"started_ns":started,"ended_ns":time.time_ns(),"loaded_modules":loaded}
report_path.write_text(json.dumps(report,sort_keys=True,separators=(",", ":"))+"\n", encoding="utf-8")
raise SystemExit(exit_code)
'''


class GateContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.shared = tempfile.TemporaryDirectory()
        cls.base = Path(cls.shared.name)
        cls.repo = cls.base / "repo"
        cls.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=cls.repo, check=True)
        subprocess.run(["git", "config", "user.email", "audit@example.invalid"], cwd=cls.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Audit Contract"], cwd=cls.repo, check=True)
        (cls.repo / "scenario.py").write_text(EMITTER, encoding="utf-8")
        (cls.repo / "foreign.py").write_text("import fractions\n" + EMITTER, encoding="utf-8")
        (cls.repo / "numbers_target.py").write_text("import numbers\n" + EMITTER, encoding="utf-8")
        (cls.repo / "slow.py").write_text("import time\ntime.sleep(0.6)\n" + EMITTER, encoding="utf-8")
        (cls.repo / "self_trace.py").write_text(
            "from pathlib import Path\nimport os\nPath(os.environ['PB_AUDIT_RUN_DIR'],'trace.jsonl').write_text('{}\\n')\n" + EMITTER,
            encoding="utf-8",
        )
        cls.pid_marker = cls.base / "tree-pids.json"
        (cls.repo / "tree_timeout.py").write_text(
            "import subprocess,sys,time\n" + f"marker={str(cls.pid_marker)!r}\n" +
            "grand='import time; time.sleep(60)'\n"
            "child='import json,os,subprocess,sys,time; p=subprocess.Popen([sys.executable,\"-I\",\"-S\",\"-c\",sys.argv[2]]); open(sys.argv[1],\"w\").write(json.dumps([os.getpid(),p.pid])); time.sleep(60)'\n"
            "subprocess.Popen([sys.executable,'-I','-S','-c',child,marker,grand])\ntime.sleep(60)\n",
            encoding="utf-8",
        )
        (cls.repo / ".gitattributes").write_text("scenario.py filter=evil\n", encoding="utf-8")
        subprocess.run(["git", "add", "scenario.py", "foreign.py", "numbers_target.py", "slow.py", "self_trace.py", "tree_timeout.py", ".gitattributes"], cwd=cls.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "audited product"], cwd=cls.repo, check=True)
        cls.audited_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cls.repo, check=True, capture_output=True, text=True).stdout.strip()
        tool_target = cls.repo / "tools" / "audit_runtime_evidence.py"
        tool_target.parent.mkdir()
        shutil.copy2(TOOL_PATH, tool_target)
        (cls.repo / "harness.py").write_text(HARNESS, encoding="utf-8")
        (cls.repo / "checker.py").write_text("from pathlib import Path\nimport sys\nraise SystemExit(0 if Path(sys.argv[1]).read_text() == 'result\\n' else 3)\n", encoding="utf-8")
        (cls.repo / "tamper_checker.py").write_text("from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_text('{}\\n')\n", encoding="utf-8")
        subprocess.run(["git", "add", "tools/audit_runtime_evidence.py", "harness.py", "checker.py", "tamper_checker.py"], cwd=cls.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "trusted tooling harness"], cwd=cls.repo, check=True)
        cls.tooling_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cls.repo, check=True, capture_output=True, text=True).stdout.strip()
        cls.tool = _load_tool()
        evil = cls.base / "evil_filter.py"
        evil.write_text("import sys\nsys.stdin.buffer.read()\nsys.stdout.write('raise SystemExit(91)\\n')\n", encoding="utf-8")
        subprocess.run(["git", "config", "filter.evil.smudge", f'"{sys.executable}" "{evil}"'], cwd=cls.repo, check=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.shared.cleanup()

    def setUp(self) -> None:
        self.evidence = self.base / f"evidence-{time.time_ns()}"
        (self.evidence / "inputs").mkdir(parents=True)
        self.input_path = self.evidence / "inputs" / "input.json"
        self.input_path.write_text('{"fixture":true}\n', encoding="utf-8")
        self.catalog_path = self.evidence / "scenario_catalog.jsonl"
        self.feature_path = self.evidence / "features.jsonl"
        self.symbol_path = self.evidence / "symbols.jsonl"
        self.executor_path = self.evidence / "executors.json"
        self.dependency_path = self.evidence / "dependencies.json"
        self.contract_path = self.evidence / "audit_contract.json"
        runtime_keys = {
            "runtime-scenario-catalog", "runtime-feature-universe",
            "runtime-symbol-universe", "runtime-executor-manifest",
            "runtime-dependency-manifest",
        }
        self.other_artifacts = {}
        for key in sorted(GLOBAL_ARTIFACT_KEYS - runtime_keys):
            path = self.evidence / f"{key}.json"
            path.write_text("{}\n", encoding="utf-8")
            self.other_artifacts[key] = path
        self.write_jsonl(self.feature_path, [{"feature_id": "FEAT-001", "path_id": "main"}])
        self.symbol_path.write_text("", encoding="utf-8")
        self.executor_path.write_bytes(_json_bytes({"python": {"path": sys.executable, "sha256": _sha(Path(sys.executable)), "version": sys.version}}) + b"\n")
        self.dependency_path.write_bytes(_json_bytes({"schema_version": 1, "python_version": sys.version, "stdlib_modules": [], "modules": []}) + b"\n")
        self.write_catalog([self.valid_scenario()])
        self.write_contract()

    def tearDown(self) -> None:
        shutil.rmtree(self.evidence, ignore_errors=True)
        self.pid_marker.unlink(missing_ok=True)

    def write_jsonl(self, path: Path, rows: list[dict]) -> None:
        path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")

    def valid_scenario(self, *, scenario_id: str = "SCN-001", script: str = "scenario.py") -> dict:
        row = {
            "schema_version": 3, "run_id": "RUN-001", "scenario_id": scenario_id,
            "audited_commit": self.audited_commit, "tooling_commit": self.tooling_commit,
            "snapshot_id": "snapshot-001", "feature_target": "FEAT-001/main",
            "harness": {"root": "tooling", "argv": ["python", "harness.py", "{target_descriptor}", "{harness_report}"], "cwd": "."},
            "target": {"path": script, "argv": []}, "timeout_seconds": 5.0,
            "inputs": [{"name": "fixture", "ref": "inputs/input.json", "sha256": _sha(self.input_path)}],
            "allowed_symbol_ids": [], "allowed_axes": ["executed", "result", "live_evidence"],
            "required_modules": [], "required_stdlib_modules": [],
            "postcondition": {"root": "tooling", "argv": ["python", "checker.py", "{run_dir}/artifact.txt"], "cwd": ".", "timeout_seconds": 5.0},
            "artifacts": [{"name": "result", "ref": "artifact.txt", "required": True}],
        }
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        return row

    def write_catalog(self, rows: list[dict]) -> None:
        self.write_jsonl(self.catalog_path, rows)

    def write_contract(self, *, bind_authority: bool = True, authority_overrides: dict | None = None, **overrides: object) -> None:
        def artifact(path: Path, records: int) -> dict:
            digest = _sha(path)
            return {"artifact_id":f"sha256:{digest}","ref":path.name,"sha256":digest,
                    "bytes":path.stat().st_size,"record_count":records}
        contract = {
            "schema_version": 1, "plan_id":"PB-STUDIO-EXHAUSTIVE-AUDIT",
            "run_id": "RUN-001", "snapshot_id": "snapshot-001",
            "audited_commit": self.audited_commit, "tooling_commit": self.tooling_commit,
            "frozen_at":"2026-08-15T00:00:00+00:00", "expires_at":"2099-08-15T00:00:00+00:00",
            "artifacts": {
                "runtime-scenario-catalog":artifact(self.catalog_path,len(self.catalog_path.read_text().splitlines())),
                "runtime-feature-universe":artifact(self.feature_path,len(self.feature_path.read_text().splitlines())),
                "runtime-symbol-universe":artifact(self.symbol_path,len(self.symbol_path.read_text().splitlines())),
                "runtime-executor-manifest":artifact(self.executor_path,1),
                "runtime-dependency-manifest":artifact(self.dependency_path,1),
                **{key: artifact(path, 1) for key, path in self.other_artifacts.items()},
            },
        }
        contract.update(overrides)
        contract["contract_sha256"] = self.tool.canonical_sha256(contract, omit={"contract_sha256"})
        self.contract_path.write_bytes(_json_bytes(contract) + b"\n")
        self.expected_contract_sha256 = contract["contract_sha256"]
        if bind_authority:
            self.write_authority_policy(contract, authority_overrides=authority_overrides)

    def write_authority_policy(
        self, contract: dict | None = None, *, authority_overrides: dict | None = None,
        policy_path: str = "config/audit_runtime_authority_policy.json",
    ) -> str:
        contract = contract or json.loads(self.contract_path.read_text(encoding="utf-8"))
        policy = {
            "schema_version": 1,
            "audit_contract_sha256": contract["contract_sha256"],
            "plan_id": contract["plan_id"], "run_id": contract["run_id"],
            "snapshot_id": contract["snapshot_id"],
            "audited_commit": contract["audited_commit"], "tooling_commit": contract["tooling_commit"],
            "allow_same_audited_tooling_commit": False,
        }
        policy.update(authority_overrides or {})
        target = self.repo / policy_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_json_bytes(policy) + b"\n")
        subprocess.run(["git", "add", "--", policy_path], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "--allow-empty", "-qm", f"authority {time.time_ns()}"], cwd=self.repo, check=True)
        self.authority_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.repo, check=True, capture_output=True, text=True,
        ).stdout.strip()
        return self.authority_commit

    def refresh_contract(self) -> None:
        self.write_contract()

    def run_valid(
        self, runtime_run_id: str = "LIVE-001", scenario_id: str = "SCN-001", *,
        expected_contract_sha256: str | None = None, authority_commit: str | None = None,
        expected_authority_commit: str | None = None,
        authority_policy_path: str = "config/audit_runtime_authority_policy.json",
    ) -> dict:
        return self.tool.run_scenario(repo_root=self.repo, evidence_root=self.evidence, contract_path=self.contract_path,
            expected_contract_sha256=expected_contract_sha256 or self.expected_contract_sha256,
            authority_commit=authority_commit or self.authority_commit,
            expected_authority_commit=expected_authority_commit or self.authority_commit,
            authority_policy_path=authority_policy_path, scenario_id=scenario_id, runtime_run_id=runtime_run_id)

    def projection_trust(self) -> dict:
        return {
            "repo_root": self.repo,
            "expected_contract_sha256": self.expected_contract_sha256,
            "expected_authority_commit": self.authority_commit,
        }

    def test_positive_minimal(self) -> None:
        receipt = self.run_valid()
        self.assertEqual(receipt["covered_feature_paths"], ["FEAT-001/main"])
        self.assertEqual(receipt["covered_symbol_ids"], [])
        self.assertEqual(receipt["covered_axes"], ["executed", "live_evidence", "result"])
        self.assertEqual(receipt["harness"]["source"]["commit"], self.tooling_commit)
        self.assertEqual(receipt["target"]["source"]["commit"], self.audited_commit)
        self.assertEqual(receipt["observer"]["source"], "harness-controlled")
        self.assertEqual(receipt["observer"]["threat_boundary"], "shared-interpreter-no-cryptographic-anti-tamper")
        self.assertEqual(receipt["environment"]["python_flags"], ["-I", "-S"])
        self.assertFalse(receipt["observer"]["cryptographic_anti_tamper"])
        self.assertEqual(receipt["materialization"]["method"], "git-cat-file")
        self.assertNotEqual(receipt["audited_commit"], receipt["tooling_commit"])
        self.assertEqual(receipt["authority"]["authority_commit"], self.authority_commit)
        self.assertEqual(receipt["authority"]["expected_authority_commit"], self.authority_commit)
        self.assertEqual(
            receipt["authority"]["trust_boundary"],
            "trusted-external-authority-pin-required; compromised-external-pin-not-detected",
        )
        expected_blob = subprocess.run(
            ["git", "rev-parse", f"{self.authority_commit}:config/audit_runtime_authority_policy.json"],
            cwd=self.repo, check=True, capture_output=True, text=True,
        ).stdout.strip()
        policy_bytes = subprocess.run(
            ["git", "show", f"{self.authority_commit}:config/audit_runtime_authority_policy.json"],
            cwd=self.repo, check=True, capture_output=True,
        ).stdout
        self.assertEqual(receipt["authority"]["git_blob"], expected_blob)
        self.assertEqual(receipt["authority"]["sha256"], hashlib.sha256(policy_bytes).hexdigest())
        self.assertIn(b"scenario-ok", (self.evidence / receipt["stdout"]["ref"]).read_bytes())
        run_dir = self.evidence / "runs" / "LIVE-001"
        projection = json.loads((run_dir / "projection.json").read_text(encoding="utf-8"))
        self.assertEqual(projection["evidence_id"], receipt["evidence_id"])
        self.assertEqual(projection["covered_feature_paths"], ["FEAT-001/main"])
        self.assertEqual(projection["covered_symbol_ids"], [])
        self.assertEqual(projection["proof_ref"], "runs/LIVE-001/receipt.json")
        self.assertEqual(projection["proof_sha256"], _sha(run_dir / "receipt.json"))
        exported = (self.evidence / "runtime-evidence.jsonl").read_bytes()
        self.assertEqual(exported, _json_bytes(projection) + b"\n")

    def test_global_contract_artifact_exact_set_missing_and_extra_rejected(self) -> None:
        for mutation in ("missing", "extra"):
            with self.subTest(mutation=mutation):
                contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
                if mutation == "missing":
                    del contract["artifacts"]["feature-catalog"]
                else:
                    contract["artifacts"]["foreign"] = next(iter(contract["artifacts"].values()))
                contract["contract_sha256"] = self.tool.canonical_sha256(contract, omit={"contract_sha256"})
                self.contract_path.write_bytes(_json_bytes(contract) + b"\n")
                self.expected_contract_sha256 = contract["contract_sha256"]
                self.write_authority_policy(contract)
                with self.assertRaisesRegex(self.tool.ContractError, "Exact-Set"):
                    self.run_valid(runtime_run_id=f"LIVE-{mutation.upper()}")
                self.write_contract()

    def test_exact_five_runtime_descriptors_are_individually_validated(self) -> None:
        runtime_keys = (
            "runtime-scenario-catalog", "runtime-feature-universe",
            "runtime-symbol-universe", "runtime-executor-manifest",
            "runtime-dependency-manifest",
        )
        for index, key in enumerate(runtime_keys):
            with self.subTest(key=key):
                contract = json.loads(self.contract_path.read_text(encoding="utf-8"))
                contract["artifacts"][key]["record_count"] += 1
                contract["contract_sha256"] = self.tool.canonical_sha256(contract, omit={"contract_sha256"})
                self.contract_path.write_bytes(_json_bytes(contract) + b"\n")
                self.expected_contract_sha256 = contract["contract_sha256"]
                self.write_authority_policy(contract)
                with self.assertRaisesRegex(self.tool.ContractError, "record_count"):
                    self.run_valid(runtime_run_id=f"LIVE-DESCRIPTOR-{index}")
                self.write_contract()

    def _minimal_forged_receipt(self) -> tuple[dict, bytes]:
        receipt = {
            "plan_id": "PLAN", "run_id": "RUN-001", "runtime_run_id": "LIVE-SYNTH",
            "audited_commit": "1" * 40, "tooling_commit": "2" * 40,
            "snapshot_id": "snapshot-001", "scenario_id": "SCN-001",
            "timestamp": "2026-08-16T00:00:00+00:00",
            "covered_feature_paths": ["FEAT-001/main"],
            "covered_symbol_ids": [],
            "covered_axes": ["executed", "live_evidence", "result"],
        }
        receipt["evidence_id"] = self.tool.canonical_evidence_id(receipt)
        return receipt, _json_bytes(receipt) + b"\n"

    def test_minimal_forged_receipt_cannot_authorize_projection_or_export(self) -> None:
        receipt, receipt_bytes = self._minimal_forged_receipt()
        forged_run = self.evidence / "runs" / "LIVE-SYNTH"
        forged_run.mkdir(parents=True)
        with self.assertRaisesRegex(self.tool.ContractError, "Rich Receipt.*Exact-Fields"):
            self.tool.build_runtime_projection(receipt, receipt_bytes, forged_run, **self.projection_trust())
        projection = {
            "evidence_id": receipt["evidence_id"], "evidence_kind": "runtime",
            "runtime_run_id": receipt["runtime_run_id"],
            "covered_feature_paths": receipt["covered_feature_paths"],
            "covered_symbol_ids": [], "covered_axes": receipt["covered_axes"],
            "proof_ref": "runs/LIVE-SYNTH/receipt.json",
            "proof_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            "run_id": receipt["run_id"], "audited_commit": receipt["audited_commit"],
            "tooling_commit": receipt["tooling_commit"], "snapshot_id": receipt["snapshot_id"],
            "timestamp": receipt["timestamp"],
        }
        projection["record_sha256"] = self.tool.canonical_sha256(projection)
        (forged_run / "receipt.json").write_bytes(receipt_bytes)
        (forged_run / "projection.json").write_bytes(_json_bytes(projection) + b"\n")
        (self.evidence / "runtime_runs.jsonl").write_bytes(receipt_bytes)
        with self.assertRaisesRegex(self.tool.ContractError, "Rich Receipt.*Exact-Fields"):
            self.tool.export_runtime_evidence(self.evidence, **self.projection_trust())

    def test_projection_api_every_field_tamper_rejected_against_full_rich_receipt(self) -> None:
        receipt = self.run_valid()
        run_dir = self.evidence / "runs" / "LIVE-001"
        receipt_bytes = (run_dir / "receipt.json").read_bytes()
        projection = json.loads((run_dir / "projection.json").read_text(encoding="utf-8"))
        self.tool.validate_runtime_projection(
            projection, receipt, receipt_bytes, run_dir, **self.projection_trust(),
        )
        mutations = {
            "evidence_id": "sha256:" + "0" * 64,
            "evidence_kind": "foreign", "runtime_run_id": "LIVE-X",
            "covered_feature_paths": ["FEAT-X/main"],
            "covered_symbol_ids": ["SYM-X"], "covered_axes": ["executed"],
            "proof_ref": "runs/LIVE-X/receipt.json", "proof_sha256": "0" * 64,
            "run_id": "RUN-X", "audited_commit": "3" * 40,
            "tooling_commit": "4" * 40, "snapshot_id": "snapshot-X",
            "timestamp": "2026-08-16T01:00:00+00:00", "record_sha256": "0" * 64,
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                tampered = dict(projection)
                tampered[field] = value
                if field != "record_sha256":
                    tampered["record_sha256"] = self.tool.canonical_sha256(
                        tampered, omit={"record_sha256"},
                    )
                with self.assertRaises(self.tool.ContractError):
                    self.tool.validate_runtime_projection(
                        tampered, receipt, receipt_bytes, run_dir, **self.projection_trust(),
                    )

    def test_plural_symbol_projection_is_capacity_only_without_external_observer(self) -> None:
        receipt = self.run_valid()
        run_dir = self.evidence / "runs" / "LIVE-001"
        receipt["covered_symbol_ids"] = ["SYM-A", "SYM-B"]
        receipt["evidence_id"] = self.tool.canonical_evidence_id(receipt)
        receipt_bytes = _json_bytes(receipt) + b"\n"
        with self.assertRaisesRegex(self.tool.ContractError, "Symbol-Observer.*nicht implementiert"):
            self.tool.build_runtime_projection(
                receipt, receipt_bytes, run_dir, **self.projection_trust(),
            )

    def test_projection_export_requires_external_contract_and_authority_pins(self) -> None:
        self.run_valid()
        with self.assertRaises(TypeError):
            self.tool.export_runtime_evidence(self.evidence)
        with self.assertRaisesRegex(self.tool.ContractError, "externer Contract-Pin"):
            self.tool.export_runtime_evidence(
                self.evidence, repo_root=self.repo,
                expected_contract_sha256="0" * 64,
                expected_authority_commit=self.authority_commit,
            )
        with self.assertRaisesRegex(self.tool.ContractError, "externer Authority-Pin"):
            self.tool.export_runtime_evidence(
                self.evidence, repo_root=self.repo,
                expected_contract_sha256=self.expected_contract_sha256,
                expected_authority_commit="0" * 40,
            )

    def test_required_modules_rejects_structured_item_with_contract_error(self) -> None:
        row = self.valid_scenario()
        row["required_modules"] = [{}]
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "Scenario.required_modules ungueltig"):
            self.run_valid()

    def test_full_rich_receipt_trust_components_reject_resealed_tamper(self) -> None:
        receipt = self.run_valid()
        run_dir = self.evidence / "runs" / "LIVE-001"
        mutations = {
            "authority": lambda row: row["authority"]["policy"].update({"run_id": "FORGED"}),
            "audit_contract": lambda row: row["audit_contract"].update({"contract_sha256": "0" * 64}),
            "scenario": lambda row: row.update({"scenario_sha256": "0" * 64}),
            "runner": lambda row: row["runner"].update({"sha256": "0" * 64}),
            "trace": lambda row: row["trace"].update({"sha256": "0" * 64}),
            "postcondition": lambda row: row["postcondition"].update({"result": "forged"}),
            "final_integrity": lambda row: row.update({"final_integrity_sha256": "0" * 64}),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                tampered = json.loads(json.dumps(receipt))
                mutate(tampered)
                tampered["evidence_id"] = self.tool.canonical_evidence_id(tampered)
                tampered_bytes = _json_bytes(tampered) + b"\n"
                with self.assertRaises(self.tool.ContractError):
                    self.tool.build_runtime_projection(
                        tampered, tampered_bytes, run_dir, **self.projection_trust(),
                    )

    def test_projection_and_export_replay_harness_loaded_module_validation(self) -> None:
        row = self.valid_scenario(script="numbers_target.py")
        row["required_stdlib_modules"] = ["numbers"]
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.dependency_path.write_bytes(_json_bytes({
            "schema_version": 1, "python_version": sys.version,
            "stdlib_modules": ["numbers"], "modules": [],
        }) + b"\n")
        self.write_catalog([row])
        self.refresh_contract()
        receipt = self.run_valid()
        run_dir = self.evidence / "runs" / "LIVE-001"
        report_path = run_dir / "harness_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(["numbers"], [item["name"] for item in report["loaded_modules"]])
        report["loaded_modules"] = []
        report_bytes = _json_bytes(report) + b"\n"
        report_path.chmod(0o666)
        report_path.write_bytes(report_bytes)
        receipt["target"]["report"] = report
        integrity = self.tool._snapshot_files(run_dir)
        integrity.pop("receipt.json")
        integrity.pop("projection.json")
        receipt["final_integrity_sha256"] = self.tool.canonical_sha256(integrity)
        receipt["evidence_id"] = self.tool.canonical_evidence_id(receipt)
        receipt_bytes = _json_bytes(receipt) + b"\n"

        failures: list[str] = []
        try:
            self.tool.build_runtime_projection(
                receipt, receipt_bytes, run_dir, **self.projection_trust(),
            )
        except self.tool.ContractError:
            pass
        else:
            failures.append("projection")

        projection = json.loads((run_dir / "projection.json").read_text(encoding="utf-8"))
        projection["evidence_id"] = receipt["evidence_id"]
        projection["proof_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
        projection["record_sha256"] = self.tool.canonical_sha256(
            projection, omit={"record_sha256"},
        )
        (run_dir / "receipt.json").chmod(0o666)
        (run_dir / "receipt.json").write_bytes(receipt_bytes)
        (run_dir / "projection.json").chmod(0o666)
        (run_dir / "projection.json").write_bytes(_json_bytes(projection) + b"\n")
        (self.evidence / "runtime_runs.jsonl").write_bytes(receipt_bytes)
        try:
            self.tool.export_runtime_evidence(self.evidence, **self.projection_trust())
        except self.tool.ContractError:
            pass
        else:
            failures.append("export")
        self.assertEqual([], failures)

    def test_projection_and_export_require_scenario_canonical_input_refs(self) -> None:
        receipt = self.run_valid()
        run_dir = self.evidence / "runs" / "LIVE-001"
        canonical_input = run_dir / "sealed" / "inputs" / "fixture.json"
        forged_input = run_dir / "forged" / "input.json"
        forged_input.parent.mkdir()
        shutil.copy2(canonical_input, forged_input)
        forged_ref = "runs/LIVE-001/forged/input.json"

        descriptor_path = run_dir / "target_descriptor.json"
        descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        descriptor["inputs"]["fixture"] = forged_ref
        descriptor_bytes = _json_bytes(descriptor) + b"\n"
        descriptor_path.chmod(0o666)
        descriptor_path.write_bytes(descriptor_bytes)
        descriptor_sha = hashlib.sha256(descriptor_bytes).hexdigest()

        report_path = run_dir / "harness_report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["descriptor_sha256"] = descriptor_sha
        report_path.chmod(0o666)
        report_path.write_bytes(_json_bytes(report) + b"\n")

        trace_path = run_dir / "trace.jsonl"
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        for event in events:
            if event.get("axis") == "executed":
                event["descriptor_sha256"] = descriptor_sha
        trace_bytes = b"".join(_json_bytes(event) + b"\n" for event in events)
        trace_path.chmod(0o666)
        trace_path.write_bytes(trace_bytes)

        receipt["inputs"][0]["ref"] = forged_ref
        receipt["input"]["ref"] = forged_ref
        receipt["target"]["descriptor_sha256"] = descriptor_sha
        receipt["target"]["report"] = report
        receipt["trace"]["sha256"] = hashlib.sha256(trace_bytes).hexdigest()
        receipt["trace"]["bytes"] = len(trace_bytes)
        integrity = self.tool._snapshot_files(run_dir)
        integrity.pop("receipt.json")
        integrity.pop("projection.json")
        receipt["final_integrity_sha256"] = self.tool.canonical_sha256(integrity)
        receipt["evidence_id"] = self.tool.canonical_evidence_id(receipt)
        receipt_bytes = _json_bytes(receipt) + b"\n"

        self.assertRaises(
            self.tool.ContractError,
            self.tool.build_runtime_projection,
            receipt,
            receipt_bytes,
            run_dir,
            **self.projection_trust(),
        )

        projection = json.loads((run_dir / "projection.json").read_text(encoding="utf-8"))
        projection["evidence_id"] = receipt["evidence_id"]
        projection["proof_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
        projection["record_sha256"] = self.tool.canonical_sha256(
            projection, omit={"record_sha256"},
        )
        (run_dir / "receipt.json").chmod(0o666)
        (run_dir / "receipt.json").write_bytes(receipt_bytes)
        (run_dir / "projection.json").chmod(0o666)
        (run_dir / "projection.json").write_bytes(_json_bytes(projection) + b"\n")
        (self.evidence / "runtime_runs.jsonl").write_bytes(receipt_bytes)
        self.assertRaises(
            self.tool.ContractError,
            self.tool.export_runtime_evidence,
            self.evidence,
            **self.projection_trust(),
        )

    def test_projection_input_types_fail_closed_without_crash(self) -> None:
        receipt = self.run_valid()
        run_dir = self.evidence / "runs" / "LIVE-001"

        scenario_item = next(
            item for item in receipt["sealed_contract_inputs"]
            if item["name"] == "scenario_catalog"
        )
        catalog = self.tool._load_catalog(
            (self.evidence / scenario_item["ref"]).read_bytes(),
        )
        for malformed_inputs in (None, 7):
            with self.subTest(scenario_inputs=malformed_inputs):
                malformed_catalog = copy.deepcopy(catalog)
                malformed_row = malformed_catalog["SCN-001"]
                malformed_row["inputs"] = malformed_inputs
                malformed_row["scenario_sha256"] = self.tool.canonical_sha256(
                    malformed_row, omit={"scenario_sha256"},
                )
                malformed_receipt = copy.deepcopy(receipt)
                malformed_receipt["scenario_sha256"] = malformed_row["scenario_sha256"]
                malformed_receipt["evidence_id"] = self.tool.canonical_evidence_id(
                    malformed_receipt,
                )
                malformed_bytes = _json_bytes(malformed_receipt) + b"\n"
                with mock.patch.object(
                    self.tool, "_load_catalog", return_value=malformed_catalog,
                ):
                    with self.assertRaises(self.tool.ContractError):
                        self.tool.build_runtime_projection(
                            malformed_receipt, malformed_bytes, run_dir,
                            **self.projection_trust(),
                        )

        for malformed_name in ([], {}):
            with self.subTest(receipt_input_name=malformed_name):
                malformed_receipt = copy.deepcopy(receipt)
                malformed_receipt["inputs"][0]["name"] = malformed_name
                malformed_receipt["evidence_id"] = self.tool.canonical_evidence_id(
                    malformed_receipt,
                )
                malformed_bytes = _json_bytes(malformed_receipt) + b"\n"
                with self.assertRaises(self.tool.ContractError):
                    self.tool.build_runtime_projection(
                        malformed_receipt, malformed_bytes, run_dir,
                        **self.projection_trust(),
                    )

    def test_provenance_materialization_and_trace_type_seven_repros(self) -> None:
        receipt = self.run_valid()
        run_dir = self.evidence / "runs" / "LIVE-001"
        cases = {
            "harness-source": lambda row: row["harness"].update({
                "source": {"path": "forged.py", "git_blob": "0" * 40,
                           "sha256": "0" * 64, "commit": self.tooling_commit},
            }),
            "harness-executor": lambda row: row["harness"].update({
                "executor": {"path": "C:/forged/python.exe", "sha256": "0" * 64,
                             "version": "forged"},
            }),
            "checker-source": lambda row: row["postcondition"]["checker"].update({
                "source": {"path": "forged.py", "git_blob": "0" * 40,
                           "sha256": "0" * 64, "commit": self.tooling_commit},
            }),
            "checker-executor": lambda row: row["postcondition"]["checker"].update({
                "executor": {"path": "C:/forged/python.exe", "sha256": "0" * 64,
                             "version": "forged"},
            }),
            "materialization-audited": lambda row: row["materialization"]["audited"].update({
                "files": 999, "manifest_sha256": "0" * 64,
            }),
            "materialization-tooling": lambda row: row["materialization"]["tooling"].update({
                "files": 999, "manifest_sha256": "0" * 64,
            }),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                tampered = json.loads(json.dumps(receipt))
                mutate(tampered)
                tampered["evidence_id"] = self.tool.canonical_evidence_id(tampered)
                with self.assertRaises(self.tool.ContractError):
                    self.tool.build_runtime_projection(
                        tampered, _json_bytes(tampered) + b"\n", run_dir,
                        **self.projection_trust(),
                    )

        trace_path = run_dir / "trace.jsonl"
        events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        events[0]["axis"] = []
        trace_bytes = b"".join(_json_bytes(event) + b"\n" for event in events)
        trace_path.chmod(0o666)
        trace_path.write_bytes(trace_bytes)
        tampered = json.loads(json.dumps(receipt))
        tampered["trace"]["sha256"] = hashlib.sha256(trace_bytes).hexdigest()
        tampered["trace"]["bytes"] = len(trace_bytes)
        integrity = self.tool._snapshot_files(run_dir)
        integrity.pop("receipt.json")
        integrity.pop("projection.json")
        tampered["final_integrity_sha256"] = self.tool.canonical_sha256(integrity)
        tampered["evidence_id"] = self.tool.canonical_evidence_id(tampered)
        with self.assertRaisesRegex(self.tool.ContractError, "Trace.*Achse"):
            self.tool.build_runtime_projection(
                tampered, _json_bytes(tampered) + b"\n", run_dir,
                **self.projection_trust(),
            )

    def test_resealed_target_descriptor_outside_path_and_fake_git_identity_rejected(self) -> None:
        receipt = self.run_valid()
        run_dir = self.evidence / "runs" / "LIVE-001"
        descriptor_path = run_dir / "target_descriptor.json"
        report_path = run_dir / "harness_report.json"
        trace_path = run_dir / "trace.jsonl"
        original_descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
        original_report = json.loads(report_path.read_text(encoding="utf-8"))
        original_events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
        cases = (
            ("outside-path", {"target_path": "../outside.py"}, {}),
            ("fake-blob", {"target_git_blob": "0" * 40}, {"git_blob": "0" * 40}),
            ("fake-sha", {"target_sha256": "0" * 64}, {"sha256": "0" * 64}),
            ("fake-input", {"inputs": {"fixture": "C:/forged/input.json"}}, {}),
        )
        for label, descriptor_changes, source_changes in cases:
            with self.subTest(case=label):
                descriptor = {**original_descriptor, **descriptor_changes}
                descriptor_bytes = _json_bytes(descriptor) + b"\n"
                descriptor_path.chmod(0o666)
                descriptor_path.write_bytes(descriptor_bytes)
                descriptor_sha = hashlib.sha256(descriptor_bytes).hexdigest()

                report = {**original_report, "descriptor_sha256": descriptor_sha}
                report_bytes = _json_bytes(report) + b"\n"
                report_path.chmod(0o666)
                report_path.write_bytes(report_bytes)

                events = json.loads(json.dumps(original_events))
                for event in events:
                    if event.get("axis") == "executed":
                        event["descriptor_sha256"] = descriptor_sha
                trace_bytes = b"".join(_json_bytes(event) + b"\n" for event in events)
                trace_path.chmod(0o666)
                trace_path.write_bytes(trace_bytes)

                tampered = json.loads(json.dumps(receipt))
                tampered["target"]["descriptor_sha256"] = descriptor_sha
                tampered["target"]["report"] = report
                tampered["target"]["source"].update(source_changes)
                tampered["trace"]["sha256"] = hashlib.sha256(trace_bytes).hexdigest()
                tampered["trace"]["bytes"] = len(trace_bytes)
                integrity = self.tool._snapshot_files(run_dir)
                integrity.pop("receipt.json")
                integrity.pop("projection.json")
                tampered["final_integrity_sha256"] = self.tool.canonical_sha256(integrity)
                tampered["evidence_id"] = self.tool.canonical_evidence_id(tampered)
                with self.assertRaisesRegex(self.tool.ContractError, "Target.*(Pfad|Git|Source)"):
                    self.tool.build_runtime_projection(
                        tampered, _json_bytes(tampered) + b"\n", run_dir,
                        **self.projection_trust(),
                    )

    @unittest.skipUnless(os.name == "nt", "Windows taskkill TOCTOU contract")
    def test_timeout_process_normal_exit_between_poll_and_taskkill_twenty_times(self) -> None:
        class NearBoundaryProcess:
            pid = 424242
            def __init__(self) -> None:
                self.polls = 0
            def poll(self):
                self.polls += 1
                return None if self.polls == 1 else 0
            def kill(self) -> None:
                raise OSError("already exited")
            def wait(self, timeout: float):
                return 0
        taskkill_not_found = subprocess.CompletedProcess(
            ["taskkill"], 128, stdout=b"", stderr=b"ERROR: process not found",
        )
        with mock.patch.object(self.tool.subprocess, "run", return_value=taskkill_not_found):
            for _ in range(20):
                self.tool._kill_process_tree(NearBoundaryProcess())
            class StillLiveProcess(NearBoundaryProcess):
                def poll(self):
                    return None
                def kill(self) -> None:
                    return None
            with self.assertRaisesRegex(self.tool.ContractError, "nicht attestierbar"):
                self.tool._kill_process_tree(StillLiveProcess())
        taskkill_access_denied = subprocess.CompletedProcess(
            ["taskkill"], 5, stdout=b"", stderr=b"ERROR: access denied",
        )
        with mock.patch.object(self.tool.subprocess, "run", return_value=taskkill_access_denied):
            with self.assertRaisesRegex(self.tool.ContractError, "nicht attestierbar"):
                self.tool._kill_process_tree(NearBoundaryProcess())

    @unittest.skipUnless(os.name == "nt", "Windows Job Object timeout contract")
    def test_windows_timeout_job_kills_grandchild_after_intermediate_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pid_file = root / "grandchild.pid"
            grandchild = root / "grandchild.py"
            grandchild.write_text(
                "import os,sys,time\n"
                "from pathlib import Path\n"
                "Path(sys.argv[1]).write_text(str(os.getpid()), encoding='ascii')\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )
            intermediate = root / "intermediate.py"
            intermediate.write_text(
                "import subprocess,sys\n"
                "subprocess.Popen([sys.executable, sys.argv[1], sys.argv[2]])\n",
                encoding="utf-8",
            )
            parent = root / "parent.py"
            parent.write_text(
                "import subprocess,sys,time\n"
                "middle=subprocess.Popen([sys.executable, sys.argv[1], sys.argv[2], sys.argv[3]])\n"
                "middle.wait()\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )
            try:
                with self.assertRaisesRegex(self.tool.ContractError, "Timeout"):
                    self.tool._execute(
                        [sys.executable, str(parent), str(intermediate), str(grandchild), str(pid_file)],
                        cwd=root, timeout=5.0, environment=dict(os.environ), label="job-grandchild",
                    )
                child_pid = int(pid_file.read_text(encoding="ascii"))
                status = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {child_pid}", "/FO", "CSV", "/NH"],
                    capture_output=True, text=True, check=False,
                )
                self.assertNotIn(str(child_pid), status.stdout)
            finally:
                if pid_file.exists():
                    subprocess.run(
                        ["taskkill", "/PID", pid_file.read_text(encoding="ascii"), "/T", "/F"],
                        capture_output=True, check=False,
                    )

    @unittest.skipUnless(os.name == "nt", "Windows Job Object failure contracts")
    def test_windows_job_api_failures_are_fail_closed(self) -> None:
        kernel = mock.Mock()
        kernel.CreateJobObjectW.return_value = 0
        with mock.patch.object(self.tool, "_windows_kernel32", return_value=kernel):
            with self.assertRaisesRegex(self.tool.ContractError, "nicht erstellbar"):
                self.tool._windows_create_kill_job()

        kernel = mock.Mock()
        kernel.CreateJobObjectW.return_value = 41
        kernel.SetInformationJobObject.return_value = False
        kernel.CloseHandle.return_value = True
        with mock.patch.object(self.tool, "_windows_kernel32", return_value=kernel):
            with self.assertRaisesRegex(self.tool.ContractError, "nicht konfigurierbar"):
                self.tool._windows_create_kill_job()
        kernel.CloseHandle.assert_called_once_with(41)

        kernel = mock.Mock()
        kernel.AssignProcessToJobObject.return_value = False
        process = mock.Mock()
        process._handle = 52
        with mock.patch.object(self.tool, "_windows_kernel32", return_value=kernel):
            with self.assertRaisesRegex(self.tool.ContractError, "nicht an Job Object bindbar"):
                self.tool._windows_assign_process_to_job(41, process)

        kernel = mock.Mock()
        kernel.CreateToolhelp32Snapshot.return_value = ctypes.c_void_p(-1).value
        with mock.patch.object(self.tool, "_windows_kernel32", return_value=kernel):
            with self.assertRaisesRegex(self.tool.ContractError, "Threadsnapshot fehlgeschlagen"):
                self.tool._windows_resume_suspended_process(53)

        kernel = mock.Mock()
        kernel.QueryInformationJobObject.return_value = False
        with mock.patch.object(self.tool, "_windows_kernel32", return_value=kernel):
            with self.assertRaisesRegex(self.tool.ContractError, "nicht attestierbar"):
                self.tool._windows_job_active_processes(41)

        kernel = mock.Mock()
        kernel.TerminateJobObject.return_value = False
        with (
            mock.patch.object(self.tool, "_windows_kernel32", return_value=kernel),
            mock.patch.object(self.tool, "_windows_job_active_processes", return_value=1),
        ):
            with self.assertRaisesRegex(self.tool.ContractError, "nicht terminierbar"):
                self.tool._windows_terminate_job(41)
        with (
            mock.patch.object(self.tool, "_windows_kernel32", return_value=kernel),
            mock.patch.object(self.tool, "_windows_job_active_processes", return_value=0),
        ):
            self.tool._windows_terminate_job(41)

        kernel = mock.Mock()
        kernel.CloseHandle.return_value = False
        with mock.patch.object(self.tool, "_windows_kernel32", return_value=kernel):
            with self.assertRaisesRegex(self.tool.ContractError, "nicht schliessbar"):
                self.tool._windows_close_job(41)

    @unittest.skipUnless(os.name == "nt", "Windows suspended-process cleanup contract")
    def test_windows_setup_failure_preserves_primary_and_cleanup_errors(self) -> None:
        process = mock.Mock(pid=61)
        process._handle = 62
        process.kill.side_effect = OSError("kill denied")
        process.wait.side_effect = subprocess.TimeoutExpired("wait", 5)
        with (
            mock.patch.object(self.tool, "_windows_create_kill_job", return_value=41),
            mock.patch.object(self.tool.subprocess, "Popen", return_value=process),
            mock.patch.object(
                self.tool, "_windows_assign_process_to_job",
                side_effect=self.tool.ContractError("assign primary"),
            ),
            mock.patch.object(self.tool, "_windows_close_job") as close_job,
        ):
            with self.assertRaisesRegex(
                self.tool.ContractError,
                "assign primary; Setup-Cleanup fehlgeschlagen: kill: kill denied; wait:",
            ):
                self.tool._execute(
                    ["unused"], cwd=Path.cwd(), timeout=1,
                    environment={}, label="setup-failure",
                )
        close_job.assert_called_once_with(41)

    @unittest.skipUnless(os.name == "nt", "Windows Job Object close contract")
    def test_windows_job_close_failure_rejects_otherwise_successful_execution(self) -> None:
        process = mock.Mock(pid=71, returncode=0)
        process._handle = 72
        process.communicate.return_value = (b"out", b"")
        with (
            mock.patch.object(self.tool, "_windows_create_kill_job", return_value=41),
            mock.patch.object(self.tool.subprocess, "Popen", return_value=process),
            mock.patch.object(self.tool, "_windows_assign_process_to_job"),
            mock.patch.object(self.tool, "_windows_resume_suspended_process"),
            mock.patch.object(self.tool, "_windows_job_active_processes", return_value=0),
            mock.patch.object(
                self.tool, "_windows_close_job",
                side_effect=self.tool.ContractError("Windows Job Object nicht schliessbar"),
            ),
        ):
            with self.assertRaisesRegex(self.tool.ContractError, "nicht schliessbar"):
                self.tool._execute(
                    ["unused"], cwd=Path.cwd(), timeout=1,
                    environment={}, label="close-failure",
                )

    @unittest.skipUnless(os.name == "nt", "Windows cleanup diagnostics contract")
    def test_windows_cleanup_failures_keep_primary_error_visible(self) -> None:
        kernel = mock.Mock()
        kernel.CreateToolhelp32Snapshot.return_value = 81
        kernel.Thread32First.side_effect = self.tool.ContractError("PRIMARY enumeration failed")
        kernel.CloseHandle.return_value = False
        with mock.patch.object(self.tool, "_windows_kernel32", return_value=kernel):
            with self.assertRaisesRegex(
                self.tool.ContractError,
                "PRIMARY enumeration failed; Snapshot-Cleanup fehlgeschlagen:.*nicht schliessbar",
            ):
                self.tool._windows_resume_suspended_process(82)

        process = mock.Mock(pid=83)
        process._handle = 84
        process.communicate.side_effect = self.tool.ContractError("PRIMARY execution failed")
        with (
            mock.patch.object(self.tool, "_windows_create_kill_job", return_value=85),
            mock.patch.object(self.tool.subprocess, "Popen", return_value=process),
            mock.patch.object(self.tool, "_windows_assign_process_to_job"),
            mock.patch.object(self.tool, "_windows_resume_suspended_process"),
            mock.patch.object(
                self.tool, "_windows_close_job",
                side_effect=self.tool.ContractError("CLEANUP job close failed"),
            ),
        ):
            with self.assertRaisesRegex(
                self.tool.ContractError,
                "PRIMARY execution failed; Job-Cleanup fehlgeschlagen: CLEANUP job close failed",
            ):
                self.tool._execute(
                    ["unused"], cwd=Path.cwd(), timeout=1,
                    environment={}, label="combined-failure",
                )

    @unittest.skipUnless(os.name == "nt", "Windows interrupt cleanup contract")
    def test_windows_interrupts_keep_primary_type_and_close_handles(self) -> None:
        class RejectCleanupAttribute(KeyboardInterrupt):
            def __setattr__(self, name, value):
                if name == "_pb_audit_cleanup_error":
                    raise RuntimeError("attribute denied")
                super().__setattr__(name, value)

        rejecting = RejectCleanupAttribute("PRIMARY interrupt")
        with mock.patch.object(self.tool.sys, "stderr", new_callable=io.StringIO) as reporter_stderr:
            self.tool._report_base_cleanup_error(rejecting, "attribute cleanup")
        self.assertIn("attribute cleanup", reporter_stderr.getvalue())

        failing_stderr = mock.Mock()
        failing_stderr.write.side_effect = ValueError("stderr closed")
        reporter_primary = KeyboardInterrupt("PRIMARY interrupt")
        with mock.patch.object(self.tool.sys, "stderr", failing_stderr):
            self.tool._report_base_cleanup_error(reporter_primary, "stderr cleanup")
        self.assertEqual(str(reporter_primary), "PRIMARY interrupt")

        kernel = mock.Mock()
        kernel.CreateToolhelp32Snapshot.return_value = 91
        kernel.Thread32First.side_effect = KeyboardInterrupt("PRIMARY interrupt")
        kernel.CloseHandle.return_value = True
        with mock.patch.object(self.tool, "_windows_kernel32", return_value=kernel):
            with self.assertRaisesRegex(KeyboardInterrupt, "PRIMARY interrupt"):
                self.tool._windows_resume_suspended_process(92)
        kernel.CloseHandle.assert_called_once_with(91)

        process = mock.Mock(pid=93)
        process._handle = 94
        process.communicate.side_effect = KeyboardInterrupt("PRIMARY interrupt")
        with (
            mock.patch.object(self.tool, "_windows_create_kill_job", return_value=95),
            mock.patch.object(self.tool.subprocess, "Popen", return_value=process),
            mock.patch.object(self.tool, "_windows_assign_process_to_job"),
            mock.patch.object(self.tool, "_windows_resume_suspended_process"),
            mock.patch.object(
                self.tool, "_windows_close_job",
                side_effect=self.tool.ContractError("CLEANUP job close failed"),
            ),
            mock.patch.object(self.tool.sys, "stderr", new_callable=io.StringIO) as error_stream,
        ):
            with self.assertRaises(KeyboardInterrupt) as raised:
                self.tool._execute(
                    ["unused"], cwd=Path.cwd(), timeout=1,
                    environment={}, label="interrupt-cleanup",
                )
        self.assertEqual(str(raised.exception), "PRIMARY interrupt")
        self.assertIn(
            "CLEANUP job close failed",
            raised.exception._pb_audit_cleanup_error,
        )
        self.assertIn("CLEANUP job close failed", error_stream.getvalue())

    def test_projection_export_rejects_missing_orphan_duplicate_and_receipt_tamper(self) -> None:
        cases = ("missing", "orphan", "duplicate", "receipt-tamper")
        for case in cases:
            with self.subTest(case=case):
                try:
                    self.run_valid()
                    run_dir = self.evidence / "runs" / "LIVE-001"
                    if case == "missing":
                        projection_path = run_dir / "projection.json"
                        projection_path.chmod(0o666)
                        projection_path.unlink()
                    elif case == "orphan":
                        orphan = self.evidence / "runs" / "LIVE-ORPHAN"
                        shutil.copytree(run_dir, orphan)
                    elif case == "duplicate":
                        ledger = self.evidence / "runtime_runs.jsonl"
                        ledger.write_bytes(ledger.read_bytes() * 2)
                    else:
                        receipt_path = run_dir / "receipt.json"
                        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                        receipt["snapshot_id"] = "tampered"
                        receipt_path.chmod(0o666)
                        receipt_path.write_bytes(_json_bytes(receipt) + b"\n")
                    with self.assertRaises(self.tool.ContractError):
                        self.tool.export_runtime_evidence(self.evidence, **self.projection_trust())
                finally:
                    self.tool._remove_tree(self.evidence)
                    self.setUp()

    def test_projection_write_crash_leaves_no_published_run(self) -> None:
        original = self.tool._durable_write
        def crash_projection(path: Path, data: bytes) -> None:
            if path.name == "projection.json":
                raise OSError("projection-crash")
            original(path, data)
        with mock.patch.object(self.tool, "_durable_write", side_effect=crash_projection):
            with self.assertRaisesRegex(OSError, "projection-crash"):
                self.run_valid()
        self.assertFalse((self.evidence / "runs" / "LIVE-001").exists())
        self.assertFalse((self.evidence / "runtime_runs.jsonl").exists())

    def test_publish_failure_does_not_delete_foreign_replacement_run(self) -> None:
        stage_run = self.evidence / ".staging" / "owned-run"
        stage_run.mkdir(parents=True)
        (stage_run / "owned.txt").write_text("owned", encoding="utf-8")
        final_run = self.evidence / "runs" / "LIVE-OWNERSHIP"
        final_run.parent.mkdir()
        ledger = self.evidence / "runtime_runs.jsonl"
        ownership_token = "a" * 32
        self.tool._write_run_ownership(stage_run, "LIVE-OWNERSHIP", ownership_token)
        receipt = {
            "runtime_run_id": "LIVE-OWNERSHIP", "evidence_id": "sha256:" + "1" * 64,
            "scenario_id": "SCN-OWNERSHIP",
        }
        original_write = self.tool._durable_write

        def replace_with_foreign_then_fail(path: Path, data: bytes) -> None:
            if path.name.startswith("runtime-runs-"):
                self.tool._remove_tree(final_run)
                final_run.mkdir()
                (final_run / "foreign.txt").write_text("foreign", encoding="utf-8")
                raise OSError("ledger-publish-crash")
            original_write(path, data)

        with mock.patch.object(self.tool, "_durable_write", side_effect=replace_with_foreign_then_fail):
            with self.assertRaisesRegex(OSError, "ledger-publish-crash"):
                self.tool._publish_run_and_ledgers(
                    stage_run, final_run, ledger, receipt,
                    repo_root=self.repo,
                    expected_contract_sha256=self.expected_contract_sha256,
                    expected_authority_commit=self.authority_commit,
                    ownership_token=ownership_token,
                )
        self.assertEqual("foreign", (final_run / "foreign.txt").read_text(encoding="utf-8"))

    def test_projection_export_is_deterministic_and_atomic_failure_preserves_old_bytes(self) -> None:
        self.run_valid()
        shard = self.evidence / "runtime-evidence.jsonl"
        expected = shard.read_bytes()
        self.tool.export_runtime_evidence(self.evidence, **self.projection_trust())
        self.assertEqual(shard.read_bytes(), expected)
        original_replace = self.tool.os.replace
        def fail_shard(source: object, target: object) -> None:
            if Path(target).name == "runtime-evidence.jsonl":
                raise OSError("replace-crash")
            original_replace(source, target)
        with mock.patch.object(self.tool.os, "replace", side_effect=fail_shard):
            with self.assertRaisesRegex(OSError, "replace-crash"):
                self.tool.export_runtime_evidence(self.evidence, **self.projection_trust())
        self.assertEqual(shard.read_bytes(), expected)

    def test_missing_required_rejected(self) -> None:
        row = self.valid_scenario(); del row["postcondition"]
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"}); self.write_catalog([row]); self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "postcondition"): self.run_valid()

    def test_tampered_binding_rejected(self) -> None:
        row = self.valid_scenario(); row["audited_commit"] = "0" * 40
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"}); self.write_catalog([row]); self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "Auditvertrag"): self.run_valid()

    def test_duplicate_or_foreign_id_rejected(self) -> None:
        row = self.valid_scenario(); self.write_catalog([row, row]); self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "doppelt"): self.run_valid()
        self.write_catalog([row]); self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "unbekannt"): self.run_valid(scenario_id="SCN-X")

    def test_missing_or_tampered_artifact_rejected(self) -> None:
        row = self.valid_scenario(); row["artifacts"] = [{"name":"x","ref":"missing","required":True}]
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"}); self.write_catalog([row]); self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "Artefakt fehlt"): self.run_valid()

    def test_authority_blob_blocks_contract_substitution(self) -> None:
        original = self.expected_contract_sha256; self.write_contract(run_id="RUN-FOREIGN")
        with self.assertRaisesRegex(self.tool.ContractError, "Authority|Auditvertrag"): self.run_valid(expected_contract_sha256=original)

    def test_joint_contract_catalog_cli_and_all_ids_substitution_rejected(self) -> None:
        pinned_authority = self.authority_commit
        row = self.valid_scenario()
        row.update({
            "run_id": "RUN-FOREIGN", "snapshot_id": "snapshot-foreign",
            "audited_commit": "1" * 40, "tooling_commit": "2" * 40,
        })
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        self.write_contract(
            bind_authority=False, plan_id="PLAN-FOREIGN", run_id="RUN-FOREIGN",
            snapshot_id="snapshot-foreign", audited_commit="1" * 40, tooling_commit="2" * 40,
        )
        foreign_authority = self.write_authority_policy()
        with self.assertRaisesRegex(self.tool.ContractError, "expected_authority_commit|Authority"):
            self.run_valid(
                authority_commit=foreign_authority,
                expected_authority_commit=pinned_authority,
                expected_contract_sha256=self.expected_contract_sha256,
            )

    def test_missing_or_mismatched_external_authority_pin_rejected(self) -> None:
        with self.assertRaises(TypeError):
            self.tool.run_scenario(
                repo_root=self.repo, evidence_root=self.evidence, contract_path=self.contract_path,
                expected_contract_sha256=self.expected_contract_sha256,
                authority_commit=self.authority_commit,
                authority_policy_path="config/audit_runtime_authority_policy.json",
                scenario_id="SCN-001", runtime_run_id="LIVE-NO-PIN",
            )
        cli_without_pin = [
            "audit_runtime_evidence.py", "--root", str(self.repo),
            "--evidence-root", str(self.evidence), "--audit-contract", str(self.contract_path),
            "--expected-contract-sha256", self.expected_contract_sha256,
            "--authority-commit", self.authority_commit,
            "--scenario-id", "SCN-001", "--runtime-run-id", "LIVE-NO-CLI-PIN",
        ]
        with mock.patch.object(self.tool.sys, "argv", cli_without_pin):
            with self.assertRaisesRegex(SystemExit, "2"):
                self.tool.main()
        with self.assertRaisesRegex(self.tool.ContractError, "expected_authority_commit|Authority"):
            self.run_valid(expected_authority_commit="0" * 40)

    def test_git_replace_cannot_substitute_pinned_authority_policy(self) -> None:
        pinned_authority = self.authority_commit
        row = self.valid_scenario()
        row.update({"run_id": "RUN-FOREIGN", "snapshot_id": "snapshot-foreign"})
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        self.write_contract(
            bind_authority=False, plan_id="PLAN-FOREIGN", run_id="RUN-FOREIGN",
            snapshot_id="snapshot-foreign",
        )
        malicious_authority = self.write_authority_policy()
        subprocess.run(
            ["git", "replace", pinned_authority, malicious_authority], cwd=self.repo, check=True,
        )
        try:
            with self.assertRaisesRegex(self.tool.ContractError, "Authority-Policy|Authority"):
                self.run_valid(
                    authority_commit=pinned_authority,
                    expected_authority_commit=pinned_authority,
                    expected_contract_sha256=self.expected_contract_sha256,
                )
            self.assertFalse((self.evidence / "runs" / "LIVE-001" / "receipt.json").exists())
        finally:
            subprocess.run(["git", "replace", "-d", pinned_authority], cwd=self.repo, check=True)

    def test_wrong_authority_commit_path_blob_field_and_sha_rejected(self) -> None:
        with self.assertRaisesRegex(self.tool.ContractError, "authority_commit.*tooling_commit|Authority"):
            self.run_valid(authority_commit=self.tooling_commit)
        with self.assertRaisesRegex(self.tool.ContractError, "Policy-Pfad"):
            self.run_valid(authority_policy_path="wrong/policy.json")
        wrong_bindings = {
            "plan_id": "PLAN-WRONG", "run_id": "RUN-WRONG", "snapshot_id": "snapshot-wrong",
            "audited_commit": "1" * 40, "tooling_commit": "2" * 40,
        }
        for field, value in wrong_bindings.items():
            with self.subTest(field=field):
                bad_field_commit = self.write_authority_policy(authority_overrides={field: value})
                with self.assertRaisesRegex(self.tool.ContractError, field):
                    self.run_valid(authority_commit=bad_field_commit)
        bad_sha_commit = self.write_authority_policy(authority_overrides={"audit_contract_sha256": "0" * 64})
        with self.assertRaisesRegex(self.tool.ContractError, "audit_contract_sha256"):
            self.run_valid(authority_commit=bad_sha_commit)
        bad_blob_commit = self.write_authority_policy(authority_overrides={"unexpected": True})
        with self.assertRaisesRegex(self.tool.ContractError, "Exact-Fields"):
            self.run_valid(authority_commit=bad_blob_commit)
        with self.assertRaisesRegex(self.tool.ContractError, "getrennt"):
            self.run_valid(
                authority_commit=self.audited_commit,
                expected_authority_commit=self.audited_commit,
            )

    def test_scenario_schema_version_exact(self) -> None:
        row = self.valid_scenario(); row["schema_version"] = 2
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"}); self.write_catalog([row]); self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "schema_version"): self.run_valid()

    def test_catalog_cannot_execute_audited_scenario_directly(self) -> None:
        row = self.valid_scenario(); row["harness"] = {"root":"audited","argv":["python","scenario.py"],"cwd":"."}
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"}); self.write_catalog([row]); self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "tooling"): self.run_valid()

    def test_nonexistent_command_and_path_escape_rejected(self) -> None:
        row = self.valid_scenario(); row["harness"]["argv"][0] = "does-not-exist"
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"}); self.write_catalog([row]); self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "nicht erlaubt"): self.run_valid()
        row = self.valid_scenario(); row["target"]["path"] = "../scenario.py"
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"}); self.write_catalog([row]); self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "Pfad-Escape"): self.run_valid(runtime_run_id="LIVE-PATH")

    def test_runtime_and_scenario_reuse_rejected(self) -> None:
        self.run_valid()
        with self.assertRaisesRegex(self.tool.ContractError, "bereits"): self.run_valid()
        with self.assertRaisesRegex(self.tool.ContractError, "Evidence-Reuse"): self.run_valid(runtime_run_id="LIVE-NEW")

    def test_same_audited_tooling_commit_rejected_by_policy(self) -> None:
        self.write_contract(audited_commit=self.tooling_commit)
        with self.assertRaisesRegex(self.tool.ContractError, "gleich"): self.run_valid()

    def test_unlisted_loaded_stdlib_module_rejected(self) -> None:
        row = self.valid_scenario(script="foreign.py")
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"}); self.write_catalog([row]); self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "Modul"): self.run_valid()

    def test_symbol_runtime_claim_fails_closed_without_external_observer(self) -> None:
        row = self.valid_scenario(); row["allowed_symbol_ids"] = ["SYM-X", "SYM-Y"]
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_jsonl(self.symbol_path,[
            {"symbol_id":"SYM-X","feature_paths":["FEAT-001/main"]},
            {"symbol_id":"SYM-Y","feature_paths":["FEAT-001/main"]},
        ]); self.write_catalog([row]); self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "Symbol.*Observer"): self.run_valid()

    def test_postcondition_trace_tamper_rejected(self) -> None:
        row = self.valid_scenario(); row["postcondition"]["argv"] = ["python","tamper_checker.py","{run_dir}/trace.jsonl"]
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"}); self.write_catalog([row]); self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "Postcondition.*veraendert"): self.run_valid()

    def test_product_self_written_trace_observer_forge_rejected(self) -> None:
        row = self.valid_scenario(script="self_trace.py")
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"}); self.write_catalog([row]); self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "runner-reserviert"): self.run_valid()

    def test_input_catalog_toctou_rejected(self) -> None:
        row = self.valid_scenario(script="slow.py"); self.write_catalog([row]); self.refresh_contract()
        def mutate() -> None:
            for _ in range(3000):
                if list((self.evidence / ".staging").glob("*/sealed/inputs/*")): break
                time.sleep(0.01)
            self.input_path.write_text("changed\n"); self.catalog_path.write_text(self.catalog_path.read_text() + "\n")
        thread = threading.Thread(target=mutate); thread.start()
        with self.assertRaisesRegex(self.tool.ContractError, "TOCTOU"): self.run_valid()
        thread.join()

    def test_persistent_stale_lock_and_concurrent_different_scenarios(self) -> None:
        stale = self.evidence / ".runtime_runs.lock"; stale.write_text('{"pid":999999}\n')
        recovered = self.tool._create_ledger_lock(stale)
        self.tool._release_lock(recovered)
        self.assertEqual(stale.read_bytes(), self.tool._LOCK_SENTINEL)
        first = self.valid_scenario(script="slow.py"); second = self.valid_scenario(scenario_id="SCN-002", script="slow.py")
        second["feature_target"] = "FEAT-002/main"; second["scenario_sha256"] = self.tool.canonical_sha256(second, omit={"scenario_sha256"})
        self.write_jsonl(self.feature_path,[{"feature_id":"FEAT-001","path_id":"main"},{"feature_id":"FEAT-002","path_id":"main"}]); self.write_catalog([first,second]); self.refresh_contract()
        results: list[object] = []
        def invoke(sid: str, rid: str) -> None:
            try: results.append(self.run_valid(rid,sid))
            except Exception as exc: results.append(exc)
        threads=[threading.Thread(target=invoke,args=("SCN-001","LIVE-A")),threading.Thread(target=invoke,args=("SCN-002","LIVE-B"))]
        [thread.start() for thread in threads]; [thread.join() for thread in threads]
        self.assertEqual(2, sum(isinstance(item,dict) for item in results), results)
        for runtime_run_id in ("LIVE-A", "LIVE-B"):
            persistent = self.evidence / "runs" / f".{runtime_run_id}.lock"
            self.assertTrue(persistent.is_file())
            self.assertEqual(persistent.read_bytes(), self.tool._LOCK_SENTINEL)

    def test_runtime_lock_release_is_descriptor_bound_and_never_unlinks_replacement(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / ".runtime_runs.lock"
            first = self.tool._create_lock(path, "Ledger")
            with self.assertRaisesRegex(self.tool.ContractError, "blockiert"):
                self.tool._create_lock(path, "Ledger")
            self.tool._release_lock(first)
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_bytes(), self.tool._LOCK_SENTINEL)

            second = self.tool._create_lock(path, "Ledger")
            self.tool._release_lock(second)
            self.assertEqual(path.read_bytes(), self.tool._LOCK_SENTINEL)

            retired = root / "retired.lock"
            payload = b"owned\n"
            retired.write_bytes(self.tool._LOCK_SENTINEL + payload)
            descriptor = os.open(retired, os.O_RDWR | getattr(os, "O_BINARY", 0))
            self.assertTrue(self.tool._try_lock_descriptor(descriptor))
            replacement = root / "replacement.lock"
            replacement.write_bytes(b"FOREIGN\n")
            displaced = self.tool._OwnedRuntimeLock(
                replacement, "Ledger", descriptor, payload,
            )
            with mock.patch.object(Path, "unlink", side_effect=AssertionError("unlink forbidden")):
                with self.assertRaisesRegex(self.tool.ContractError, "Ownership geaendert"):
                    self.tool._release_lock(displaced)
            self.assertEqual(replacement.read_bytes(), b"FOREIGN\n")
            self.assertEqual(retired.read_bytes(), self.tool._LOCK_SENTINEL + payload)

            race_path = root / "race.lock"
            race_lock = self.tool._create_lock(race_path, "Ledger")
            race_retired = root / "race-retired.lock"
            if os.name == "nt":
                with self.assertRaises(PermissionError):
                    os.replace(race_path, race_retired)
                self.tool._release_lock(race_lock)
                self.assertEqual(race_path.read_bytes(), self.tool._LOCK_SENTINEL)
            else:
                real_owner = self.tool._runtime_lock_owner

                def replace_after_owner_check(lock) -> bool:
                    self.assertTrue(real_owner(lock))
                    os.replace(race_path, race_retired)
                    race_path.write_bytes(b"RACE-FOREIGN\n")
                    return True

                with mock.patch.object(
                    self.tool, "_runtime_lock_owner", side_effect=replace_after_owner_check,
                ):
                    self.tool._release_lock(race_lock)
                self.assertEqual(race_path.read_bytes(), b"RACE-FOREIGN\n")
                self.assertEqual(race_retired.read_bytes(), self.tool._LOCK_SENTINEL)

    def test_runtime_lock_cleanup_runs_all_steps_and_preserves_primary(self) -> None:
        calls: list[str] = []

        def cleanup_failure() -> None:
            calls.append("cleanup")
            raise PermissionError("cleanup denied")

        def release_failure() -> None:
            calls.append("release")
            raise self.tool.ContractError("release denied")

        primary = ValueError("PRIMARY runtime failure")

        def operation_with_failing_cleanup() -> None:
            primary_error: BaseException | None = None
            try:
                raise primary
            except BaseException as exc:
                primary_error = exc
                raise
            finally:
                self.tool._finish_cleanup(
                    primary_error,
                    [("cleanup", cleanup_failure), ("release", release_failure)],
                )

        with mock.patch.object(self.tool.sys, "stderr", new_callable=io.StringIO) as error_stream:
            with self.assertRaises(ValueError) as raised:
                operation_with_failing_cleanup()
        self.assertIs(raised.exception, primary)
        self.assertIn("cleanup denied; release: release denied", primary._pb_audit_cleanup_error)
        self.assertIn("cleanup denied; release: release denied", error_stream.getvalue())
        self.assertEqual(calls, ["cleanup", "release"])

        interrupt = KeyboardInterrupt("cleanup interrupt")

        def interrupt_cleanup() -> None:
            raise interrupt

        with self.assertRaises(KeyboardInterrupt) as raised_interrupt:
            self.tool._finish_cleanup(None, [("interrupt", interrupt_cleanup)])
        self.assertIs(raised_interrupt.exception, interrupt)

    def test_runtime_staging_cleanup_failure_still_releases_run_lock(self) -> None:
        real_remove = self.tool._remove_tree
        real_release = self.tool._release_lock
        released: list[str] = []

        def fail_only_staging(path: Path) -> None:
            if path.name.startswith("LIVE-001-"):
                raise PermissionError("staging denied")
            real_remove(path)

        def track_release(lock) -> None:
            released.append(lock.label)
            real_release(lock)

        with (
            mock.patch.object(self.tool, "_remove_tree", side_effect=fail_only_staging),
            mock.patch.object(self.tool, "_release_lock", side_effect=track_release),
            mock.patch.object(
                self.tool, "_materialize_commit",
                side_effect=self.tool.ContractError("PRIMARY materialize failure"),
            ),
            mock.patch.object(self.tool.sys, "stderr", new_callable=io.StringIO) as error_stream,
        ):
            with self.assertRaisesRegex(self.tool.ContractError, "PRIMARY materialize failure") as raised:
                self.run_valid()
        self.assertIn("Runtime-Staging-Cleanup: staging denied", raised.exception._pb_audit_cleanup_error)
        self.assertIn("Runtime-Staging-Cleanup: staging denied", error_stream.getvalue())
        self.assertIn("Runtime-Run", released)
        run_lock = self.evidence / "runs" / ".LIVE-001.lock"
        self.assertEqual(run_lock.read_bytes(), self.tool._LOCK_SENTINEL)

    def test_atomic_ledger_crash_preserves_old_bytes(self) -> None:
        ledger=self.evidence/"runtime_runs.jsonl"; old=b'{"evidence_id":"old","runtime_run_id":"old","scenario_id":"old"}\n'; ledger.write_bytes(old)
        real_replace=os.replace
        def crash(source, target):
            if Path(target).name=="runtime_runs.jsonl": raise OSError("simulated crash")
            return real_replace(source,target)
        with mock.patch.object(self.tool.os,"replace",side_effect=crash):
            with self.assertRaisesRegex(OSError,"simulated crash"): self.run_valid()
        self.assertEqual(ledger.read_bytes(),old)

    @unittest.skipUnless(os.name == "nt", "Windows process-tree contract")
    def test_timeout_kills_child_and_grandchild(self) -> None:
        row=self.valid_scenario(script="tree_timeout.py"); row["timeout_seconds"]=5.0; row["required_stdlib_modules"]=["subprocess"]
        row["scenario_sha256"]=self.tool.canonical_sha256(row,omit={"scenario_sha256"})
        self.dependency_path.write_bytes(_json_bytes({"schema_version":1,"python_version":sys.version,"stdlib_modules":["subprocess"],"modules":[]})+b"\n")
        self.write_catalog([row]); self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError,"Timeout"): self.run_valid()
        for _ in range(100):
            if self.pid_marker.exists(): break
            time.sleep(0.02)
        for pid in json.loads(self.pid_marker.read_text()):
            output=subprocess.run(["tasklist","/FI",f"PID eq {pid}","/FO","CSV","/NH"],capture_output=True,text=True).stdout
            self.assertNotIn(f'"{pid}"',output)


def _node(method: str) -> unittest.TestCase:
    return GateContractTests(method)

def test_positive_minimal() -> unittest.TestCase: return _node("test_positive_minimal")
def test_missing_required_rejected() -> unittest.TestCase: return _node("test_missing_required_rejected")
def test_tampered_binding_rejected() -> unittest.TestCase: return _node("test_tampered_binding_rejected")
def test_duplicate_or_foreign_id_rejected() -> unittest.TestCase: return _node("test_duplicate_or_foreign_id_rejected")
def test_missing_or_tampered_artifact_rejected() -> unittest.TestCase: return _node("test_missing_or_tampered_artifact_rejected")

if __name__ == "__main__":
    unittest.main()
