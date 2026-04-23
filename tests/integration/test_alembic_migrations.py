"""Integration tests: Alembic migration roundtrip — T1.4.

Tests both an empty-DB roundtrip and a populated-DB roundtrip for the three
new Studio-Brain migrations (T1.1, T1.2, T1.3).

The project's baseline schema was not created by Alembic migrations (the
initial migration is a no-op placeholder).  Instead the schema is created by
SQLAlchemy ``Base.metadata.create_all()``.  The populated-DB test therefore:

1. Creates the schema with ``create_all()``.
2. Stamps the DB at the last pre-Studio-Brain revision so Alembic knows the
   starting point.
3. Seeds a few rows.
4. Runs the three new migrations up → down → up and asserts invariants.

Run with:
    pytest tests/integration/test_alembic_migrations.py -v
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, event as sa_event, text as sa_text
from sqlalchemy.orm import Session

from database.models import Base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

#: Tables added by our three new migrations.
NEW_TABLES = [
    "struct_style_bucket",
    "struct_clip_tags",
    "struct_compat_edge",
    "mem_pacing_run",
    "mem_decision",
    "mem_learned_pattern",
    "mem_user_feedback_event",
]

#: The Alembic revision that corresponds to the state BEFORE Studio-Brain
#: migrations were added (last pre-T1.1 revision in the chain).
_LAST_GOOD_REVISION = "a3df65cc10b1"


def _make_alembic_cfg(db_path: Path) -> Config:
    """Return an Alembic Config pointing at the project ini but overriding the URL."""
    ini_path = Path(__file__).parent.parent.parent / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _make_engine(db_path: Path) -> "Engine":  # noqa: F821
    """Create a SQLAlchemy engine for the given SQLite path with FK support."""
    from sqlalchemy.engine import Engine as _Engine  # local import avoids circular refs

    eng: _Engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @sa_event.listens_for(eng, "connect")
    def _set_pragmas(dbapi_conn: object, _rec: object) -> None:
        cur = dbapi_conn.cursor()  # type: ignore[union-attr]
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

    return eng


def _tables_in_db(db_path: Path) -> list[str]:
    """Return sorted list of user table names in the SQLite file."""
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return sorted(r[0] for r in rows)


def _bootstrap_baseline_populated(db_path: Path, cfg: Config) -> None:
    """Create the baseline schema + seed rows, then stamp at the last good revision.

    Because the initial Alembic migration is an empty no-op placeholder, the
    real schema is produced by ``Base.metadata.create_all()``.  We create the
    schema, stamp the DB so Alembic knows the starting point, then insert seed
    rows so the T1.3 data-migration has something to process.
    """
    # 1. Create all tables via ORM metadata (mirrors production app startup).
    #    This creates the full baseline schema WITHOUT running any Alembic
    #    migrations (the initial migration is empty).
    engine = _make_engine(db_path)
    try:
        # Only create tables that belong to the baseline schema — NOT the
        # Studio-Brain tables (those are created by our migrations).
        studio_brain_tables = {
            "struct_clip_tags", "struct_style_bucket", "struct_compat_edge",
            "mem_pacing_run", "mem_decision", "mem_learned_pattern",
            "mem_user_feedback_event",
        }
        tables_to_create = [
            t for t in Base.metadata.sorted_tables
            if t.name not in studio_brain_tables
        ]
        Base.metadata.create_all(engine, tables=tables_to_create)
    finally:
        engine.dispose()

    # 2. Stamp the DB at the last pre-Studio-Brain revision so Alembic knows
    #    the starting point and won't try to run any earlier migrations.
    alembic_command.stamp(cfg, _LAST_GOOD_REVISION)

    # 3. Seed rows using plain sqlite3 (no SQLAlchemy session needed).
    #    FK constraints are NOT enforced by sqlite3 by default (no PRAGMA
    #    foreign_keys in plain sqlite3 connections), so insert order matters
    #    only for logical integrity, not enforcement.
    with sqlite3.connect(str(db_path)) as conn:
        # Project — required FK for audio_tracks and video_clips.
        # resolution and fps have defaults in the ORM but sqlite3 raw inserts
        # don't apply Python-level defaults, so provide them explicitly.
        conn.execute(
            "INSERT INTO projects (id, name, path, resolution, fps) "
            "VALUES (1, 'test_project', '/fake/project', '1920x1080', 30.0)"
        )
        # AudioTrack — referenced by AIPacingMemory.
        conn.execute(
            "INSERT INTO audio_tracks (id, project_id, file_path, duration, bpm) "
            "VALUES (1, 1, '/fake/track.wav', 120.0, 140.0)"
        )
        # VideoClip — parent of Scene.
        conn.execute(
            "INSERT INTO video_clips (id, project_id, file_path, duration, playback_offset) "
            "VALUES (1, 1, '/fake/clip.mp4', 30.0, 0.0)"
        )
        # Scenes — T1.1/T1.2 FKs reference scenes(id).
        for scene_id in (1, 2, 3):
            conn.execute(
                "INSERT INTO scenes (id, video_clip_id, start_time, end_time) "
                f"VALUES ({scene_id}, 1, {(scene_id - 1) * 5.0}, {scene_id * 5.0})"
            )
        # AIPacingMemory rows — imported by T1.3 into mem_learned_pattern.
        conn.execute(
            "INSERT INTO ai_pacing_memory "
            "(bpm, overall_energy, mood, section_type, audio_track_id, scene_id) "
            "VALUES (140.0, 0.8, 'drop', 'DROP', 1, 1)"
        )
        conn.execute(
            "INSERT INTO ai_pacing_memory "
            "(bpm, overall_energy, mood, section_type, audio_track_id, scene_id) "
            "VALUES (128.0, 0.5, 'buildup', 'BUILDUP', 1, 2)"
        )
        # analysis_status video row — so T1.3 can add structure_enrichment rows.
        conn.execute(
            "INSERT INTO analysis_status "
            "(media_type, media_id, step_key, status) "
            "VALUES ('video', 1, 'scene_db_storage', 'done')"
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_full_roundtrip_empty_db(tmp_path: Path) -> None:
    """All 3 new migrations up → down → up on an empty SQLite.

    After each 'up' phase the 7 new tables must exist.
    After 'down base' they must all be gone.
    """
    db_path = tmp_path / "pb_studio_test.db"
    cfg = _make_alembic_cfg(db_path)

    # ── First up (from empty DB — runs all migrations including baseline) ────
    alembic_command.upgrade(cfg, "head")
    tables_after_up = _tables_in_db(db_path)
    for t in NEW_TABLES:
        assert t in tables_after_up, f"Table {t!r} missing after first upgrade head"

    # ── Down to base ─────────────────────────────────────────────────────────
    alembic_command.downgrade(cfg, "base")
    tables_after_down = _tables_in_db(db_path)
    for t in NEW_TABLES:
        assert t not in tables_after_down, (
            f"Table {t!r} should be gone after downgrade base but is still present"
        )

    # ── Second up ────────────────────────────────────────────────────────────
    alembic_command.upgrade(cfg, "head")
    tables_after_second_up = _tables_in_db(db_path)
    for t in NEW_TABLES:
        assert t in tables_after_second_up, (
            f"Table {t!r} missing after second upgrade head"
        )


def test_full_roundtrip_populated_db(tmp_path: Path) -> None:
    """Migrations preserve existing Scene, AudioTrack, AIPacingMemory data.

    Seed a fresh DB with baseline schema + rows, run the 3 new migrations
    up/down/up, assert original rows still present with unchanged counts.
    """
    db_path = tmp_path / "pb_studio_test.db"
    cfg = _make_alembic_cfg(db_path)

    # ── Bootstrap baseline schema + seed rows ────────────────────────────────
    _bootstrap_baseline_populated(db_path, cfg)

    # Capture pre-migration row counts.
    with sqlite3.connect(str(db_path)) as conn:
        scenes_before = conn.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]
        tracks_before = conn.execute("SELECT COUNT(*) FROM audio_tracks").fetchone()[0]
        apm_before = conn.execute("SELECT COUNT(*) FROM ai_pacing_memory").fetchone()[0]

    assert scenes_before == 3, "Seed must have 3 scenes"
    assert tracks_before == 1, "Seed must have 1 audio track"
    assert apm_before == 2, "Seed must have 2 AIPacingMemory rows"

    # ── Run the 3 new migrations up ──────────────────────────────────────────
    alembic_command.upgrade(cfg, "head")

    tables_after_up = _tables_in_db(db_path)
    for t in NEW_TABLES:
        assert t in tables_after_up, f"Table {t!r} missing after upgrade head"

    # Original rows must still be intact.
    with sqlite3.connect(str(db_path)) as conn:
        scenes_mid = conn.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]
        tracks_mid = conn.execute("SELECT COUNT(*) FROM audio_tracks").fetchone()[0]
        apm_mid = conn.execute("SELECT COUNT(*) FROM ai_pacing_memory").fetchone()[0]

    assert scenes_mid == scenes_before, "scenes count changed after upgrade"
    assert tracks_mid == tracks_before, "audio_tracks count changed after upgrade"
    assert apm_mid == apm_before, "ai_pacing_memory count changed after upgrade"

    # T1.3 must have imported AIPacingMemory rows into mem_learned_pattern.
    with sqlite3.connect(str(db_path)) as conn:
        pattern_count = conn.execute(
            "SELECT COUNT(*) FROM mem_learned_pattern"
        ).fetchone()[0]
    assert pattern_count == apm_before, (
        f"Expected {apm_before} imported patterns, got {pattern_count}"
    )

    # T1.3 must have added structure_enrichment rows for existing videos.
    with sqlite3.connect(str(db_path)) as conn:
        se_count = conn.execute(
            "SELECT COUNT(*) FROM analysis_status "
            "WHERE step_key='structure_enrichment' AND media_type='video'"
        ).fetchone()[0]
    assert se_count >= 1, "No structure_enrichment rows added by T1.3"

    # ── Down (only the 3 new Studio-Brain migrations) ────────────────────────
    alembic_command.downgrade(cfg, _LAST_GOOD_REVISION)

    tables_after_down = _tables_in_db(db_path)
    for t in NEW_TABLES:
        assert t not in tables_after_down, (
            f"Table {t!r} should be gone after downgrade but is still present"
        )

    # Original rows must still be intact after downgrade.
    with sqlite3.connect(str(db_path)) as conn:
        scenes_after = conn.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]
        tracks_after = conn.execute("SELECT COUNT(*) FROM audio_tracks").fetchone()[0]
        apm_after = conn.execute("SELECT COUNT(*) FROM ai_pacing_memory").fetchone()[0]

    assert scenes_after == scenes_before, "scenes count changed after downgrade"
    assert tracks_after == tracks_before, "audio_tracks count changed after downgrade"
    assert apm_after == apm_before, (
        "ai_pacing_memory rows were deleted by downgrade — must be preserved"
    )

    # ── Second up ────────────────────────────────────────────────────────────
    alembic_command.upgrade(cfg, "head")

    tables_after_second_up = _tables_in_db(db_path)
    for t in NEW_TABLES:
        assert t in tables_after_second_up, (
            f"Table {t!r} missing after second upgrade head"
        )

    # Original rows must still be intact after second up.
    with sqlite3.connect(str(db_path)) as conn:
        scenes_final = conn.execute("SELECT COUNT(*) FROM scenes").fetchone()[0]
        tracks_final = conn.execute("SELECT COUNT(*) FROM audio_tracks").fetchone()[0]
        apm_final = conn.execute("SELECT COUNT(*) FROM ai_pacing_memory").fetchone()[0]

    assert scenes_final == scenes_before, "scenes count changed after second upgrade"
    assert tracks_final == tracks_before, "audio_tracks count changed after second upgrade"
    assert apm_final == apm_before, "ai_pacing_memory count changed after second upgrade"
