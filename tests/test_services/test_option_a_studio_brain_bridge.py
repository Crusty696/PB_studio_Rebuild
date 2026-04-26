"""Cycle 14 / Option A: Studio-Brain Bridge fertig verdrahtet.

Verifiziert:
- Migration b2c3d4e5f6a7 fügt 3 Spalten zu audio_tracks hinzu
- bridge_mapping.build_audio_context liest die neuen Spalten
- bridge_mapping liest groove_template via beatgrid-Relationship
- pacing_service._select_scene_for_offset wählt korrekte Scene
"""
from __future__ import annotations

import importlib
import inspect
import sqlite3
from pathlib import Path

import numpy as np
import pytest


MIGRATION_MODULE = (
    "database.alembic.versions."
    "2026_04_26_b2c3d4e5f6a7_audio_track_studio_brain_columns"
)


# ── Migration ─────────────────────────────────────────────────────────────


def test_migration_module_loads():
    mod = importlib.import_module(MIGRATION_MODULE)
    assert mod.revision == "b2c3d4e5f6a7"
    assert mod.down_revision == "a1b2c3d4e5f6"
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def _build_minimal_audio_tracks(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE audio_tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            title TEXT,
            bpm REAL,
            harmonic_tension_curve TEXT
        )
        """
    )
    con.commit()


def _column_exists(con: sqlite3.Connection, table: str, column: str) -> bool:
    cur = con.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def test_migration_adds_three_studio_brain_columns(tmp_path):
    db_path = tmp_path / "ab_test.sqlite"
    con = sqlite3.connect(db_path)
    _build_minimal_audio_tracks(con)
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
        finally:
            alembic_op_module._proxy = None
        conn.commit()

    con = sqlite3.connect(db_path)
    try:
        for col in ("sub_genre", "spectral_hash", "harmonic_tension"):
            assert _column_exists(con, "audio_tracks", col), f"Column {col} missing"
    finally:
        con.close()


def test_migration_idempotent(tmp_path):
    db_path = tmp_path / "ab_idem.sqlite"
    con = sqlite3.connect(db_path)
    _build_minimal_audio_tracks(con)
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
            mod.upgrade()  # Doppelt — darf nicht crashen
        finally:
            alembic_op_module._proxy = None
        conn.commit()

    con = sqlite3.connect(db_path)
    try:
        for col in ("sub_genre", "spectral_hash", "harmonic_tension"):
            assert _column_exists(con, "audio_tracks", col)
    finally:
        con.close()


# ── bridge_mapping erweitert ──────────────────────────────────────────────


class _StubAudioTrack:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _StubBeatgrid:
    def __init__(self, groove_template: str | None = None):
        self.groove_template = groove_template


def test_bridge_mapping_reads_new_scalar_columns():
    """bridge_mapping nutzt jetzt audio_track.sub_genre / spectral_hash /
    harmonic_tension Skalar-Spalten."""
    from services.pacing.bridge_mapping import build_audio_context

    track = _StubAudioTrack(
        bpm=128.0, key="Am", mood="energetic", genre="psytrance",
        sub_genre="progressive_psy",
        spectral_hash="hash_abc",
        harmonic_tension=0.65,
        beatgrid=_StubBeatgrid(groove_template="fotf"),
    )
    ctx = build_audio_context(
        seg_start_sec=1.0, seg_section_type="drop",
        audio_track=track, beats=np.array([0.0, 0.5, 1.0, 1.5]),
        energy_per_beat=[0.2, 0.5, 0.9, 0.8],
    )
    assert ctx.at_sub_genre == "progressive_psy"
    assert ctx.at_spectral_hash == "hash_abc"
    assert abs(ctx.at_harmonic_tension - 0.65) < 1e-6
    assert ctx.at_groove_template == "fotf"


def test_bridge_mapping_falls_back_to_curve_when_no_scalar():
    from services.pacing.bridge_mapping import build_audio_context

    track = _StubAudioTrack(
        bpm=128.0,
        harmonic_tension_curve=[0.1, 0.4, 0.7, 0.9],
    )
    # beat_idx will be 2 (seg_start=1.0 with beats [0,0.5,1.0,1.5])
    ctx = build_audio_context(
        seg_start_sec=1.0, seg_section_type="drop",
        audio_track=track, beats=np.array([0.0, 0.5, 1.0, 1.5]),
        energy_per_beat=[0.2, 0.5, 0.9, 0.8],
    )
    # Tension von Curve[2] = 0.7
    assert abs(ctx.at_harmonic_tension - 0.7) < 1e-6


def test_bridge_mapping_groove_template_via_beatgrid():
    """groove_template lebt auf audio_track.beatgrid (lazy=joined)."""
    from services.pacing.bridge_mapping import build_audio_context

    track = _StubAudioTrack(
        bpm=128.0,
        beatgrid=_StubBeatgrid(groove_template="techno_4on4"),
    )
    ctx = build_audio_context(
        seg_start_sec=0.0, seg_section_type=None,
        audio_track=track, beats=np.array([0.0]),
        energy_per_beat=[0.5],
    )
    assert ctx.at_groove_template == "techno_4on4"


def test_bridge_mapping_no_beatgrid_groove_template_none():
    from services.pacing.bridge_mapping import build_audio_context

    track = _StubAudioTrack(bpm=128.0)  # kein beatgrid attribute
    ctx = build_audio_context(
        seg_start_sec=0.0, seg_section_type=None,
        audio_track=track, beats=np.array([0.0]),
        energy_per_beat=[0.5],
    )
    assert ctx.at_groove_template is None


# ── Scene-Selection ───────────────────────────────────────────────────────


def test_select_scene_for_offset_finds_matching_scene():
    from services.pacing_service import _select_scene_for_offset

    scenes = [
        {"id": 1, "start": 0.0, "end": 2.0, "ai_mood": "calm"},
        {"id": 2, "start": 2.0, "end": 5.0, "ai_mood": "energetic"},
        {"id": 3, "start": 5.0, "end": 8.0, "ai_mood": "dramatic"},
    ]
    sc = _select_scene_for_offset(scenes, offset_sec=3.5)
    assert sc["id"] == 2
    assert sc["ai_mood"] == "energetic"


def test_select_scene_for_offset_handles_offset_at_boundary():
    from services.pacing_service import _select_scene_for_offset
    scenes = [
        {"id": 1, "start": 0.0, "end": 2.0},
        {"id": 2, "start": 2.0, "end": 5.0},
    ]
    # Exact boundary: 2.0 → scene 2 (start <= offset < end)
    sc = _select_scene_for_offset(scenes, offset_sec=2.0)
    assert sc["id"] == 2


def test_select_scene_for_offset_zero_offset_picks_first():
    from services.pacing_service import _select_scene_for_offset
    scenes = [
        {"id": 1, "start": 0.0, "end": 2.0},
        {"id": 2, "start": 2.0, "end": 5.0},
    ]
    sc = _select_scene_for_offset(scenes, offset_sec=0.0)
    assert sc["id"] == 1


def test_select_scene_for_offset_past_end_picks_last():
    from services.pacing_service import _select_scene_for_offset
    scenes = [
        {"id": 1, "start": 0.0, "end": 2.0},
        {"id": 2, "start": 2.0, "end": 5.0},
    ]
    # Offset jenseits des letzten Scene-Ends → letzter Fallback
    sc = _select_scene_for_offset(scenes, offset_sec=99.0)
    assert sc["id"] == 2


def test_select_scene_for_offset_empty_scenes_returns_empty_dict():
    from services.pacing_service import _select_scene_for_offset
    sc = _select_scene_for_offset([], offset_sec=1.0)
    assert sc == {}


def test_select_scene_for_offset_handles_start_time_alias():
    """Manche scenes verwenden start_time/end_time statt start/end."""
    from services.pacing_service import _select_scene_for_offset
    scenes = [
        {"id": 1, "start_time": 0.0, "end_time": 2.0},
        {"id": 2, "start_time": 2.0, "end_time": 5.0},
    ]
    sc = _select_scene_for_offset(scenes, offset_sec=3.0)
    assert sc["id"] == 2


# ── Integration: pacing_service Studio-Brain-Pfad nutzt _select_scene ─────


def test_pacing_service_uses_select_scene_in_studio_brain_path():
    """Source-Inspektion: Studio-Brain-Cut-Loop ruft _select_scene_for_offset."""
    from services import pacing_service
    src = inspect.getsource(pacing_service._auto_edit_phase3_inner)
    assert "_select_scene_for_offset" in src
    # Und der alte _scenes[0]-Pattern darf nicht mehr im Studio-Brain-Block sein
    # (aber Anchor-Pfad nutzt ihn ggf. weiterhin → wir prüfen auf Build-Block)
    sb_block_idx = src.find("_sb_candidates = []")
    assert sb_block_idx > 0
    sb_block = src[sb_block_idx:sb_block_idx + 1500]
    assert "_select_scene_for_offset" in sb_block
    # Der unkonditionale _scenes[0] sollte im SB-Block weg sein
    assert "_sc = _scenes[0]" not in sb_block
