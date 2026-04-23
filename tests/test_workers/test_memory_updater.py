from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from services.enrichment import ENRICHER_VERSION
from workers.memory_updater import MemoryUpdaterWorker


def _build_sqlite_with_migrations(tmp_path: Path) -> tuple[Any, Any]:
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "mem.db"

    # Pre-create dependency tables before Alembic migrations run.
    # audio_tracks, video_clips, scenes are part of the main app schema
    # (bootstrapped by models.py), not Alembic, but mem_pacing_run /
    # mem_decision have FKs into them.
    bootstrap = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    with bootstrap.begin() as conn:
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
    bootstrap.dispose()

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    return engine, sessionmaker(bind=engine)


def _seed_decisions(engine: Any, n: int) -> int:
    """Seed n accept-decisions on one scene so there's something to aggregate."""
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO audio_tracks (id, file_path, original_filename, sha256, status, created_at) "
            "VALUES (1, '/f.mp3', 'f.mp3', 'x', 'ready', datetime('now'))"
        ))
        row = conn.execute(text(
            "INSERT INTO mem_pacing_run (audio_track_id, started_at, is_dj_mix, total_duration_sec, "
            "total_cuts, agent_version, weights_profile) VALUES (1, datetime('now'), 0, 120.0, 0, "
            "'test', 'default') RETURNING id"
        )).fetchone()
        assert row is not None
        run_id = int(row[0])
        for i in range(n):
            conn.execute(text("""
                INSERT INTO mem_decision
                (run_id, sequence_idx, at_timestamp_sec, at_section_type, at_bpm, at_genre,
                 at_enricher_version, scene_id, clip_role, clip_mood_refined, clip_style_bucket_id,
                 agent_score, agent_rationale, user_verdict)
                VALUES (:rid, :i, 60.0, 'drop', 140.0, 'psytrance', :ver, 42, 'hero', 'euphoric', 1,
                        0.7, '{}', 'accept')
            """), {"rid": run_id, "i": i, "ver": ENRICHER_VERSION})
    return run_id


def test_worker_flushes_after_batch_size(tmp_path: Path) -> None:
    engine, Session = _build_sqlite_with_migrations(tmp_path)
    _seed_decisions(engine, n=1)
    worker = MemoryUpdaterWorker(session_factory=Session, batch_size=3)

    # 2 feedback events → no flush yet
    assert worker.notify_feedback() is False
    assert worker.notify_feedback() is False
    assert worker.pending_events == 2
    # 3rd feedback triggers flush
    assert worker.notify_feedback() is True
    assert worker.pending_events == 0
    # And the pattern is in the DB
    with engine.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM mem_learned_pattern")).scalar()
    assert count == 1


def test_worker_flushes_on_run_end(tmp_path: Path) -> None:
    engine, Session = _build_sqlite_with_migrations(tmp_path)
    _seed_decisions(engine, n=1)
    worker = MemoryUpdaterWorker(session_factory=Session)
    # No feedback events yet; run_end should still flush
    worker.notify_feedback()   # 1 pending
    n = worker.notify_run_end()
    assert n == 1
    assert worker.pending_events == 0


def test_default_batch_size_is_20(tmp_path: Path) -> None:
    engine, Session = _build_sqlite_with_migrations(tmp_path)
    worker = MemoryUpdaterWorker(session_factory=Session)
    assert worker.BATCH_SIZE == 20


def test_worker_is_idempotent_when_no_decisions(tmp_path: Path) -> None:
    engine, Session = _build_sqlite_with_migrations(tmp_path)
    worker = MemoryUpdaterWorker(session_factory=Session)
    # No decisions seeded; run() should return 0, not raise
    assert worker.run() == 0
