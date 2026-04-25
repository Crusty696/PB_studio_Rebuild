"""P1.3: Migration `a1b2c3d4e5f6` fügt reward + reward_components zu mem_decision."""
from __future__ import annotations

import importlib
import sqlite3
import tempfile
from pathlib import Path

import pytest


MIGRATION_MODULE = (
    "database.alembic.versions."
    "2026_04_26_a1b2c3d4e5f6_add_reward_components_to_mem_decision"
)


def test_migration_module_loads():
    mod = importlib.import_module(MIGRATION_MODULE)
    assert mod.revision == "a1b2c3d4e5f6"
    assert mod.down_revision == "e670c6bc097c"
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def _build_minimal_mem_decision_table(con: sqlite3.Connection) -> None:
    """Mini-Tabelle die genug ist um die Migration zu testen."""
    con.execute(
        """
        CREATE TABLE mem_decision (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            sequence_idx INTEGER NOT NULL,
            at_timestamp_sec REAL NOT NULL,
            scene_id INTEGER NOT NULL,
            clip_role TEXT NOT NULL,
            clip_mood_refined TEXT NOT NULL,
            clip_style_bucket_id INTEGER NOT NULL,
            agent_score REAL NOT NULL,
            agent_rationale TEXT NOT NULL,
            user_verdict TEXT
        )
        """
    )
    con.commit()


def _column_exists(con: sqlite3.Connection, table: str, column: str) -> bool:
    cur = con.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def test_migration_adds_reward_columns(tmp_path):
    """Smoke-Test: führe upgrade() in einer Test-DB und verifiziere Spalten."""
    db_path = tmp_path / "test.sqlite"
    con = sqlite3.connect(db_path)
    _build_minimal_mem_decision_table(con)
    assert not _column_exists(con, "mem_decision", "reward")
    assert not _column_exists(con, "mem_decision", "reward_components")
    con.close()

    # Migration manuell mit SQLAlchemy-Engine + Alembic-Op laufen lassen
    from sqlalchemy import create_engine
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)
        # Op-context für den Migration-Code injecten
        from alembic import op as alembic_op_module
        alembic_op_module._proxy = op
        try:
            mod = importlib.import_module(MIGRATION_MODULE)
            mod.upgrade()
        finally:
            alembic_op_module._proxy = None
        conn.commit()

    con = sqlite3.connect(db_path)
    try:
        assert _column_exists(con, "mem_decision", "reward")
        assert _column_exists(con, "mem_decision", "reward_components")

        # Insert + Read-Back: NULL-Werte erlaubt
        con.execute(
            """
            INSERT INTO mem_decision (
                run_id, sequence_idx, at_timestamp_sec, scene_id,
                clip_role, clip_mood_refined, clip_style_bucket_id,
                agent_score, agent_rationale, reward, reward_components
            ) VALUES (1, 1, 0.0, 100, 'hero', 'energetic', 3, 0.5, '{}',
                      0.85, '{"r_energy": 0.7, "r_mood": 0.9}')
            """
        )
        con.commit()
        row = con.execute("SELECT reward, reward_components FROM mem_decision").fetchone()
        assert row is not None
        assert abs(row[0] - 0.85) < 1e-6
        assert "r_energy" in row[1]
    finally:
        con.close()


def test_migration_idempotent(tmp_path):
    """Doppelter upgrade() darf nicht crashen — _column_exists guard greift."""
    db_path = tmp_path / "test_idem.sqlite"
    con = sqlite3.connect(db_path)
    _build_minimal_mem_decision_table(con)
    con.close()

    from sqlalchemy import create_engine
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from alembic import op as alembic_op_module

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)
        alembic_op_module._proxy = op
        try:
            mod = importlib.import_module(MIGRATION_MODULE)
            mod.upgrade()
            # Zweimal — darf nicht crashen
            mod.upgrade()
        finally:
            alembic_op_module._proxy = None
        conn.commit()

    con = sqlite3.connect(db_path)
    try:
        assert _column_exists(con, "mem_decision", "reward")
        assert _column_exists(con, "mem_decision", "reward_components")
    finally:
        con.close()
