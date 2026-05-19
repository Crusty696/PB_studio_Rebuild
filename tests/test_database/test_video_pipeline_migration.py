"""Video-Pipeline Tier-1 Phase-01: DB-Migration idempotent + vollstaendig.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 01 (Tier 1 Foundation)
Decision-Anker: D-045

Verifiziert dass ``_run_legacy_migrations()`` neue Spalten in
``video_clips`` und ``scenes`` ergaenzt + Indizes anlegt, **idempotent**
auf einer schon migrierten DB.

Pattern uebernommen aus
``test_database/test_schnitt_migrations_idempotent.py``.
"""
from sqlalchemy import create_engine, event, inspect

from database import migrations as migrations_mod
from database.models import Base


VIDEO_CLIPS_NEW_COLUMNS = {
    "video_pipeline_status",
    "video_pipeline_checkpoint_path",
    "stream_sha256",
    "embeddings_path",
    "motion_path",
    "proxy_status",
}

SCENES_NEW_COLUMNS = {
    "scene_index",
    "keyframe_paths",
    "embedding_indices",
}

EXPECTED_INDICES = {
    "ix_video_clips_stream_sha256",
    "ix_video_clips_pipeline_status",
    "ix_scenes_scene_index",
}


def _make_inmemory_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return eng


def test_video_pipeline_migration_adds_video_clips_columns(monkeypatch):
    eng = _make_inmemory_engine()
    Base.metadata.create_all(eng)

    monkeypatch.setattr(migrations_mod, "engine", eng)
    monkeypatch.setattr(migrations_mod, "get_raw_engine", lambda: eng)

    migrations_mod._run_legacy_migrations()

    insp = inspect(eng)
    vc_cols = {c["name"] for c in insp.get_columns("video_clips")}
    missing = VIDEO_CLIPS_NEW_COLUMNS - vc_cols
    assert not missing, (
        f"video_clips fehlende Spalten nach Migration: {sorted(missing)}"
    )


def test_video_pipeline_migration_adds_scenes_columns(monkeypatch):
    eng = _make_inmemory_engine()
    Base.metadata.create_all(eng)

    monkeypatch.setattr(migrations_mod, "engine", eng)
    monkeypatch.setattr(migrations_mod, "get_raw_engine", lambda: eng)

    migrations_mod._run_legacy_migrations()

    insp = inspect(eng)
    sc_cols = {c["name"] for c in insp.get_columns("scenes")}
    missing = SCENES_NEW_COLUMNS - sc_cols
    assert not missing, (
        f"scenes fehlende Spalten nach Migration: {sorted(missing)}"
    )


def test_video_pipeline_migration_creates_indices(monkeypatch):
    eng = _make_inmemory_engine()
    Base.metadata.create_all(eng)

    monkeypatch.setattr(migrations_mod, "engine", eng)
    monkeypatch.setattr(migrations_mod, "get_raw_engine", lambda: eng)

    migrations_mod._run_legacy_migrations()

    insp = inspect(eng)
    vc_idx = {i["name"] for i in insp.get_indexes("video_clips")}
    sc_idx = {i["name"] for i in insp.get_indexes("scenes")}
    all_idx = vc_idx | sc_idx
    missing = EXPECTED_INDICES - all_idx
    assert not missing, (
        f"Erwartete Indizes fehlen nach Migration: {sorted(missing)}"
    )


def test_video_pipeline_migration_is_idempotent(monkeypatch):
    eng = _make_inmemory_engine()
    Base.metadata.create_all(eng)

    monkeypatch.setattr(migrations_mod, "engine", eng)
    monkeypatch.setattr(migrations_mod, "get_raw_engine", lambda: eng)

    # Lauf 1 — fuegt Spalten + Indizes hinzu.
    migrations_mod._run_legacy_migrations()

    # Lauf 2 — darf nicht crashen, Schema unveraendert.
    migrations_mod._run_legacy_migrations()

    insp = inspect(eng)
    vc_cols = {c["name"] for c in insp.get_columns("video_clips")}
    sc_cols = {c["name"] for c in insp.get_columns("scenes")}
    assert VIDEO_CLIPS_NEW_COLUMNS <= vc_cols
    assert SCENES_NEW_COLUMNS <= sc_cols
