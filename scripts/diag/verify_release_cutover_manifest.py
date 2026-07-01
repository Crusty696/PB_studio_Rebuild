from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "qa_artifacts" / "release_cutover_manifest.json"

sys.path.insert(0, str(ROOT))

from services.deferred_gates import active_gates  # noqa: E402
from services.release_readiness import production_blockers  # noqa: E402


QA = ROOT / "tests" / "qa_artifacts"
SYNTHESIS = ROOT / "docs" / "superpowers" / "synthesis"


def _load_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"exists": False, "path": str(path)}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"exists": True, "path": str(path), "parse_error": str(exc)}
    if isinstance(data, dict):
        data.setdefault("exists", True)
        data.setdefault("path", str(path))
        return data
    return {"exists": True, "path": str(path), "payload_type": type(data).__name__}


def _required_actions(open_ids: set[str]) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    if "DG-001" in open_ids:
        actions.append(
            {
                "blocker_id": "DG-001",
                "owner": "user",
                "action": "Decide whether the 4h H1 loop medium is accepted as replacement for the lost historical H1 medium.",
                "required_evidence": str(SYNTHESIS / "dg001-h1-4h-live-2026-06-23.md"),
                "clears_release_gate": False,
                "note": "Agent cannot decide this without user acceptance.",
            }
        )
    if "SIGN-001" in open_ids:
        actions.append(
            {
                "blocker_id": "SIGN-001",
                "owner": "operator",
                "action": "Install trusted code-signing tool/certificate and sign the installer stub.",
                "required_command_after_signing": (
                    "& 'C:\\Users\\David_Lochmann\\miniconda3\\envs\\pb-studio\\python.exe' "
                    "scripts\\diag\\verify_signing_readiness.py"
                ),
                "required_evidence": str(QA / "signing_readiness.json"),
                "clears_release_gate": False,
                "note": "Signing changes the installer EXE hash; refresh distribution hashes after signing.",
            }
        )
    if "VM-001" in open_ids:
        actions.append(
            {
                "blocker_id": "VM-001",
                "owner": "operator",
                "action": "Run installer stub and NSISBI payload on a clean Windows VM, then create live proof frontmatter.",
                "required_frontmatter": {
                    "release_gate_proof": "true",
                    "proof_type": "clean-vm-install",
                    "status": "pass",
                    "evidence_level": "live",
                },
                "required_command_before_attempt": (
                    "& 'C:\\Users\\David_Lochmann\\miniconda3\\envs\\pb-studio\\python.exe' "
                    "scripts\\diag\\verify_clean_vm_readiness.py"
                ),
                "clears_release_gate": False,
                "note": "Preflight alone cannot clear VM-001; only live clean-VM install proof can.",
            }
        )
    if "GUI-001" in open_ids:
        actions.append(
            {
                "blocker_id": "GUI-001",
                "owner": "operator",
                "action": "Launch installed PB Studio EXE and run installed-app GUI verifier with proof writing.",
                "required_command_after_install": (
                    "& 'C:\\Users\\David_Lochmann\\miniconda3\\envs\\pb-studio\\python.exe' "
                    "scripts\\diag\\verify_installed_app_gui_workflow.py --write-proof"
                ),
                "required_frontmatter": {
                    "release_gate_proof": "true",
                    "proof_type": "installed-app-gui",
                    "status": "pass",
                    "evidence_level": "live",
                },
                "clears_release_gate": False,
                "note": "Verifier writes proof only after real installed EXE GUI pass.",
            }
        )
    return actions


def main() -> int:
    gates = active_gates(ROOT / "docs" / "superpowers" / "DEFERRED_GATES.md")
    blockers = production_blockers(ROOT)
    open_ids = {gate.gate_id for gate in gates} | {blocker.blocker_id for blocker in blockers}
    sources = {
        "distribution_bundle_candidate": _load_json(QA / "distribution_bundle_candidate.json"),
        "release_evidence_matrix": _load_json(QA / "release_evidence_matrix.json"),
        "signing_readiness": _load_json(QA / "signing_readiness.json"),
        "clean_vm_readiness": _load_json(QA / "clean_vm_readiness.json"),
        "installed_app_gui_readiness": _load_json(QA / "installed_app_gui_readiness.json"),
        "installed_app_gui_workflow": _load_json(QA / "installed_app_gui_workflow.json"),
    }
    result = {
        "status": "blocked" if open_ids else "pass",
        "release_ready": not open_ids,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "open_blocker_ids": sorted(open_ids),
        "deferred_gates": [gate.__dict__ for gate in gates],
        "production_blockers": [blocker.__dict__ for blocker in blockers],
        "required_actions": _required_actions(open_ids),
        "qa_sources": sources,
        "final_gate_command": (
            "& 'C:\\Users\\David_Lochmann\\miniconda3\\envs\\pb-studio\\python.exe' tools\\release_gate.py"
        ),
        "honest_limit": (
            "This manifest does not clear blockers. It records exact remaining proof work "
            "from current gate state."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
