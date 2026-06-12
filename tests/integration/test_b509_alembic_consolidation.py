"""B-509 (CRF-011): Alembic-Konsolidierung — Revision d4e5f6a7b8c9.

Seit c3d4e5f6a7b8 (2026-04-30) lebten neuere Schema-Teile NUR als
Hand-ALTERs in ``database/migrations.py`` (locked, timeline_snapshots,
project_notes, video_pipeline-Spalten). Die Konsolidierungs-Revision
macht die Alembic-Kette wieder zur vollstaendigen Schema-Wahrheit.

Test 1: Frische DB NUR via ``alembic upgrade head`` -> Inspector-Vergleich
gegen ``Base.metadata``: keine fehlenden Tabellen/Spalten (Alembic-only-
Artefakte wie alembic_version/struct_*/mem_*/brain_* werden ignoriert —
die leben bewusst nicht in database/models.py).

Test 2: DB, die die Hand-ALTERs bereits hat (simuliert via
``Base.metadata.create_all`` — derselbe End-Zustand, den
``_run_legacy_migrations`` herstellt), gestempelt auf c3d4e5f6a7b8 ->
``upgrade head`` laeuft idempotent durch, kein Fehler, Schema vollstaendig;
zweiter ``upgrade head`` ist ein No-Op.
"""
from __future__ import annotations

from pathlib import Path

from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from database.models import Base

_REPO_ROOT = Path(__file__).parent.parent.parent

#: Revision VOR der Konsolidierung (bisheriger Head).
_PRE_CONSOLIDATION_HEAD = "c3d4e5f6a7b8"


def _make_alembic_cfg(db_path: Path) -> Config:
    cfg = Config(str(_REPO_ROOT / "alembic.ini"))
    cfg.set_main_option(
        "script_location", str(_REPO_ROOT / "database" / "alembic")
    )
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def _schema_diff_models_vs_db(db_path: Path) -> list[str]:
    """Liefert Liste menschenlesbarer Diffs (models -> DB Richtung)."""
    eng = create_engine(f"sqlite:///{db_path}")
    try:
        insp = inspect(eng)
        db_tables = set(insp.get_table_names())
        model_tables = set(Base.metadata.tables.keys())
        problems: list[str] = []

        for t in sorted(model_tables - db_tables):
            problems.append(f"Tabelle fehlt in DB: {t}")

        for t in sorted(model_tables & db_tables):
            db_cols = {c["name"] for c in insp.get_columns(t)}
            model_cols = set(Base.metadata.tables[t].columns.keys())
            for c in sorted(model_cols - db_cols):
                problems.append(f"Spalte fehlt in DB: {t}.{c}")
        return problems
    finally:
        eng.dispose()


def test_fresh_db_alembic_only_matches_models(tmp_path: Path) -> None:
    """Frische DB nur via Alembic (upgrade head) deckt Base.metadata ab."""
    db_path = tmp_path / "b509_fresh.db"
    cfg = _make_alembic_cfg(db_path)

    alembic_command.upgrade(cfg, "head")

    problems = _schema_diff_models_vs_db(db_path)
    assert problems == [], (
        "B-509: Alembic-Head deckt models.py nicht ab:\n" + "\n".join(problems)
    )

    # Kernstuecke der Konsolidierung explizit pruefen
    eng = create_engine(f"sqlite:///{db_path}")
    try:
        insp = inspect(eng)
        tables = set(insp.get_table_names())
        assert "timeline_snapshots" in tables
        assert "project_notes" in tables
        te_cols = {c["name"] for c in insp.get_columns("timeline_entries")}
        assert "locked" in te_cols
        vc_cols = {c["name"] for c in insp.get_columns("video_clips")}
        for col in (
            "video_pipeline_status", "video_pipeline_checkpoint_path",
            "stream_sha256", "embeddings_path", "motion_path", "proxy_status",
        ):
            assert col in vc_cols, f"video_clips.{col} fehlt"
        sc_cols = {c["name"] for c in insp.get_columns("scenes")}
        for col in ("scene_index", "keyframe_paths", "embedding_indices"):
            assert col in sc_cols, f"scenes.{col} fehlt"
        ts_idx = {i["name"] for i in insp.get_indexes("timeline_snapshots")}
        assert "idx_snapshot_project_version" in ts_idx
    finally:
        eng.dispose()


def test_upgrade_idempotent_on_db_with_hand_alters(tmp_path: Path) -> None:
    """Bestands-DB (Hand-ALTERs vorhanden) + upgrade head -> kein Fehler.

    Simulation des migrations.py-Endzustands: ``Base.metadata.create_all``
    erzeugt exakt das Schema, das ``_run_legacy_migrations`` auf einer
    Bestands-DB herstellt (inkl. locked, timeline_snapshots, project_notes,
    video_pipeline-Spalten). Gestempelt auf den Vor-Konsolidierungs-Head —
    die neue Revision muss alles per Inspector-Check ueberspringen.
    """
    db_path = tmp_path / "b509_existing.db"
    cfg = _make_alembic_cfg(db_path)

    eng = create_engine(f"sqlite:///{db_path}")
    try:
        Base.metadata.create_all(eng)
    finally:
        eng.dispose()

    # DB kennt Alembic bis zum bisherigen Head (wie produktive Bestands-DBs)
    alembic_command.stamp(cfg, _PRE_CONSOLIDATION_HEAD)

    # Konsolidierungs-Revision laeuft — darf NICHT crashen (idempotent)
    alembic_command.upgrade(cfg, "head")

    problems = _schema_diff_models_vs_db(db_path)
    assert problems == [], (
        "B-509: Schema nach idempotentem upgrade unvollstaendig:\n"
        + "\n".join(problems)
    )

    # Zweiter upgrade head -> No-Op, ebenfalls fehlerfrei
    alembic_command.upgrade(cfg, "head")
