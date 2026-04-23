"""T8.1 headless test: feedback keystrokes persist mem_user_feedback_event."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from services.enrichment import ENRICHER_VERSION
from services.feedback_service import FeedbackService, VERDICT_FROM_KEY


def _build_sqlite(tmp_path: Path) -> tuple[Any, Any]:
    """Migrate a fresh SQLite at tmp_path up to head.

    Pre-creates audio_tracks, video_clips, and scenes stubs before Alembic
    runs, because mem_pacing_run/mem_decision have FKs to those tables but
    they are not part of any Alembic migration (they live in the main app
    schema bootstrapped by models.py).
    """
    from alembic import command
    from alembic.config import Config

    db_path = tmp_path / "mem.db"

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


def _seed_decision(engine: Any) -> tuple[int, int, int]:
    """Seed a run + 1 decision; return (run_id, scene_id, decision_id)."""
    with engine.begin() as conn:
        # Insert a video_clip so scenes FK resolves
        conn.execute(
            text(
                "INSERT INTO video_clips (id, file_path, original_filename, sha256, status, created_at) "
                "VALUES (1, '/v.mp4', 'v.mp4', 'y', 'ready', datetime('now'))"
            )
        )
        # Insert the scene that mem_decision will reference
        scene_id = 42
        conn.execute(
            text(
                "INSERT INTO scenes (id, video_clip_id, start_time, end_time) "
                "VALUES (:sid, 1, 0.0, 5.0)"
            ),
            {"sid": scene_id},
        )
        conn.execute(
            text(
                "INSERT INTO audio_tracks (id, file_path, original_filename, sha256, status, created_at) "
                "VALUES (1, '/f.mp3', 'f.mp3', 'x', 'ready', datetime('now'))"
            )
        )
        row = conn.execute(
            text(
                "INSERT INTO mem_pacing_run (audio_track_id, started_at, is_dj_mix, total_duration_sec, "
                "total_cuts, agent_version, weights_profile) VALUES "
                "(1, datetime('now'), 0, 120.0, 0, 'test', 'default') RETURNING id"
            )
        ).fetchone()
        assert row is not None
        run_id = int(row[0])
        row = conn.execute(
            text("""
            INSERT INTO mem_decision
            (run_id, sequence_idx, at_timestamp_sec, at_section_type, at_bpm, at_genre,
             at_enricher_version, scene_id, clip_role, clip_mood_refined, clip_style_bucket_id,
             agent_score, agent_rationale, user_verdict)
            VALUES (:rid, 0, 60.0, 'drop', 140.0, 'psytrance', :ver, :sid, 'hero', 'euphoric', 1,
                    0.7, '{}', NULL) RETURNING id
        """),
            {"rid": run_id, "ver": ENRICHER_VERSION, "sid": scene_id},
        ).fetchone()
        assert row is not None
        decision_id = int(row[0])
    return run_id, scene_id, decision_id


def test_feedback_service_accept(tmp_path: Path) -> None:
    engine, Session = _build_sqlite(tmp_path)
    run_id, scene_id, decision_id = _seed_decision(engine)

    svc = FeedbackService(session_factory=Session)
    result = svc.record_verdict(run_id, scene_id, "accept")
    assert result.success
    assert result.event_id is not None
    assert result.decision_id == decision_id

    # Verify mem_user_feedback_event row + mem_decision.user_verdict set
    with engine.begin() as conn:
        ev = (
            conn.execute(
                text(
                    "SELECT event_type FROM mem_user_feedback_event " "WHERE id = :id"
                ),
                {"id": result.event_id},
            )
            .mappings()
            .one()
        )
        assert ev["event_type"] == "accept"
        dec = (
            conn.execute(
                text("SELECT user_verdict FROM mem_decision " "WHERE id = :id"),
                {"id": decision_id},
            )
            .mappings()
            .one()
        )
        assert dec["user_verdict"] == "accept"


def test_feedback_service_reject(tmp_path: Path) -> None:
    engine, Session = _build_sqlite(tmp_path)
    run_id, scene_id, decision_id = _seed_decision(engine)
    svc = FeedbackService(session_factory=Session)
    result = svc.record_verdict(run_id, scene_id, "reject")
    assert result.success


def test_feedback_service_rating(tmp_path: Path) -> None:
    engine, Session = _build_sqlite(tmp_path)
    run_id, scene_id, decision_id = _seed_decision(engine)
    svc = FeedbackService(session_factory=Session)
    result = svc.record_rating(run_id, scene_id, 4)
    assert result.success

    with engine.begin() as conn:
        dec = (
            conn.execute(
                text("SELECT user_rating FROM mem_decision WHERE id = :id"),
                {"id": decision_id},
            )
            .mappings()
            .one()
        )
        assert dec["user_rating"] == 4


def test_feedback_service_missing_decision(tmp_path: Path) -> None:
    engine, Session = _build_sqlite(tmp_path)
    # No decision seeded
    svc = FeedbackService(session_factory=Session)
    result = svc.record_verdict(run_id=99, scene_id=99, verdict="accept")
    assert result.success is False
    assert result.error is not None


def test_feedback_service_does_not_clobber_existing_verdict(tmp_path: Path) -> None:
    """If user_verdict is already set, record_verdict MUST NOT overwrite it."""
    engine, Session = _build_sqlite(tmp_path)
    run_id, scene_id, decision_id = _seed_decision(engine)

    svc = FeedbackService(session_factory=Session)
    svc.record_verdict(run_id, scene_id, "accept")

    # Second call — user_verdict already 'accept', should stay that way.
    svc.record_verdict(run_id, scene_id, "reject")
    with engine.begin() as conn:
        dec = (
            conn.execute(
                text("SELECT user_verdict FROM mem_decision WHERE id = :id"),
                {"id": decision_id},
            )
            .mappings()
            .one()
        )
        assert dec["user_verdict"] == "accept"  # NOT reject

    # But a new mem_user_feedback_event row SHOULD exist for the reject
    with engine.begin() as conn:
        events = (
            conn.execute(
                text(
                    "SELECT event_type FROM mem_user_feedback_event WHERE decision_id = :id "
                    "ORDER BY id"
                ),
                {"id": decision_id},
            )
            .mappings()
            .all()
        )
        assert [e["event_type"] for e in events] == ["accept", "reject"]


def test_verdict_from_key_mapping() -> None:
    assert VERDICT_FROM_KEY == {"A": "accept", "R": "reject", "S": "skip"}


def test_invalid_verdict_returns_error(tmp_path: Path) -> None:
    engine, Session = _build_sqlite(tmp_path)
    _seed_decision(engine)
    svc = FeedbackService(session_factory=Session)
    result = svc.record_verdict(1, 42, "bogus")
    assert result.success is False
    assert result.error is not None


def test_invalid_rating_returns_error(tmp_path: Path) -> None:
    engine, Session = _build_sqlite(tmp_path)
    _seed_decision(engine)
    svc = FeedbackService(session_factory=Session)
    assert svc.record_rating(1, 42, 0).success is False
    assert svc.record_rating(1, 42, 6).success is False


def test_no_deprecated_utcnow_usage() -> None:
    source = Path("services/feedback_service.py").read_text(encoding="utf-8")
    assert "datetime.utcnow(" not in source


def test_timeline_module_still_imports() -> None:
    """Sanity: adding feedback shortcuts to ui/timeline.py didn't break the module."""
    import ui.timeline  # must import without error

    # The signal + method we added must exist
    assert hasattr(ui.timeline.InteractiveTimeline, "set_active_pacing_run")
    assert hasattr(ui.timeline.InteractiveTimeline, "feedback_event_emitted")
