from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


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

    def test_artifact_rows_reject_hostile_types_at_cli_boundary(self) -> None:
        commit = "1" * 40
        authority = {
            "authority_commit": "2" * 40,
            "expected_authority_commit": "2" * 40,
            "tooling_commit": commit,
            "policy_path": READINESS.AUTHORITY_POLICY_PATH,
            "policy_blob_oid": "3" * 40,
            "policy_sha256": "4" * 64,
            "artifacts": {},
        }
        valid_row = {
            "run_id": "RUN-B859",
            "tooling_commit": commit,
            "path": sorted(READINESS.REQUIRED_ARTIFACTS)[0],
            "bytes": 0,
            "sha256": "7" * 64,
        }
        hostile_rows = (
            ("unhashable-path", {**valid_row, "path": {}}),
            ("non-object-row", 1),
            ("structured-run-id", {**valid_row, "run_id": {}}),
            ("structured-tooling-commit", {**valid_row, "tooling_commit": []}),
            ("structured-sha256", {**valid_row, "sha256": {}}),
            ("boolean-bytes", {**valid_row, "bytes": True}),
            ("negative-bytes", {**valid_row, "bytes": -1}),
        )
        for label, row in hostile_rows:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                manifest_path = base / "readiness.json"
                manifest = {
                    "schema_version": 3,
                    "plan_id": READINESS.PLAN_ID,
                    "run_id": "RUN-B859",
                    "tooling_commit": commit,
                    "integration_head": commit,
                    "matrix_version": 1,
                    "artifacts": [row],
                    "reviewer_roster_path": str((base / "roster.jsonl").resolve()),
                    "reviewer_roster_sha256": "5" * 64,
                    "attestation_bundle_path": str((base / "bundle.json").resolve()),
                    "attestation_bundle_sha256": "6" * 64,
                }
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                before = {path.name: path.read_bytes() for path in base.iterdir()}
                stdout = io.StringIO()
                stderr = io.StringIO()

                def fake_git(_root: Path, *args: str) -> bytes:
                    if args[0] != "rev-parse":
                        raise AssertionError(f"unerwarteter Git-Zugriff: {args}")
                    return f"{commit}\n".encode()

                argv = [
                    str(SCRIPT),
                    "--root", str(ROOT),
                    "--manifest", str(manifest_path),
                    "--authority-commit", authority["authority_commit"],
                    "--expected-authority-commit", authority["expected_authority_commit"],
                ]
                with (
                    patch.object(sys, "argv", argv),
                    patch.object(READINESS, "_load_authority_policy", return_value=(authority, [])),
                    patch.object(READINESS, "_git", side_effect=fake_git),
                    patch.object(READINESS, "_load_bundle_manifest", return_value=({}, [])) as bundle_loader,
                    patch.object(
                        READINESS, "_basis",
                        side_effect=AssertionError("_basis darf bei ungueltiger Artefaktzeile nicht laufen"),
                    ) as basis,
                    patch.object(READINESS, "_run_gates") as gates,
                    patch.object(READINESS, "_verify_attestation_bundle") as bundle,
                    redirect_stdout(stdout),
                    redirect_stderr(stderr),
                ):
                    exit_code = READINESS.main()

                self.assertEqual(2, exit_code)
                self.assertEqual("ERROR: Artefaktzeile ungueltig/fremd\n", stdout.getvalue())
                self.assertEqual("", stderr.getvalue())
                self.assertEqual(before, {path.name: path.read_bytes() for path in base.iterdir()})
                bundle_loader.assert_not_called()
                basis.assert_not_called()
                gates.assert_not_called()
                bundle.assert_not_called()

    def test_artifact_exact_set_and_valid_rows_remain_controlled(self) -> None:
        commit = "1" * 40
        run_id = "RUN-B859"
        authority = {
            "authority_commit": "2" * 40,
            "expected_authority_commit": "2" * 40,
            "tooling_commit": commit,
            "policy_path": READINESS.AUTHORITY_POLICY_PATH,
            "policy_blob_oid": "3" * 40,
            "policy_sha256": "4" * 64,
            "artifacts": {},
        }
        artifact_bytes = {
            path: f"artifact:{path}\n".encode()
            for path in READINESS.REQUIRED_ARTIFACTS
        }
        valid_rows = [
            {
                "run_id": run_id,
                "tooling_commit": commit,
                "path": path,
                "bytes": len(artifact_bytes[path]),
                "sha256": READINESS._sha(artifact_bytes[path]),
            }
            for path in sorted(READINESS.REQUIRED_ARTIFACTS)
        ]

        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            roster = base / "roster.jsonl"
            roster.write_bytes(b"reviewer\n")

            def run(rows: list[object], name: str) -> list[str]:
                manifest_path = base / f"{name}.json"
                manifest = {
                    "schema_version": 3,
                    "plan_id": READINESS.PLAN_ID,
                    "run_id": run_id,
                    "tooling_commit": commit,
                    "integration_head": commit,
                    "matrix_version": 1,
                    "artifacts": rows,
                    "reviewer_roster_path": str(roster.resolve()),
                    "reviewer_roster_sha256": READINESS._sha(roster.read_bytes()),
                    "attestation_bundle_path": str((base / "bundle.json").resolve()),
                    "attestation_bundle_sha256": "6" * 64,
                }
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

                def fake_git(_root: Path, *args: str) -> bytes:
                    if args[0] == "rev-parse":
                        return f"{commit}\n".encode()
                    if args[0] == "show":
                        path = args[1].split(":", 1)[1]
                        return artifact_bytes[path]
                    raise AssertionError(f"unerwarteter Git-Zugriff: {args}")

                with (
                    patch.object(READINESS, "_load_authority_policy", return_value=(authority, [])),
                    patch.object(READINESS, "_git", side_effect=fake_git),
                    patch.object(READINESS, "_load_bundle_manifest", return_value=({}, [])),
                    patch.object(READINESS, "_run_gates", return_value=[]),
                    patch.object(READINESS, "_verify_attestation_bundle", return_value=[]),
                ):
                    return READINESS.verify_readiness(
                        ROOT,
                        manifest_path,
                        authority_commit=authority["authority_commit"],
                        expected_authority_commit=authority["expected_authority_commit"],
                    )

            self.assertEqual([], run(valid_rows, "valid"))
            cases = (
                (
                    "missing",
                    valid_rows[:-1],
                    ["Artefaktmenge entspricht nicht exakt Phase-minus-1-Vertrag"],
                ),
                (
                    "duplicate",
                    [*valid_rows, dict(valid_rows[0])],
                    ["Artefaktmenge entspricht nicht exakt Phase-minus-1-Vertrag"],
                ),
                (
                    "foreign",
                    [{**valid_rows[0], "path": "foreign.py"}],
                    ["Artefaktzeile ungueltig/fremd"],
                ),
            )
            for label, rows, expected in cases:
                with self.subTest(label=label):
                    self.assertEqual(expected, run(rows, label))

    def test_cli_uses_single_verified_manifest_and_authority_snapshot(self) -> None:
        commit = "1" * 40
        run_id = "RUN-B859-SNAPSHOT"
        authority = {
            "authority_commit": "2" * 40,
            "expected_authority_commit": "2" * 40,
            "tooling_commit": commit,
            "policy_path": READINESS.AUTHORITY_POLICY_PATH,
            "policy_blob_oid": "3" * 40,
            "policy_sha256": "4" * 64,
            "artifacts": {},
        }
        artifact_bytes = {
            path: f"artifact:{path}\n".encode()
            for path in READINESS.REQUIRED_ARTIFACTS
        }
        rows = [
            {
                "run_id": run_id,
                "tooling_commit": commit,
                "path": path,
                "bytes": len(artifact_bytes[path]),
                "sha256": READINESS._sha(artifact_bytes[path]),
            }
            for path in sorted(READINESS.REQUIRED_ARTIFACTS)
        ]

        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            roster = base / "roster.jsonl"
            roster.write_bytes(b"reviewer\n")
            manifest_path = base / "readiness.json"
            manifest = {
                "schema_version": 3,
                "plan_id": READINESS.PLAN_ID,
                "run_id": run_id,
                "tooling_commit": commit,
                "integration_head": commit,
                "matrix_version": 1,
                "artifacts": rows,
                "reviewer_roster_path": str(roster.resolve()),
                "reviewer_roster_sha256": READINESS._sha(roster.read_bytes()),
                "attestation_bundle_path": str((base / "bundle.json").resolve()),
                "attestation_bundle_sha256": "6" * 64,
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            expected_basis = READINESS._basis(
                manifest, rows, manifest["reviewer_roster_sha256"], authority,
            )
            real_load = READINESS._load_readiness_manifest

            def load_then_replace(path: Path) -> tuple[dict, list[str]]:
                loaded, errors = real_load(path)
                hostile = {**manifest, "artifacts": [1]}
                path.write_text(json.dumps(hostile), encoding="utf-8")
                return loaded, errors

            def fake_git(_root: Path, *args: str) -> bytes:
                if args[0] == "rev-parse":
                    return f"{commit}\n".encode()
                if args[0] == "show":
                    path = args[1].split(":", 1)[1]
                    return artifact_bytes[path]
                raise AssertionError(f"unerwarteter Git-Zugriff: {args}")

            stdout = io.StringIO()
            stderr = io.StringIO()
            argv = [
                str(SCRIPT),
                "--root", str(ROOT),
                "--manifest", str(manifest_path),
                "--authority-commit", authority["authority_commit"],
                "--expected-authority-commit", authority["expected_authority_commit"],
            ]
            with (
                patch.object(sys, "argv", argv),
                patch.object(
                    READINESS, "_load_readiness_manifest", side_effect=load_then_replace,
                ) as manifest_loader,
                patch.object(
                    READINESS, "_load_authority_policy", return_value=(authority, []),
                ) as authority_loader,
                patch.object(READINESS, "_git", side_effect=fake_git),
                patch.object(READINESS, "_load_bundle_manifest", return_value=({}, [])),
                patch.object(READINESS, "_run_gates", return_value=[]),
                patch.object(READINESS, "_verify_attestation_bundle", return_value=[]),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = READINESS.main()

            self.assertEqual(0, exit_code)
            self.assertEqual("", stderr.getvalue())
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["ok"])
            self.assertEqual(expected_basis, payload["basis_sha256"])
            self.assertEqual(1, manifest_loader.call_count)
            self.assertEqual(1, authority_loader.call_count)


if __name__ == "__main__":
    unittest.main()
