from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".agents/skills/pb-exhaustive-audit-ledger/scripts/verify_audit_readiness.py"
SPEC = importlib.util.spec_from_file_location("audit_readiness_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
READINESS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READINESS)


class ReadinessAuthorityContractTests(unittest.TestCase):
    @staticmethod
    def _bundle(base: Path) -> dict[str, object]:
        value = {
            key: str((base / key).resolve())
            for key in READINESS.BUNDLE_FIELDS
            - {"schema_version"}
            - READINESS.BUNDLE_SHA_FIELDS
        }
        value.update({
            "schema_version": 1,
            "expected_readiness_binding_sha256": "a" * 64,
            "expected_audit_contract_sha256": "b" * 64,
        })
        return value

    def test_non_object_manifests_fail_closed(self) -> None:
        for value in ([], 1, None):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temp:
                manifest = Path(temp) / "manifest.json"
                manifest.write_text(json.dumps(value), encoding="utf-8")
                loaded, errors = READINESS._load_readiness_manifest(manifest)
                self.assertEqual({}, loaded)
                self.assertTrue(any("Objekt" in error for error in errors), errors)

    def test_authority_pin_mismatch_stops_before_git_access(self) -> None:
        calls: list[tuple[str, ...]] = []

        def forbidden_git(_root: Path, *args: str) -> bytes:
            calls.append(args)
            raise AssertionError("Git darf vor Pinvergleich nicht gelesen werden")

        original = READINESS._git
        READINESS._git = forbidden_git
        try:
            binding, errors = READINESS._load_authority_policy(
                ROOT,
                "1" * 40,
                "2" * 40,
            )
        finally:
            READINESS._git = original
        self.assertEqual({}, binding)
        self.assertTrue(any("extern" in error or "Pin" in error for error in errors), errors)
        self.assertEqual([], calls)

    def test_missing_authority_pin_fails_closed(self) -> None:
        binding, errors = READINESS._load_authority_policy(ROOT, None, None)
        self.assertEqual({}, binding)
        self.assertTrue(errors)

    def test_reviewer_module_failures_are_returned_not_raised(self) -> None:
        sources = {
            "syntax": "def broken(:\n",
            "runtime": "raise RuntimeError('boom')\n",
            "missing_cli": "VALUE = 1\n",
            "invalid_receipt": "import json\nprint(json.dumps([]))\n",
        }
        for label, source in sources.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                materialized = Path(temp)
                tool = materialized / "tools/audit_reviewer_roster.py"
                tool.parent.mkdir(parents=True)
                tool.write_text(source, encoding="utf-8")
                errors = READINESS._run_materialized_reviewer(
                    materialized,
                    ROOT,
                    self._bundle(materialized),
                    basis_sha256="a" * 64,
                    roster_path=materialized / "roster.jsonl",
                    tooling_commit="b" * 40,
                )
            self.assertTrue(errors)

    def test_basis_binds_authority_policy_identity(self) -> None:
        manifest = {
            "run_id": "R", "tooling_commit": "1" * 40,
            "integration_head": "1" * 40, "matrix_version": 1,
            "attestation_bundle_sha256": "2" * 64,
        }
        authority = {
            "authority_commit": "3" * 40,
            "expected_authority_commit": "3" * 40,
            "policy_path": READINESS.AUTHORITY_POLICY_PATH,
            "policy_blob_oid": "4" * 40,
            "policy_sha256": "5" * 64,
        }
        first = READINESS._basis(manifest, [], "6" * 64, authority)
        changed = dict(authority)
        changed["policy_sha256"] = "7" * 64
        self.assertNotEqual(first, READINESS._basis(manifest, [], "6" * 64, changed))

    def test_real_reviewer_cli_without_provisioned_bundle_is_no_go(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            materialized = Path(temp)
            for relative in READINESS.REVIEWER_RUNTIME_PATHS:
                target = materialized / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / relative).read_bytes())
            errors = READINESS._run_materialized_reviewer(
                materialized,
                ROOT,
                self._bundle(materialized),
                basis_sha256="a" * 64,
                roster_path=materialized / "missing-roster.jsonl",
                tooling_commit=READINESS._git(ROOT, "rev-parse", "HEAD").decode().strip(),
            )
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
