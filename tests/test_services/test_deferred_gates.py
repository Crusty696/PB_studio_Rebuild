"""Tests for services.deferred_gates (release-gate foundation)."""
from __future__ import annotations

from pathlib import Path

from services import deferred_gates as dg

_REPO = Path(__file__).resolve().parents[2]

_SAMPLE = """# PB Studio Deferred Gates

## Active Deferred Gates

| gate_id | source_task | status | must_happen_later | reason | evidence |
|---|---|---|---|---|---|
| DG-001 | OTK-019 | deferred-heavy-live-gate | run 4h test | user defer | ev1 |
| DG-002 | OTK-099 | live-verified | nothing | done | ev2 |

## Rules

- Deferred gate does not permit `fixed`.
"""


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "DEFERRED_GATES.md"
    p.write_text(_SAMPLE, encoding="utf-8")
    return p


def test_parse_skips_header_and_separator(tmp_path):
    gates = dg.parse_deferred_gates(_write(tmp_path))
    assert [g.gate_id for g in gates] == ["DG-001", "DG-002"]


def test_active_excludes_resolved(tmp_path):
    active = dg.active_gates(_write(tmp_path))
    assert [g.gate_id for g in active] == ["DG-001"]
    assert active[0].is_active is True


def test_release_block_reason_lists_active(tmp_path):
    reason = dg.release_block_reason(_write(tmp_path))
    assert reason is not None
    assert "DG-001" in reason
    assert "DG-002" not in reason


def test_no_block_when_all_cleared(tmp_path):
    p = tmp_path / "DEFERRED_GATES.md"
    p.write_text(_SAMPLE.replace("deferred-heavy-live-gate", "live-verified"), encoding="utf-8")
    assert dg.active_gates(p) == []
    assert dg.release_block_reason(p) is None


def test_missing_file_is_empty(tmp_path):
    assert dg.parse_deferred_gates(tmp_path / "nope.md") == []
    assert dg.release_block_reason(tmp_path / "nope.md") is None


def test_real_repo_file_parses():
    """The shipped DEFERRED_GATES.md must parse and reflect current gate state."""
    real = _REPO / "docs" / "superpowers" / "DEFERRED_GATES.md"
    gates = dg.parse_deferred_gates(real)
    by_id = {g.gate_id: g for g in gates}
    assert "DG-001" in by_id
    assert by_id["DG-001"].status == "live-verified"
    assert by_id["DG-001"].is_active is False
