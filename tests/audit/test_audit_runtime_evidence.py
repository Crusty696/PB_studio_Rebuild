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


EMITTER = r'''from pathlib import Path
import os
run_dir = Path(os.environ["PB_AUDIT_RUN_DIR"])
(run_dir / "artifact.txt").write_text("result\n", encoding="utf-8")
print("scenario-ok")
'''


class RuntimeEvidenceContractTests(unittest.TestCase):
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
        (cls.repo / "slow.py").write_text("import time\ntime.sleep(0.6)\n" + EMITTER, encoding="utf-8")
        (cls.repo / "self_trace.py").write_text(
            "from pathlib import Path\nimport os\n"
            "Path(os.environ['PB_AUDIT_RUN_DIR'],'trace.jsonl').write_text('{}\\n')\n" + EMITTER,
            encoding="utf-8",
        )
        (cls.repo / "ui_generic.py").write_text(EMITTER, encoding="utf-8")
        cls.pid_marker = cls.base / "tree-pids.json"
        (cls.repo / "tree_timeout.py").write_text(
            "import subprocess, sys, time\n"
            f"marker={str(cls.pid_marker)!r}\n"
            "grand='import time; time.sleep(60)'\n"
            "child='import json,os,subprocess,sys,time; p=subprocess.Popen([sys.executable,\"-c\",sys.argv[2]]); f=open(sys.argv[1],\"w\"); f.write(json.dumps([os.getpid(),p.pid])); f.flush(); f.close(); time.sleep(60)'\n"
            "subprocess.Popen([sys.executable,'-c',child,marker,grand])\n"
            "time.sleep(60)\n",
            encoding="utf-8",
        )
        (cls.repo / ".gitattributes").write_text("scenario.py filter=evil\n", encoding="utf-8")
        subprocess.run(
            ["git", "add", "scenario.py", "slow.py", "self_trace.py", "ui_generic.py", "tree_timeout.py", ".gitattributes"],
            cwd=cls.repo, check=True,
        )
        subprocess.run(["git", "commit", "-qm", "audited product"], cwd=cls.repo, check=True)
        cls.audited_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cls.repo, check=True, capture_output=True, text=True
        ).stdout.strip()

        tool_target = cls.repo / "tools" / "audit_runtime_evidence.py"
        tool_target.parent.mkdir()
        shutil.copy2(TOOL_PATH, tool_target)
        (cls.repo / "checker.py").write_text(
            "from pathlib import Path\nimport sys\n"
            "raise SystemExit(0 if Path(sys.argv[1]).read_text(encoding='utf-8') == 'result\\n' else 3)\n",
            encoding="utf-8",
        )
        (cls.repo / "tamper_checker.py").write_text(
            "from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_text('{}\\n', encoding='utf-8')\n",
            encoding="utf-8",
        )
        subprocess.run(
            ["git", "add", "tools/audit_runtime_evidence.py", "checker.py", "tamper_checker.py"], cwd=cls.repo, check=True
        )
        subprocess.run(["git", "commit", "-qm", "tooling harness"], cwd=cls.repo, check=True)
        cls.tooling_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=cls.repo, check=True, capture_output=True, text=True
        ).stdout.strip()
        cls.tool = _load_tool()

        evil = cls.base / "evil_filter.py"
        evil.write_text("import sys\nsys.stdin.buffer.read()\nsys.stdout.write('raise SystemExit(91)\\n')\n", encoding="utf-8")
        subprocess.run(
            ["git", "config", "filter.evil.smudge", f'"{sys.executable}" "{evil}"'], cwd=cls.repo, check=True
        )
        subprocess.run(["git", "config", "filter.evil.clean", "cat"], cwd=cls.repo, check=True)

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
        self.feature_rows = [{"feature_id": "FEAT-001", "path_id": "main"}]
        self.symbol_rows = [{"symbol_id": "SYM-scenario:main", "feature_paths": ["FEAT-001/main"]}]
        self.write_jsonl(self.feature_path, self.feature_rows)
        self.write_jsonl(self.symbol_path, self.symbol_rows)
        self.executor_path.write_bytes(_json_bytes({
            "python": {"path": sys.executable, "sha256": _sha(Path(sys.executable)), "version": sys.version}
        }) + b"\n")
        self.dependency_path.write_bytes(_json_bytes({"python_version": sys.version, "modules": []}) + b"\n")
        self.write_catalog([self.valid_scenario()])
        self.write_contract()

    def tearDown(self) -> None:
        shutil.rmtree(self.evidence, ignore_errors=True)
        self.pid_marker.unlink(missing_ok=True)

    def write_jsonl(self, path: Path, rows: list[dict]) -> None:
        path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")

    def valid_scenario(self, *, scenario_id: str = "SCN-001", script: str = "scenario.py") -> dict:
        row = {
            "schema_version": 2,
            "run_id": "RUN-001",
            "scenario_id": scenario_id,
            "audited_commit": self.audited_commit,
            "tooling_commit": self.tooling_commit,
            "snapshot_id": "snapshot-001",
            "feature_target": "FEAT-001/main",
            "command": {"root": "audited", "argv": ["python", script], "cwd": "."},
            "timeout_seconds": 5.0,
            "inputs": [{"name": "fixture", "ref": "inputs/input.json", "sha256": _sha(self.input_path)}],
            "allowed_symbol_ids": ["SYM-scenario:main"],
            "symbol_probes": [{"symbol_id": "SYM-scenario:main", "path": script, "function": "<module>"}],
            "allowed_axes": ["executed", "result", "live_evidence"],
            "required_modules": [],
            "postcondition": {
                "root": "tooling", "argv": ["python", "checker.py", "{run_dir}/artifact.txt"],
                "cwd": ".", "timeout_seconds": 5.0,
            },
            "artifacts": [{"name": "result", "ref": "artifact.txt", "required": True}],
        }
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        return row

    def write_catalog(self, rows: list[dict]) -> None:
        self.write_jsonl(self.catalog_path, rows)

    def write_contract(self, **overrides: object) -> None:
        contract = {
            "schema_version": 1,
            "run_id": "RUN-001",
            "snapshot_id": "snapshot-001",
            "audited_commit": self.audited_commit,
            "tooling_commit": self.tooling_commit,
            "scenario_catalog": {"ref": "scenario_catalog.jsonl", "sha256": _sha(self.catalog_path)},
            "feature_universe": {"ref": "features.jsonl", "sha256": _sha(self.feature_path)},
            "symbol_universe": {"ref": "symbols.jsonl", "sha256": _sha(self.symbol_path)},
            "executor_manifest": {"ref": "executors.json", "sha256": _sha(self.executor_path)},
            "dependency_manifest": {"ref": "dependencies.json", "sha256": _sha(self.dependency_path)},
        }
        contract.update(overrides)
        self.contract_path.write_bytes(_json_bytes(contract) + b"\n")

    def refresh_contract(self) -> None:
        self.write_contract()

    def run_valid(self, runtime_run_id: str = "LIVE-001", scenario_id: str = "SCN-001") -> dict:
        return self.tool.run_scenario(
            repo_root=self.repo,
            evidence_root=self.evidence,
            contract_path=self.contract_path,
            scenario_id=scenario_id,
            runtime_run_id=runtime_run_id,
        )

    def test_positive_minimal(self) -> None:
        receipt = self.run_valid()
        self.assertEqual(receipt["covered_feature_paths"], ["FEAT-001/main"])
        self.assertEqual(receipt["covered_symbol_ids"], ["SYM-scenario:main"])
        self.assertEqual(receipt["covered_axes"], ["executed", "live_evidence", "result"])
        self.assertEqual(receipt["exit"]["code"], 0)
        self.assertEqual(receipt["postcondition"]["result"], "pass")
        self.assertEqual(receipt["evidence_id"], self.tool.canonical_evidence_id(receipt))
        self.assertEqual(receipt["command"]["source"]["commit"], self.audited_commit)
        self.assertEqual(receipt["postcondition"]["checker"]["source"]["commit"], self.tooling_commit)
        self.assertNotEqual(self.audited_commit, self.tooling_commit)
        self.assertEqual(receipt["runner"]["tooling_commit"], self.tooling_commit)
        self.assertTrue(receipt["observer"]["nonce_bound"])
        self.assertTrue(receipt["environment"]["python_no_user_site"])
        self.assertIn(b"scenario-ok", (self.evidence / receipt["stdout"]["ref"]).read_bytes())

    def test_missing_required_rejected(self) -> None:
        row = self.valid_scenario()
        del row["postcondition"]
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "postcondition"):
            self.run_valid()

    def test_tampered_binding_rejected(self) -> None:
        row = self.valid_scenario()
        row["audited_commit"] = "0" * 40
        self.write_catalog([row])
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "scenario_sha256"):
            self.run_valid()

    def test_recomputed_foreign_binding_rejected_by_external_contract(self) -> None:
        row = self.valid_scenario()
        row["audited_commit"] = self.tooling_commit
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "Auditvertrag"):
            self.run_valid()

    def test_duplicate_or_foreign_id_rejected(self) -> None:
        row = self.valid_scenario()
        self.write_catalog([row, row])
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "doppelt"):
            self.run_valid()
        self.write_catalog([row])
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "unbekannt"):
            self.run_valid(scenario_id="SCN-FOREIGN")

    def test_missing_or_tampered_artifact_rejected(self) -> None:
        row = self.valid_scenario()
        row["artifacts"] = [{"name": "missing", "ref": "missing.bin", "required": True}]
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "Artefakt fehlt"):
            self.run_valid()
        row = self.valid_scenario()
        row["inputs"][0]["sha256"] = "f" * 64
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "Input-Hash"):
            self.run_valid("LIVE-002")

    def test_checkout_filter_cannot_overwrite_materialized_product_blob(self) -> None:
        receipt = self.run_valid()
        self.assertEqual(receipt["materialization"]["method"], "git-cat-file")
        self.assertIn(b"scenario-ok", (self.evidence / receipt["stdout"]["ref"]).read_bytes())

    def test_postcondition_cannot_mutate_trace_or_evidence(self) -> None:
        row = self.valid_scenario()
        row["postcondition"]["argv"] = ["python", "tamper_checker.py", "{run_dir}/trace.jsonl"]
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "Postcondition.*veraendert"):
            self.run_valid()

    def test_input_and_catalog_toctou_rejected(self) -> None:
        row = self.valid_scenario(script="slow.py")
        self.write_catalog([row])
        self.refresh_contract()
        def mutate() -> None:
            for _ in range(3000):
                if list((self.evidence / ".staging").glob("*/sealed/inputs/fixture.json")):
                    break
                time.sleep(0.01)
            self.input_path.write_text("mutated\n", encoding="utf-8")
            self.catalog_path.write_text(self.catalog_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        thread = threading.Thread(target=mutate)
        thread.start()
        with self.assertRaisesRegex(self.tool.ContractError, "TOCTOU"):
            self.run_valid()
        thread.join()

    def test_self_written_trace_is_rejected(self) -> None:
        row = self.valid_scenario(script="self_trace.py")
        self.write_catalog([row])
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "runner-reserviert"):
            self.run_valid()

    def test_duplicate_semantic_target_and_cross_feature_symbol_rejected(self) -> None:
        first = self.valid_scenario()
        second = self.valid_scenario(scenario_id="SCN-002")
        self.write_catalog([first, second])
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "semantisches Ziel doppelt"):
            self.run_valid()
        self.write_catalog([first])
        self.feature_rows.append({"feature_id": "FEAT-UNCLAIMED", "path_id": "main"})
        self.write_jsonl(self.feature_path, self.feature_rows)
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "Exact-Set"):
            self.run_valid("LIVE-002")
        self.feature_rows.pop()
        self.write_jsonl(self.feature_path, self.feature_rows)
        self.symbol_rows[0]["feature_paths"] = ["FEAT-OTHER/main"]
        self.write_jsonl(self.symbol_path, self.symbol_rows)
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "Symbol.*(Featuretarget|Featurepfade)"):
            self.run_valid("LIVE-003")

    def test_executor_and_dependency_manifests_are_enforced(self) -> None:
        manifest = json.loads(self.executor_path.read_text(encoding="utf-8"))
        manifest["python"]["sha256"] = "0" * 64
        self.executor_path.write_bytes(_json_bytes(manifest) + b"\n")
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "Executor python"):
            self.run_valid()

        self.executor_path.write_bytes(_json_bytes({
            "python": {"path": sys.executable, "sha256": _sha(Path(sys.executable)), "version": sys.version}
        }) + b"\n")
        row = self.valid_scenario()
        row["required_modules"] = ["not-installed-pb-audit-module"]
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "required_modules"):
            self.run_valid("LIVE-002")

    def test_nonexistent_command_and_path_escape_rejected(self) -> None:
        row = self.valid_scenario()
        row["command"]["argv"] = ["does-not-exist", "scenario.py"]
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "nicht erlaubt"):
            self.run_valid()
        row = self.valid_scenario()
        row["command"]["cwd"] = "../outside"
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "cwd.*ausserhalb"):
            self.run_valid("LIVE-002")

    def test_ui_db_gpu_require_observer_specific_events(self) -> None:
        row = self.valid_scenario(script="ui_generic.py")
        row["allowed_axes"] = ["UI"]
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "UI.*Observer"):
            self.run_valid()

    def test_runtime_run_id_reuse_concurrent_and_stale_lock_rejected(self) -> None:
        stale = self.evidence / ".runtime_runs.lock"
        stale.write_text('{"pid":999999,"created_ns":1}\n', encoding="utf-8")
        with self.assertRaisesRegex(self.tool.ContractError, "Lock.*manuell"):
            self.run_valid()
        stale.unlink()
        row = self.valid_scenario(script="slow.py")
        self.write_catalog([row])
        self.refresh_contract()
        result: list[object] = []
        def first() -> None:
            try:
                result.append(self.run_valid())
            except Exception as exc:
                result.append(exc)
        thread = threading.Thread(target=first)
        thread.start()
        lock = self.evidence / "runs" / ".LIVE-001.lock"
        for _ in range(100):
            if lock.exists():
                break
            time.sleep(0.01)
        with self.assertRaisesRegex(self.tool.ContractError, "bereits|Lock existiert"):
            self.run_valid()
        thread.join()
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], dict)
        with self.assertRaisesRegex(self.tool.ContractError, "bereits"):
            self.run_valid()
        with self.assertRaisesRegex(self.tool.ContractError, "Evidence-Reuse"):
            self.run_valid("LIVE-002")

    @unittest.skipUnless(os.name == "nt", "taskkill /T-Vertrag ist Windows-spezifisch")
    def test_timeout_kills_child_and_grandchild(self) -> None:
        row = self.valid_scenario(script="tree_timeout.py")
        row["timeout_seconds"] = 10.0
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        self.refresh_contract()
        with self.assertRaisesRegex(self.tool.ContractError, "Timeout"):
            self.run_valid()
        for _ in range(100):
            if self.pid_marker.exists():
                break
            time.sleep(0.02)
        pids = json.loads(self.pid_marker.read_text(encoding="utf-8"))
        time.sleep(0.3)
        for pid in pids:
            output = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, check=False,
            ).stdout
            self.assertNotIn(f'"{pid}"', output, output)


def _node(method: str) -> unittest.TestCase:
    return RuntimeEvidenceContractTests(method)


def test_positive_minimal() -> unittest.TestCase:
    return _node("test_positive_minimal")


def test_missing_required_rejected() -> unittest.TestCase:
    return _node("test_missing_required_rejected")


def test_tampered_binding_rejected() -> unittest.TestCase:
    return _node("test_tampered_binding_rejected")


def test_duplicate_or_foreign_id_rejected() -> unittest.TestCase:
    return _node("test_duplicate_or_foreign_id_rejected")


def test_missing_or_tampered_artifact_rejected() -> unittest.TestCase:
    return _node("test_missing_or_tampered_artifact_rejected")


if __name__ == "__main__":
    unittest.main()
