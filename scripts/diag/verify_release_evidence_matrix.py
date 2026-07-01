from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "qa_artifacts" / "release_evidence_matrix.json"
SYNTHESIS = ROOT / "docs" / "superpowers" / "synthesis"
QA = ROOT / "tests" / "qa_artifacts"

sys.path.insert(0, str(ROOT))

from services.deferred_gates import active_gates  # noqa: E402
from services.release_readiness import production_blockers  # noqa: E402


JSON_SOURCES = {
    "release_artifact_pair_audit": QA / "release_artifact_pair_audit.json",
    "signing_readiness": QA / "signing_readiness.json",
    "clean_vm_readiness": QA / "clean_vm_readiness.json",
    "installed_app_gui_readiness": QA / "installed_app_gui_readiness.json",
    "installed_app_gui_workflow": QA / "installed_app_gui_workflow.json",
}


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


def _frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    values: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip().lower()] = value.strip().strip("'\"").lower()
    return values


def _proofs() -> list[dict[str, object]]:
    if not SYNTHESIS.is_dir():
        return []
    found: list[dict[str, object]] = []
    for path in sorted(SYNTHESIS.glob("*.md")):
        fm = _frontmatter(path)
        if fm.get("release_gate_proof") != "true":
            continue
        found.append(
            {
                "path": str(path),
                "proof_type": fm.get("proof_type"),
                "status": fm.get("status"),
                "evidence_level": fm.get("evidence_level"),
                "accepted_by_gate": (
                    fm.get("status") == "pass"
                    and fm.get("evidence_level") == "live"
                    and fm.get("proof_type") in {"clean-vm-install", "installed-app-gui"}
                ),
            }
        )
    return found


def _git_head() -> dict[str, object]:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {"returncode": proc.returncode, "short_head": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def main() -> int:
    gates = active_gates(ROOT / "docs" / "superpowers" / "DEFERRED_GATES.md")
    blockers = production_blockers(ROOT)
    proofs = _proofs()
    sources = {name: _load_json(path) for name, path in JSON_SOURCES.items()}

    open_items = []
    for gate in gates:
        open_items.append(
            {
                "id": gate.gate_id,
                "kind": "deferred_gate",
                "label": gate.source_task,
                "detail": gate.must_happen_later,
                "evidence_status": "open",
            }
        )
    for blocker in blockers:
        open_items.append(
            {
                "id": blocker.blocker_id,
                "kind": "production_blocker",
                "label": blocker.label,
                "detail": blocker.detail,
                "evidence_status": "open",
            }
        )

    result = {
        "status": "blocked" if open_items else "pass",
        "release_ready": not open_items,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git": _git_head(),
        "deferred_gates": [gate.__dict__ for gate in gates],
        "production_blockers": [blocker.__dict__ for blocker in blockers],
        "release_gate_proofs": proofs,
        "qa_json_sources": sources,
        "open_items": open_items,
        "honest_limit": (
            "This matrix aggregates evidence. It does not sign the installer, "
            "run a clean VM, install PB Studio, or resolve user decisions."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
