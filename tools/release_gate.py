"""Hard release gate: refuse a release/fixed claim while Deferred Gates are open.

Exit codes:
  0  -> no active deferred gates; release/fixed claim is allowed.
  2  -> at least one active deferred gate; release/fixed is BLOCKED.

Usage:
  python tools/release_gate.py

Single source of truth: docs/superpowers/DEFERRED_GATES.md (via
services.deferred_gates). Wired into tools/agent_handoff.ps1 (-ReleaseGate).
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from services.deferred_gates import active_gates  # noqa: E402


def main() -> int:
    gates = active_gates(_REPO / "docs" / "superpowers" / "DEFERRED_GATES.md")
    if not gates:
        print("RELEASE-GATE OK: keine offenen Deferred Gates.")
        return 0
    print("RELEASE-GATE BLOCKED: offene Deferred Gates verhindern release/fixed:")
    for g in gates:
        print(f"  - {g.gate_id} [{g.status}] (Quelle: {g.source_task})")
        print(f"      noch zu tun: {g.must_happen_later}")
    print(
        "\nLive-verifizieren oder vom User re-entscheiden, dann "
        "DEFERRED_GATES.md aktualisieren."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
