"""Hard release gate: refuse a release/fixed claim while blockers are open.

Exit codes:
  0  -> no active deferred gates or production blockers; release/fixed claim is allowed.
  2  -> at least one blocker exists; release/fixed is BLOCKED.

Usage:
  python tools/release_gate.py

Sources of truth:
  - docs/superpowers/DEFERRED_GATES.md (via services.deferred_gates)
  - local release artifacts + synthesis proofs (via services.release_readiness)
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from services.deferred_gates import active_gates  # noqa: E402
from services.release_readiness import production_blockers  # noqa: E402


def _configure_console_output() -> None:
    """Keep gate output writable on legacy Windows console encodings."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(errors="backslashreplace")


def main() -> int:
    _configure_console_output()
    gates = active_gates(_REPO / "docs" / "superpowers" / "DEFERRED_GATES.md")
    blockers = production_blockers(_REPO)
    if not gates and not blockers:
        print("RELEASE-GATE OK: keine offenen Deferred Gates oder Produktionsblocker.")
        return 0
    print("RELEASE-GATE BLOCKED: offene Blocker verhindern release/fixed:")
    if gates:
        print("  Deferred Gates:")
        for g in gates:
            print(f"    - {g.gate_id} [{g.status}] (Quelle: {g.source_task})")
            print(f"        noch zu tun: {g.must_happen_later}")
    if blockers:
        print("  Produktionsblocker:")
        for blocker in blockers:
            print(f"    - {blocker.blocker_id}: {blocker.label}")
            print(f"        {blocker.detail}")
    print(
        "\nLive-verifizieren, signieren, Clean-VM/installierte App belegen "
        "oder vom User re-entscheiden; danach Quellen aktualisieren."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
