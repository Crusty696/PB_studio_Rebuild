from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "qa_artifacts" / "distribution_bundle_candidate.json"

sys.path.insert(0, str(ROOT))

from services.deferred_gates import active_gates  # noqa: E402
from services.release_readiness import production_blockers  # noqa: E402


EXPECTED_VERSION = "0.5.0"
INSTALLER_EXE = ROOT / "dist" / f"pb_studio_setup_v{EXPECTED_VERSION}.exe"
INSTALLER_PAYLOAD = ROOT / "dist" / f"pb_studio_setup_v{EXPECTED_VERSION}.nsisbin"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _file_info(path: Path, *, hash_file: bool = False) -> dict[str, object]:
    exists = path.is_file()
    info: dict[str, object] = {
        "path": str(path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else 0,
    }
    if exists and hash_file:
        info["sha256"] = _sha256(path)
    return info


def _doc_info(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "exists": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
    }


def main() -> int:
    gates = active_gates(ROOT / "docs" / "superpowers" / "DEFERRED_GATES.md")
    blockers = production_blockers(ROOT)
    open_blocker_ids = [gate.gate_id for gate in gates] + [blocker.blocker_id for blocker in blockers]

    docs = {
        "deployment": _doc_info(ROOT / "docs" / "DEPLOYMENT.md"),
        "installer_checklist": _doc_info(ROOT / "installer" / "DEPLOYMENT_CHECKLIST.md"),
        "user_installation_guide": _doc_info(ROOT / "docs" / "user" / "INSTALLATION_GUIDE.md"),
        "license": _doc_info(ROOT / "LICENSE.txt"),
    }
    installer = _file_info(INSTALLER_EXE, hash_file=True)
    payload = _file_info(INSTALLER_PAYLOAD, hash_file=True)

    hard_checks = {
        "installer_stub_exists": installer["exists"],
        "installer_stub_nonempty": installer["size_bytes"] > 100_000,
        "installer_payload_exists": payload["exists"],
        "installer_payload_large_enough": payload["size_bytes"] > 1024**3,
        "filenames_match_expected_version": (
            INSTALLER_EXE.name == f"pb_studio_setup_v{EXPECTED_VERSION}.exe"
            and INSTALLER_PAYLOAD.name == f"pb_studio_setup_v{EXPECTED_VERSION}.nsisbin"
        ),
        "required_distribution_docs_present": all(doc["exists"] for doc in docs.values()),
        "release_gate_still_blocks": bool(open_blocker_ids),
    }

    result = {
        "status": "blocked-candidate-only",
        "distribution_candidate_ready": False,
        "artifact_pair_ready": (
            hard_checks["installer_stub_exists"]
            and hard_checks["installer_stub_nonempty"]
            and hard_checks["installer_payload_exists"]
            and hard_checks["installer_payload_large_enough"]
            and hard_checks["filenames_match_expected_version"]
        ),
        "can_create_distribution_zip": False,
        "release_ready": False,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "expected_version": EXPECTED_VERSION,
        "installer_exe": installer,
        "installer_payload": payload,
        "required_docs": docs,
        "hard_checks": hard_checks,
        "deferred_gates": [gate.__dict__ for gate in gates],
        "production_blockers": [blocker.__dict__ for blocker in blockers],
        "open_blocker_ids": open_blocker_ids,
        "honest_limit": (
            "This verifier proves local bundle inputs only. It does not create a "
            "release ZIP or run a clean VM install. Final release state comes from "
            "tools/release_gate.py."
        ),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
