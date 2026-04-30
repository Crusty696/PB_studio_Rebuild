from __future__ import annotations

import json

from sqlalchemy import text

from services.brain_v2.store import ensure_brain_v2_schema
from services.pacing.decision_recorder import DecisionRecorder
from tests.memory.test_decision_recorder import (
    _build_sqlite_with_mem_decision,
    _make_clip,
    _make_ctx,
    _seed_run,
)


def test_decision_recorder_shadow_writes_brain_v2_when_flag_enabled(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PB_STUDIO_BRAIN_V2", "1")
    engine, Session = _build_sqlite_with_mem_decision(tmp_path)
    ensure_brain_v2_schema(engine)
    run_id = _seed_run(engine)

    decision_id = DecisionRecorder(Session).record(
        run_id=run_id,
        sequence_idx=0,
        ctx=_make_ctx(),
        chosen=_make_clip(),
        rationale={"chosen_score": 0.9},
        agent_score=0.9,
    )

    assert decision_id is not None
    with engine.begin() as conn:
        mem_count = conn.execute(text("SELECT COUNT(*) FROM mem_decision")).scalar()
        row = conn.execute(
            text("SELECT decision_id, why_json, why_text FROM brain_decision")
        ).fetchone()
    assert mem_count == 1
    assert row is not None
    assert row[0] == decision_id
    why = json.loads(row[1])
    assert why["audio"]["section"] == "drop"
    assert why["clip"]["scene_id"] == 10
    assert "chose scene 10" in row[2]


def test_decision_recorder_brain_v2_failure_does_not_break_mem_decision(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PB_STUDIO_BRAIN_V2", "1")
    engine, Session = _build_sqlite_with_mem_decision(tmp_path)
    run_id = _seed_run(engine)

    decision_id = DecisionRecorder(Session).record(
        run_id=run_id,
        sequence_idx=0,
        ctx=_make_ctx(),
        chosen=_make_clip(),
        rationale={},
        agent_score=0.5,
    )

    assert decision_id is not None
    with engine.begin() as conn:
        mem_count = conn.execute(text("SELECT COUNT(*) FROM mem_decision")).scalar()
    assert mem_count == 1
