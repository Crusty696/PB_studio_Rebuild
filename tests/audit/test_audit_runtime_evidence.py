from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
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


class RuntimeEvidenceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.evidence = self.root / "evidence"
        self.repo.mkdir()
        (self.evidence / "inputs").mkdir(parents=True)
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "audit@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Audit Contract"], cwd=self.repo, check=True)

        tool_target = self.repo / "tools" / "audit_runtime_evidence.py"
        tool_target.parent.mkdir()
        shutil.copy2(TOOL_PATH, tool_target)
        (self.repo / "scenario.py").write_text(
            "from pathlib import Path\n"
            "import json, os\n"
            "run_dir = Path(os.environ['PB_AUDIT_RUN_DIR'])\n"
            "trace = Path(os.environ['PB_AUDIT_TRACE_PATH'])\n"
            "(run_dir / 'artifact.txt').write_text('result\\n', encoding='utf-8')\n"
            "trace.write_text(json.dumps({'feature_path':'FEAT-001/main','symbol_id':'SYM-scenario:main','axis':'executed','event':'entered'}) + '\\n' + json.dumps({'feature_path':'FEAT-001/main','symbol_id':'SYM-scenario:main','axis':'result','event':'result'}) + '\\n' + json.dumps({'feature_path':'FEAT-001/main','symbol_id':'SYM-scenario:main','axis':'live_evidence','event':'observed'}) + '\\n', encoding='utf-8')\n"
            "print('scenario-ok')\n",
            encoding="utf-8",
        )
        (self.repo / "checker.py").write_text(
            "from pathlib import Path\nimport sys\nraise SystemExit(0 if Path(sys.argv[1]).read_text(encoding='utf-8') == 'result\\n' else 3)\n",
            encoding="utf-8",
        )
        (self.repo / "sleep.py").write_text(
            "import time\ntime.sleep(10)\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "tools/audit_runtime_evidence.py", "scenario.py", "checker.py", "sleep.py"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.repo, check=True)
        self.commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=self.repo, check=True, capture_output=True, text=True
        ).stdout.strip()
        self.input_path = self.evidence / "inputs" / "input.json"
        self.input_path.write_text('{"fixture":true}\n', encoding="utf-8")
        self.tool = _load_tool()
        self.catalog_path = self.evidence / "scenario_catalog.jsonl"
        self.write_catalog([self.valid_scenario()])

    def tearDown(self) -> None:
        self.temp.cleanup()

    def valid_scenario(self) -> dict:
        row = {
            "schema_version": 1,
            "run_id": "RUN-001",
            "scenario_id": "SCN-001",
            "audited_commit": self.commit,
            "tooling_commit": self.commit,
            "snapshot_id": "snapshot-001",
            "feature_target": "FEAT-001/main",
            "command": {"argv": ["python", "scenario.py"], "cwd": "."},
            "timeout_seconds": 5.0,
            "inputs": [{"name": "fixture", "ref": "inputs/input.json", "sha256": _sha(self.input_path)}],
            "allowed_symbol_ids": ["SYM-scenario:main"],
            "allowed_axes": ["executed", "result", "live_evidence"],
            "postcondition": {
                "argv": ["python", "checker.py", "{run_dir}/artifact.txt"],
                "cwd": ".",
                "timeout_seconds": 5.0,
            },
            "artifacts": [{"name": "result", "ref": "artifact.txt", "required": True}],
        }
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        return row

    def write_catalog(self, rows: list[dict]) -> None:
        self.catalog_path.write_text(
            "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows),
            encoding="utf-8",
        )

    def run_valid(self, runtime_run_id: str = "LIVE-001") -> dict:
        return self.tool.run_scenario(
            repo_root=self.repo,
            evidence_root=self.evidence,
            catalog_path=self.catalog_path,
            scenario_id="SCN-001",
            runtime_run_id=runtime_run_id,
        )

    def test_positive_minimal(self) -> None:
        receipt = self.run_valid()
        self.assertEqual(receipt["covered_feature_paths"], ["FEAT-001/main"])
        self.assertEqual(receipt["covered_symbol_ids"], ["SYM-scenario:main"])
        self.assertEqual(receipt["covered_axes"], ["executed", "live_evidence", "result"])
        self.assertEqual(receipt["exit"]["code"], 0)
        self.assertEqual(receipt["postcondition"]["result"], "pass")
        self.assertEqual(receipt["command"]["source"]["path"], "scenario.py")
        self.assertRegex(receipt["command"]["source"]["git_blob"], r"^[0-9a-f]{40}$")
        self.assertEqual(receipt["postcondition"]["checker"]["source"]["path"], "checker.py")
        self.assertEqual(receipt["runner"]["tooling_commit"], self.commit)
        self.assertTrue(receipt["evidence_id"].startswith("sha256:"))
        self.assertEqual(receipt["evidence_id"], self.tool.canonical_evidence_id(receipt))
        for section in ("stdout", "stderr", "trace", "postcondition"):
            ref = receipt[section]["ref"]
            self.assertEqual(receipt[section]["sha256"], _sha(self.evidence / ref))

    def test_missing_required_rejected(self) -> None:
        row = self.valid_scenario()
        del row["postcondition"]
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        with self.assertRaisesRegex(self.tool.ContractError, "postcondition"):
            self.run_valid()

    def test_tampered_binding_rejected(self) -> None:
        row = self.valid_scenario()
        row["audited_commit"] = "0" * 40
        self.write_catalog([row])
        with self.assertRaisesRegex(self.tool.ContractError, "scenario_sha256"):
            self.run_valid()

    def test_duplicate_or_foreign_id_rejected(self) -> None:
        row = self.valid_scenario()
        self.write_catalog([row, row])
        with self.assertRaisesRegex(self.tool.ContractError, "doppelt"):
            self.run_valid()
        self.write_catalog([row])
        with self.assertRaisesRegex(self.tool.ContractError, "unbekannt"):
            self.tool.run_scenario(
                repo_root=self.repo,
                evidence_root=self.evidence,
                catalog_path=self.catalog_path,
                scenario_id="SCN-FOREIGN",
                runtime_run_id="LIVE-X",
            )

    def test_missing_or_tampered_artifact_rejected(self) -> None:
        row = self.valid_scenario()
        row["artifacts"] = [{"name": "missing", "ref": "missing.bin", "required": True}]
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        with self.assertRaisesRegex(self.tool.ContractError, "Artefakt fehlt"):
            self.run_valid()

        row = self.valid_scenario()
        row["inputs"][0]["sha256"] = "f" * 64
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        with self.assertRaisesRegex(self.tool.ContractError, "Input-Hash"):
            self.run_valid("LIVE-002")

    def test_nonexistent_command_rejected(self) -> None:
        row = self.valid_scenario()
        row["command"]["argv"] = ["does-not-exist", "scenario.py"]
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        with self.assertRaisesRegex(self.tool.ContractError, "nicht erlaubt"):
            self.run_valid()

    def test_runtime_run_id_cannot_be_reused(self) -> None:
        self.run_valid()
        with self.assertRaisesRegex(self.tool.ContractError, "bereits vorhanden"):
            self.run_valid()

    def test_timeout_is_fail_closed_and_cleans_staging(self) -> None:
        row = self.valid_scenario()
        row["command"]["argv"] = ["python", "sleep.py"]
        row["timeout_seconds"] = 0.1
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        with self.assertRaisesRegex(self.tool.ContractError, "Timeout"):
            self.run_valid()
        self.assertFalse((self.evidence / "runs" / "LIVE-001").exists())
        self.assertEqual(list((self.evidence / ".staging").glob("LIVE-001-*")), [])

    def test_path_escape_rejected(self) -> None:
        row = self.valid_scenario()
        row["command"]["cwd"] = "../outside"
        row["scenario_sha256"] = self.tool.canonical_sha256(row, omit={"scenario_sha256"})
        self.write_catalog([row])
        with self.assertRaisesRegex(self.tool.ContractError, "cwd.*ausserhalb"):
            self.run_valid()


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
