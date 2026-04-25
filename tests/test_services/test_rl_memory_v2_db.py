"""P1.3: RL-Memory v2 schreibt Reward-Daten zurück in mem_decision."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from services.pacing.rl_memory_v2 import DecisionRecord, RLPacingMemoryV2

# Reuse the SQLite-with-mem_decision harness
from tests.memory.test_decision_recorder import (
    _build_sqlite_with_mem_decision,
    _seed_run,
)


def _insert_initial_decision(engine, run_id: int, sequence_idx: int) -> int:
    """Helper: legt eine mem_decision-Row an, simuliert was der
    DecisionRecorder im Pacing-Hot-Path tut."""
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO mem_decision (
                    run_id, sequence_idx, at_timestamp_sec,
                    scene_id, clip_role, clip_mood_refined,
                    clip_style_bucket_id, clip_motion_score,
                    agent_score, agent_rationale
                ) VALUES (
                    :run_id, :seq, :ts,
                    :scene_id, :role, :mood, :bucket, :motion,
                    :score, :rationale
                ) RETURNING id
                """
            ),
            {
                "run_id": run_id, "seq": sequence_idx, "ts": 5.0,
                "scene_id": 42, "role": "hero", "mood": "energetic",
                "bucket": 3, "motion": 0.7,
                "score": 0.6, "rationale": "{}",
            },
        )
        row = result.fetchone()
        assert row is not None
        return int(row[0])


def test_rl_memory_v2_updates_reward_in_db(tmp_path: Path):
    engine, Session = _build_sqlite_with_mem_decision(tmp_path)
    run_id = _seed_run(engine)
    decision_id = _insert_initial_decision(engine, run_id, sequence_idx=1)

    mem = RLPacingMemoryV2(db_session_factory=Session)
    rec = DecisionRecord(
        run_id=run_id,
        cut_id=1,  # = sequence_idx
        timestamp_ms=5000,
        section_type="drop",
        scene_id=42,
        verdict="good",
        reward=0.85,
        components={"r_energy": 0.9, "r_mood": 0.8},
    )
    mem.record(rec)

    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT user_verdict, reward, reward_components "
                "FROM mem_decision WHERE id = :id"
            ),
            {"id": decision_id},
        ).fetchone()
    assert row[0] == "good"
    assert abs(row[1] - 0.85) < 1e-6
    parsed = json.loads(row[2])
    assert abs(parsed["r_energy"] - 0.9) < 1e-6


def test_rl_memory_v2_no_db_factory_works_in_memory_only():
    """Ohne db_session_factory bleibt RL-Memory in-memory (Backward-Compat)."""
    mem = RLPacingMemoryV2()  # kein db_session_factory
    rec = DecisionRecord(
        run_id=1, cut_id=1, timestamp_ms=1000, section_type="drop",
        scene_id=1, verdict="good", reward=0.7, components={},
    )
    mem.record(rec)
    assert mem.count() == 1
    assert mem.section_acceptance_rate("drop") == 1.0


def test_rl_memory_v2_db_failure_does_not_crash_in_memory(tmp_path: Path):
    """Wenn der DB-Update fehlschlägt, soll der in-memory-Pfad trotzdem
    funktionieren — RL-Loop darf nicht durch DB-Probleme tot sein."""
    def _broken_session():
        raise RuntimeError("simulated DB outage")

    mem = RLPacingMemoryV2(db_session_factory=_broken_session)
    rec = DecisionRecord(
        run_id=1, cut_id=1, timestamp_ms=1000, section_type="drop",
        scene_id=1, verdict="good", reward=0.7, components={},
    )
    mem.record(rec)  # darf nicht crashen
    assert mem.count() == 1


def test_rl_memory_v2_skips_update_when_no_matching_row(tmp_path: Path):
    """UPDATE auf nicht-existente Row → kein Crash, kein in-memory verlust."""
    engine, Session = _build_sqlite_with_mem_decision(tmp_path)
    run_id = _seed_run(engine)
    # KEINE initial-decision angelegt — Update wird 0 Zeilen treffen

    mem = RLPacingMemoryV2(db_session_factory=Session)
    rec = DecisionRecord(
        run_id=run_id, cut_id=99, timestamp_ms=500,
        section_type="drop", scene_id=1, verdict="bad",
        reward=0.1, components={},
    )
    mem.record(rec)
    assert mem.count() == 1  # in-memory hat den record
