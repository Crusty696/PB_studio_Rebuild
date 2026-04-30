from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from services.brain_v2.indexer import BrainIndexer
from services.brain_v2.store import ensure_brain_v2_schema


def _build_db(tmp_path: Path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'brain_v2_index.db').as_posix()}", future=True)
    ensure_brain_v2_schema(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE audio_tracks (id INTEGER PRIMARY KEY, file_path TEXT, title TEXT, duration REAL, bpm REAL, mood TEXT, genre TEXT, energy_curve TEXT)"))
        conn.execute(text("CREATE TABLE structure_segments (id INTEGER PRIMARY KEY, audio_track_id INTEGER, start_time REAL, end_time REAL, label TEXT, energy REAL, confidence REAL)"))
        conn.execute(text("CREATE TABLE video_clips (id INTEGER PRIMARY KEY, file_path TEXT, duration REAL)"))
        conn.execute(text("CREATE TABLE scenes (id INTEGER PRIMARY KEY, video_clip_id INTEGER, start_time REAL, end_time REAL, label TEXT, energy REAL, ai_mood TEXT)"))
        conn.execute(text("CREATE TABLE struct_style_bucket (id INTEGER PRIMARY KEY, name TEXT, description TEXT, member_count INTEGER, active INTEGER DEFAULT 1)"))
        conn.execute(text("CREATE TABLE struct_clip_tags (scene_id INTEGER PRIMARY KEY, role TEXT, role_confidence REAL, mood_refined TEXT, mood_confidence REAL, style_bucket_id INTEGER, style_distance REAL)"))
        conn.execute(text("INSERT INTO audio_tracks VALUES (1, 'track.wav', 'Track A', 120.0, 128.0, 'dark', 'techno', '[0.1, 0.9]')"))
        conn.execute(text("INSERT INTO structure_segments VALUES (11, 1, 0.0, 32.0, 'WARMUP', 0.2, 0.7), (12, 1, 32.0, 64.0, 'DROP', 0.9, 0.8)"))
        conn.execute(text("INSERT INTO video_clips VALUES (2, 'clip.mp4', 12.0)"))
        conn.execute(text("INSERT INTO scenes VALUES (21, 2, 0.0, 4.0, 'Scene 0', 0.6, 'energetic'), (22, 2, 4.0, 8.0, 'Scene 1', 0.3, 'calm')"))
        conn.execute(text("INSERT INTO struct_style_bucket VALUES (5, 'strobe', 'fast lights', 2, 1)"))
        conn.execute(text("INSERT INTO struct_clip_tags VALUES (21, 'hero', 0.9, 'euphoric', 0.8, 5, 0.2)"))
    return engine, sessionmaker(bind=engine)


def test_index_project_creates_entities_and_tag_facts(tmp_path: Path) -> None:
    engine, Session = _build_db(tmp_path)
    report = BrainIndexer(Session).index_project()

    assert report.entities_upserted >= 5
    assert report.facts_added >= 5
    with engine.begin() as conn:
        entities = conn.execute(text("SELECT entity_type, source_table, source_id FROM brain_entity")).fetchall()
        facts = conn.execute(text("SELECT key FROM brain_fact")).fetchall()
    assert ("track", "audio_tracks", 1) in entities
    assert ("section", "structure_segments", 12) in entities
    assert ("scene", "scenes", 21) in entities
    assert ("role",) in facts
    assert ("mood",) in facts


def test_index_project_survives_missing_optional_struct_tables(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{(tmp_path / 'minimal.db').as_posix()}", future=True)
    ensure_brain_v2_schema(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE audio_tracks (id INTEGER PRIMARY KEY, file_path TEXT, title TEXT)"))
        conn.execute(text("INSERT INTO audio_tracks VALUES (1, 'track.wav', NULL)"))
    report = BrainIndexer(sessionmaker(bind=engine)).index_project()
    assert report.entities_upserted == 1
    assert report.errors == []
