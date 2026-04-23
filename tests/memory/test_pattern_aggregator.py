from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from services.enrichment import ENRICHER_VERSION
from services.pacing.pattern_aggregator import (
    PatternAggregator,
    make_context_fingerprint,
    bpm_bucket,
)


def _build_sqlite(tmp_path: Path) -> tuple[Any, Any]:
    """Migrate a fresh SQLite at tmp_path up to head.

    Pre-creates audio_tracks, video_clips, and scenes stubs before Alembic
    runs, because mem_pacing_run/mem_decision have FKs to those tables but
    they are not part of any Alembic migration (they live in the main app
    schema bootstrapped by models.py).
    """
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "test_mem.db"

    # Pre-create dependency tables before migrations (FK order matters even in SQLite)
    bootstrap_engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    with bootstrap_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE audio_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE video_clips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE scenes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_clip_id INTEGER NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                label TEXT,
                energy REAL,
                FOREIGN KEY (video_clip_id) REFERENCES video_clips(id)
            )
        """))
    bootstrap_engine.dispose()

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(cfg, "head")

    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    return engine, sessionmaker(bind=engine)


def _seed_run(engine: Any, user_rating: int | None = None) -> int:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audio_tracks (id, file_path, original_filename, sha256, status, created_at) "
                "VALUES (1, '/f.mp3', 'f.mp3', 'x', 'ready', datetime('now'))"
            )
        )
        result = conn.execute(
            text(
                "INSERT INTO mem_pacing_run (audio_track_id, started_at, is_dj_mix, total_duration_sec, "
                "total_cuts, agent_version, weights_profile, user_rating) "
                "VALUES (1, datetime('now'), 0, 120.0, 0, 'test-v1', 'default', :ur) RETURNING id"
            ),
            {"ur": user_rating},
        )
        row = result.fetchone()
        assert row is not None
        return int(row[0])


def _seed_decision(
    engine: Any,
    run_id: int,
    scene_id: int,
    at_genre: str,
    at_section_type: str,
    at_bpm: float,
    user_verdict: str | None = None,
    at_enricher_version: str = ENRICHER_VERSION,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO mem_decision
                (run_id, sequence_idx, at_timestamp_sec, at_section_type, at_bpm,
                 at_genre, at_enricher_version, scene_id, clip_role, clip_mood_refined,
                 clip_style_bucket_id, agent_score, agent_rationale, user_verdict)
                VALUES
                (:rid, 0, 60.0, :sec, :bpm, :genre, :ver, :sid,
                 'hero', 'euphoric', 1, 0.7, '{}', :uv)
            """),
            {
                "rid": run_id,
                "sec": at_section_type,
                "bpm": at_bpm,
                "genre": at_genre,
                "ver": at_enricher_version,
                "sid": scene_id,
                "uv": user_verdict,
            },
        )


def test_aggregation_groups_by_context_fingerprint(tmp_path: Path) -> None:
    """Three decisions with same (genre, section, bpm_bucket, scene_id) must yield exactly one pattern."""
    engine, Session = _build_sqlite(tmp_path)
    run_id = _seed_run(engine)
    for _ in range(3):
        _seed_decision(
            engine,
            run_id,
            scene_id=42,
            at_genre="psytrance",
            at_section_type="drop",
            at_bpm=140.0,
            user_verdict="accept",
        )

    agg = PatternAggregator(session_factory=Session)
    n = agg.run()
    assert n == 1
    with engine.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM mem_learned_pattern")).scalar()
    assert count == 1


def test_wilson_lower_bound_used_for_confidence(tmp_path: Path) -> None:
    """With 7 accepts + 3 rejects, confidence == wilson_lower_bound(7, 10)."""
    from services.stats.wilson_lower_bound import wilson_lower_bound

    engine, Session = _build_sqlite(tmp_path)
    run_id = _seed_run(engine)
    for _ in range(7):
        _seed_decision(
            engine,
            run_id,
            scene_id=42,
            at_genre="psytrance",
            at_section_type="drop",
            at_bpm=140.0,
            user_verdict="accept",
        )
    for _ in range(3):
        _seed_decision(
            engine,
            run_id,
            scene_id=42,
            at_genre="psytrance",
            at_section_type="drop",
            at_bpm=140.0,
            user_verdict="reject",
        )

    agg = PatternAggregator(session_factory=Session)
    agg.run()

    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT confidence, stat_accept_count, stat_reject_count, stat_sample_size "
                    "FROM mem_learned_pattern WHERE pattern_type='context_preference'"
                )
            )
            .mappings()
            .one()
        )
    expected = wilson_lower_bound(7, 10)
    assert abs(row["confidence"] - expected) < 1e-9
    assert (
        row["stat_accept_count"] == 7
        and row["stat_reject_count"] == 3
        and row["stat_sample_size"] == 10
    )


