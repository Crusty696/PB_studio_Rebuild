"""Deferred-gate registry reader (DG-001, ...).

Single source of truth: ``docs/superpowers/DEFERRED_GATES.md``.

Used by:
  - ``services.startup_checks``  -> soft, non-blocking start banner.
  - ``tools/release_gate.py`` / ``tools/agent_handoff.ps1`` -> hard release gate.

A deferred gate is NOT fixed and NOT forgotten: until it is live-verified or
explicitly re-decided by the user, no ``release``/``fixed`` claim is allowed.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Statuses that mean the gate is CLEARED (no longer blocking a release).
_RESOLVED = {
    "resolved", "live-verified", "verified", "fixed",
    "done", "closed", "re-decided", "cleared",
}


@dataclass(frozen=True)
class DeferredGate:
    gate_id: str
    source_task: str
    status: str
    must_happen_later: str
    reason: str
    evidence: str

    @property
    def is_active(self) -> bool:
        """A gate blocks release unless its status is in the cleared set."""
        return self.status.strip().lower() not in _RESOLVED


def _default_path() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "docs" / "superpowers" / "DEFERRED_GATES.md"
    )


def parse_deferred_gates(md_path=None) -> list[DeferredGate]:
    """Parse the table under ``## Active Deferred Gates`` (stdlib only)."""
    path = Path(md_path) if md_path else _default_path()
    if not path.exists():
        return []
    gates: list[DeferredGate] = []
    in_section = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("## "):
            in_section = line.lower().startswith("## active deferred gates")
            continue
        if not in_section or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6:
            continue
        if cells[0].lower() == "gate_id" or set(cells[0]) <= {"-", ":"}:
            continue  # header or separator row
        gates.append(DeferredGate(*cells[:6]))
    return gates


def active_gates(md_path=None) -> list[DeferredGate]:
    """Gates that still block a release/fixed claim."""
    return [g for g in parse_deferred_gates(md_path) if g.is_active]


def release_block_reason(md_path=None) -> str | None:
    """Human-readable reason string if a release is blocked, else ``None``."""
    gates = active_gates(md_path)
    if not gates:
        return None
    ids = ", ".join(g.gate_id for g in gates)
    return (
        f"{len(gates)} offene Deferred Gate(s) blockieren release/fixed: {ids}"
    )
