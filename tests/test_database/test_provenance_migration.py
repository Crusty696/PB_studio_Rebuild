from pathlib import Path
import sqlite3

from alembic import command
from alembic.config import Config


EXPECTED_TABLES = {
    "analysis_jobs",
    "analysis_artifacts",
    "step_deps",
    "project_sources",
}


def _alembic_cfg(db_path: Path) -> Config:
    cfg = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return {row[0] for row in rows}


def _columns(db_path: Path, table: str) -> set[str]:
    with sqlite3.connect(str(db_path)) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _indexes(db_path: Path, table: str) -> set[str]:
    with sqlite3.connect(str(db_path)) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA index_list({table})").fetchall()}


def test_provenance_migration_creates_tables_and_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "pb_studio.db"

    command.upgrade(_alembic_cfg(db_path), "head")

    assert EXPECTED_TABLES <= _tables(db_path)
    assert {
        "source_sha256",
        "step_id",
        "step_version",
        "params_hash",
        "status",
        "produced_by_model",
        "produced_by_model_version",
        "coverage_percent",
        "started_at",
        "finished_at",
        "duration_seconds",
        "error",
    } <= _columns(db_path, "analysis_jobs")
    assert {
        "job_id",
        "artifact_type",
        "artifact_role",
        "path",
        "bytes",
        "sha256",
    } <= _columns(db_path, "analysis_artifacts")
    assert {
        "project_id",
        "source_sha256",
        "current_source_path",
        "last_seen_at",
    } <= _columns(db_path, "project_sources")


def test_provenance_migration_constraints_and_cascade(tmp_path: Path) -> None:
    db_path = tmp_path / "pb_studio.db"
    command.upgrade(_alembic_cfg(db_path), "head")

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO projects (id, name, path, resolution, fps) "
            "VALUES (1, 'p', '/tmp/p', '1920x1080', 30.0)"
        )
        conn.execute(
            "INSERT INTO analysis_jobs "
            "(id, source_sha256, step_id, step_version, params_hash, status) "
            "VALUES (1, 'a' || hex(zeroblob(31)), 'audio.v2.stems', '1', 'p1', 'done')"
        )
        conn.execute(
            "INSERT INTO analysis_artifacts "
            "(job_id, artifact_type, artifact_role, path, bytes, sha256) "
            "VALUES (1, 'stem', 'vocals_stem', 'audio/stems/vocals.flac', 12, 'b')"
        )
        conn.execute(
            "INSERT INTO project_sources "
            "(project_id, source_sha256, current_source_path) "
            "VALUES (1, 'a' || hex(zeroblob(31)), '/tmp/p/source.wav')"
        )

        try:
            conn.execute(
                "INSERT INTO analysis_jobs "
                "(source_sha256, step_id, step_version, params_hash, status) "
                "VALUES ('a' || hex(zeroblob(31)), 'audio.v2.stems', '1', 'p1', 'done')"
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("analysis_jobs unique constraint missing")

        conn.execute("DELETE FROM analysis_jobs WHERE id = 1")
        artifact_count = conn.execute("SELECT COUNT(*) FROM analysis_artifacts").fetchone()[0]
        assert artifact_count == 0


def test_provenance_migration_is_idempotent_via_second_upgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "pb_studio.db"
    cfg = _alembic_cfg(db_path)

    command.upgrade(cfg, "head")
    command.upgrade(cfg, "head")

    assert "uq_analysis_jobs_identity" in _indexes(db_path, "analysis_jobs")
    assert "uq_project_sources_project_source" in _indexes(db_path, "project_sources")