def test_aggregator_skips_stale_enricher_version(tmp_path: Path) -> None:
    """Decisions with at_enricher_version != current are ignored (bug G)."""
    engine, Session = _build_sqlite(tmp_path)
    run_id = _seed_run(engine)
    # 2 fresh decisions
    for _ in range(2):
        _seed_decision(
            engine,
            run_id,
            scene_id=42,
            at_genre="psytrance",
            at_section_type="drop",
            at_bpm=140.0,
            user_verdict="accept",
            at_enricher_version=ENRICHER_VERSION,
        )
    # 5 stale decisions — must be ignored
    for _ in range(5):
        _seed_decision(
            engine,
            run_id,
            scene_id=42,
            at_genre="psytrance",
            at_section_type="drop",
            at_bpm=140.0,
            user_verdict="accept",
            at_enricher_version="v0_stale",
        )

    agg = PatternAggregator(session_factory=Session)
    agg.run()
    with engine.begin() as conn:
        row = (
            conn.execute(text("SELECT stat_sample_size FROM mem_learned_pattern"))
            .mappings()
            .one_or_none()
        )
    assert row is not None
    # Only 2 fresh decisions should have contributed
    assert row["stat_sample_size"] == 2


def test_run_rating_dampening(tmp_path: Path) -> None:
    """Decisions without explicit user_verdict but with run.user_rating >= 4 count at 0.3 weight."""
    engine, Session = _build_sqlite(tmp_path)
    run_id = _seed_run(engine, user_rating=5)  # strong positive run rating
    # 10 decisions, NO user_verdict (so verdict=None → run_rating fallback)
    for _ in range(10):
        _seed_decision(
            engine,
            run_id,
            scene_id=42,
            at_genre="psytrance",
            at_section_type="drop",
            at_bpm=140.0,
            user_verdict=None,
        )

    agg = PatternAggregator(session_factory=Session)
    agg.run()
    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    "SELECT stat_accept_count, stat_reject_count, stat_sample_size "
                    "FROM mem_learned_pattern"
                )
            )
            .mappings()
            .one()
        )
    # 10 decisions × 0.3 = 3.0 → rounded to 3
    assert row["stat_accept_count"] == 3
    assert row["stat_reject_count"] == 0
    assert row["stat_sample_size"] == 3


def test_bpm_is_bucketed_not_raw_float(tmp_path: Path) -> None:
    """Bug H regression: BPM 139.98 and 140.01 must aggregate into the same pattern."""
    engine, Session = _build_sqlite(tmp_path)
    run_id = _seed_run(engine)
    _seed_decision(
        engine,
        run_id,
        scene_id=42,
        at_genre="psytrance",
        at_section_type="drop",
        at_bpm=139.98,
        user_verdict="accept",
    )
    _seed_decision(
        engine,
        run_id,
        scene_id=42,
        at_genre="psytrance",
        at_section_type="drop",
        at_bpm=140.01,
        user_verdict="accept",
    )
    _seed_decision(
        engine,
        run_id,
        scene_id=42,
        at_genre="psytrance",
        at_section_type="drop",
        at_bpm=140.49,
        user_verdict="accept",
    )
    agg = PatternAggregator(session_factory=Session)
    agg.run()
    with engine.begin() as conn:
        rows = (
            conn.execute(text("SELECT stat_sample_size FROM mem_learned_pattern"))
            .mappings()
            .all()
        )
    # All three BPM values bucket to "140", so ONE pattern row with sample_size=3
    assert len(rows) == 1
    assert rows[0]["stat_sample_size"] == 3


def test_no_deprecated_utcnow_usage() -> None:
    """Bug L regression: module must use datetime.now(timezone.utc), never datetime.utcnow()."""
    source = Path("services/pacing/pattern_aggregator.py").read_text(encoding="utf-8")
    assert (
        "datetime.utcnow(" not in source
    ), "deprecated datetime.utcnow() usage detected"
    # Positive check: the timezone-aware form should be present
    assert (
        "datetime.now(timezone.utc)" in source
        or "datetime.now(tz=timezone.utc)" in source
    )


def test_idempotent_upsert(tmp_path: Path) -> None:
    """Running aggregation twice must update the same pattern row, not create duplicates."""
    engine, Session = _build_sqlite(tmp_path)
    run_id = _seed_run(engine)
    for _ in range(5):
        _seed_decision(
            engine,
            run_id,
            scene_id=42,
            at_genre="psytrance",
            at_section_type="drop",
            at_bpm=140.0,
            user_verdict="accept",
        )
    agg = PatternAggregator(session_factory=Session)
    agg.run()
    agg.run()  # second run should NOT add a duplicate
    with engine.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM mem_learned_pattern")).scalar()
    assert count == 1


def test_bpm_bucket_helper() -> None:
    assert bpm_bucket(None) is None
    assert bpm_bucket(139.49) == "139"
    assert bpm_bucket(139.5) == "140"  # rounds to 140
    assert bpm_bucket(140.0) == "140"


def test_fingerprint_is_json_stable() -> None:
    fp1 = make_context_fingerprint("Psytrance", "DROP", 139.98)
    fp2 = make_context_fingerprint("psytrance", "drop", 140.01)
    assert fp1 == fp2  # genre/section lowercased, BPM bucketed
