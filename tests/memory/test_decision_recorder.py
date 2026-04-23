from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from services.enrichment import ENRICHER_VERSION
from services.pacing.decision_recorder import (
    AUDIO_CTX_SNAPSHOT_FIELDS,
    DecisionRecorder,
)
from services.pacing.pipeline import PacingPipeline
from services.pacing.scorer import AudioContext, ClipFeatures


def _build_sqlite_with_mem_decision(tmp_path: Path) -> tuple[Any, Any]:
    """Spin up a fresh SQLite at tmp_path and run Alembic up to head so mem_decision exists.

    The `audio_tracks` table must exist before Alembic runs because `mem_pacing_run`
    has a FK to it, but `audio_tracks` is not created by any migration (it lives in
    the main app schema).  We pre-create a minimal stub so the FK resolves.
    """
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "test_mem.db"

    # Pre-create audio_tracks stub before migrations run (FK dependency)
    bootstrap_engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    with bootstrap_engine.begin() as conn:
        conn.execute(text("""CREATE TABLE audio_tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at DATETIME NOT NULL
                )"""))
    bootstrap_engine.dispose()

    # Project alembic.ini lives at repo root
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    Session = sessionmaker(bind=engine)
    return engine, Session


def _make_ctx() -> AudioContext:
    return AudioContext(
        at_timestamp_sec=12.34,
        at_beat_idx=120,
        at_section_type="drop",
        at_bpm=140.0,
        at_energy=0.8,
        at_key="Am",
        at_key_confidence=0.9,
        at_harmonic_tension=0.75,
        at_mood_audio="energetic",
        at_mood_video="energetic",
        at_genre="psytrance",
        at_sub_genre="dark_psy",
        at_spectral_hash="hash_abc",
        at_groove_template="fotf",
        at_lufs=-8.5,
    )


def _make_clip() -> ClipFeatures:
    return ClipFeatures(
        clip_id=1,
        scene_id=10,
        role="hero",
        mood_refined="euphoric",
        style_bucket_id=2,
        motion_score=0.65,
        embedding=np.arange(8, dtype=np.float32),
    )


def _seed_run(engine: Any, audio_track_id: int = 1) -> int:
    """Insert a minimum-required mem_pacing_run row and return its id.
    Also insert an audio_tracks row since mem_pacing_run FK requires it."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audio_tracks (id, file_path, original_filename, sha256, status, created_at) "
                "VALUES (:id, :fp, :name, :sha, :status, datetime('now'))"
            ),
            {
                "id": audio_track_id,
                "fp": "/tmp/fake.mp3",
                "name": "fake.mp3",
                "sha": "0" * 64,
                "status": "ready",
            },
        )
        result = conn.execute(
            text(
                "INSERT INTO mem_pacing_run "
                "(audio_track_id, started_at, is_dj_mix, total_duration_sec, total_cuts, agent_version, weights_profile) "
                "VALUES (:atid, datetime('now'), 0, 120.0, 0, 'test-v1', 'default') "
                "RETURNING id"
            ),
            {"atid": audio_track_id},
        )
        row = result.fetchone()
        assert row is not None
        return int(row[0])


def test_record_persists_all_audio_context_fields(tmp_path: Path) -> None:
    engine, Session = _build_sqlite_with_mem_decision(tmp_path)
    run_id = _seed_run(engine)

    recorder = DecisionRecorder(session_factory=Session)
    decision_id = recorder.record(
        run_id=run_id,
        sequence_idx=0,
        ctx=_make_ctx(),
        chosen=_make_clip(),
        rationale={"chosen_score": 0.81, "contribs": {"role": 0.25}},
        agent_score=0.81,
    )
    assert decision_id is not None

    with engine.begin() as conn:
        row = (
            conn.execute(
                text("SELECT * FROM mem_decision WHERE id = :id"), {"id": decision_id}
            )
            .mappings()
            .one()
        )
    # All at_* fields from the AudioContext must be set
    for f in AUDIO_CTX_SNAPSHOT_FIELDS:
        assert row[f] is not None, f"{f} was null after record()"


def test_enricher_version_snapshotted_per_design_r4(tmp_path: Path) -> None:
    engine, Session = _build_sqlite_with_mem_decision(tmp_path)
    run_id = _seed_run(engine)

    recorder = DecisionRecorder(session_factory=Session)
    decision_id = recorder.record(
        run_id=run_id,
        sequence_idx=0,
        ctx=_make_ctx(),
        chosen=_make_clip(),
        rationale={},
        agent_score=0.5,
    )
    with engine.begin() as conn:
        row = (
            conn.execute(
                text("SELECT at_enricher_version FROM mem_decision WHERE id = :id"),
                {"id": decision_id},
            )
            .mappings()
            .one()
        )
    assert row["at_enricher_version"] == ENRICHER_VERSION, (
        f"expected at_enricher_version == {ENRICHER_VERSION}, "
        f"got {row['at_enricher_version']}"
    )


def test_sqlite_lock_retry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Simulate 2 OperationalErrors before success → record eventually succeeds."""
    engine, Session = _build_sqlite_with_mem_decision(tmp_path)
    run_id = _seed_run(engine)

    recorder = DecisionRecorder(session_factory=Session)

    calls: list[int] = []
    original_insert_once = recorder._insert_once

    def flaky_insert_once(payload: dict[str, Any]) -> int:
        calls.append(1)
        if len(calls) <= 2:
            raise OperationalError("stmt", {}, Exception("database is locked"))
        return original_insert_once(payload)

    monkeypatch.setattr(recorder, "_insert_once", flaky_insert_once)
    # Speed up test: shrink the backoff
    monkeypatch.setattr(recorder, "INITIAL_BACKOFF_SEC", 0.001)

    decision_id = recorder.record(
        run_id=run_id,
        sequence_idx=0,
        ctx=_make_ctx(),
        chosen=_make_clip(),
        rationale={},
        agent_score=0.5,
    )
    assert decision_id is not None
    assert len(calls) == 3, f"expected 3 tries (2 failures + success), got {len(calls)}"
    assert recorder.queue_size == 0


def test_pipeline_wiring_calls_recorder(tmp_path: Path) -> None:
    """Regression test for Bug F: PacingPipeline must call the DecisionRecorder."""
    engine, Session = _build_sqlite_with_mem_decision(tmp_path)
    run_id = _seed_run(engine)

    recorder = DecisionRecorder(session_factory=Session)
    pipeline = PacingPipeline(decision_recorder=recorder, run_id=run_id)

    hero = _make_clip()
    ctx = _make_ctx()
    result = pipeline.select_best([hero], ctx)
    assert result.chosen is not None
    # Row must be in mem_decision
    with engine.begin() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM mem_decision WHERE run_id = :rid"),
            {"rid": run_id},
        ).scalar()
    assert (
        count == 1
    ), f"expected 1 mem_decision row after pipeline.select_best, got {count}"
    # And rationale contains the persisted id
    assert "persisted_decision_id" in result.rationale
