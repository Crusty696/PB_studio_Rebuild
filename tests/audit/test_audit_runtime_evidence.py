from __future__ import annotations

import hashlib
import importlib.util
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

HARNESS = r'''import hashlib,json,runpy,sys,time,pkgutil,typing,weakref,_weakrefset
from pathlib import Path
descriptor_path, report_path = map(Path, sys.argv[1:3])
descriptor_bytes = descriptor_path.read_bytes()
descriptor = json.loads(descriptor_bytes)
before = set(sys.modules)
started = time.time_ns()
exit_code = 0
try:
    runpy.run_path(descriptor["target_path"], run_name="__main__")
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
        subprocess.run(["git", "add", "scenario.py", "foreign.py", "slow.py", "self_trace.py", "tree_timeout.py", ".gitattributes"], cwd=cls.repo, check=True)
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
        row = self.valid_scenario(); row["allowed_symbol_ids"] = ["SYM-X"]
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_jsonl(self.symbol_path,[{"symbol_id":"SYM-X","feature_paths":["FEAT-001/main"]}]); self.write_catalog([row]); self.refresh_contract()
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

    def test_stale_lock_and_concurrent_different_scenarios(self) -> None:
        stale = self.evidence / ".runtime_runs.lock"; stale.write_text('{"pid":999999}\n')
        with self.assertRaisesRegex(self.tool.ContractError, "Lock.*manuell"): self.run_valid()
        stale.unlink()
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
