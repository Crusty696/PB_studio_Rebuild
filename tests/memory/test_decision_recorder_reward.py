"""P1.3: DecisionRecorder.record() persistiert reward + reward_components."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from services.pacing.decision_recorder import DecisionRecorder

# Reuse the existing harness from the recorder test module
from tests.memory.test_decision_recorder import (
    _build_sqlite_with_mem_decision,
    _make_clip,
    _make_ctx,
    _seed_run,
)


def test_record_with_reward_persists_columns(tmp_path: Path):
    engine, Session = _build_sqlite_with_mem_decision(tmp_path)
    run_id = _seed_run(engine)
    recorder = DecisionRecorder(session_factory=Session)

    components = {
        "r_energy": 0.7, "r_mood": 0.85, "r_stem_class": 0.5,
        "r_section": 0.6, "r_freshness": 0.9, "r_collision": 0.7, "r_user": 0.5,
    }
    decision_id = recorder.record(
        run_id=run_id,
        sequence_idx=0,
        ctx=_make_ctx(),
        chosen=_make_clip(),
        rationale={"chosen_score": 0.65},
        agent_score=0.65,
        reward=0.69,
        reward_components=components,
    )
    assert decision_id is not None

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT reward, reward_components FROM mem_decision WHERE id=:id"),
            {"id": decision_id},
        ).fetchone()

    assert row is not None
    assert abs(row[0] - 0.69) < 1e-6
    parsed = json.loads(row[1])
    assert set(parsed.keys()) == set(components.keys())
    for k, v in components.items():
        assert abs(parsed[k] - v) < 1e-6


def test_record_without_reward_writes_null(tmp_path: Path):
    """Backward-Compat: alte Caller (kein reward-Arg) → DB-Spalten NULL."""
    engine, Session = _build_sqlite_with_mem_decision(tmp_path)
    run_id = _seed_run(engine)
    recorder = DecisionRecorder(session_factory=Session)

    decision_id = recorder.record(
        run_id=run_id,
        sequence_idx=0,
        ctx=_make_ctx(),
        chosen=_make_clip(),
        rationale={"chosen_score": 0.5},
        agent_score=0.5,
    )
    assert decision_id is not None

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT reward, reward_components FROM mem_decision WHERE id=:id"),
            {"id": decision_id},
        ).fetchone()
    assert row is not None
    assert row[0] is None
    assert row[1] is None


def test_record_with_only_reward_no_components(tmp_path: Path):
    engine, Session = _build_sqlite_with_mem_decision(tmp_path)
    run_id = _seed_run(engine)
    recorder = DecisionRecorder(session_factory=Session)

    decision_id = recorder.record(
        run_id=run_id,
        sequence_idx=0,
        ctx=_make_ctx(),
        chosen=_make_clip(),
        rationale={"chosen_score": 0.4},
        agent_score=0.4,
        reward=0.42,
    )
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT reward, reward_components FROM mem_decision WHERE id=:id"),
            {"id": decision_id},
        ).fetchone()
    assert row[0] == pytest.approx(0.42)
    assert row[1] is None
