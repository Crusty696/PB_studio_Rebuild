from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from services.brain_v2.store import BrainStore, ensure_brain_v2_schema


def _session_factory(tmp_path: Path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'brain_v2.db').as_posix()}", future=True)
    ensure_brain_v2_schema(engine)
    return engine, sessionmaker(bind=engine)


def test_upsert_entity_deduplicates_and_updates_metadata(tmp_path: Path) -> None:
    engine, Session = _session_factory(tmp_path)
    store = BrainStore(Session)

    first_id = store.upsert_entity(
        entity_type="scene",
        source_table="scenes",
        source_id=7,
        title="Scene 7",
        summary="first",
        metadata={"mood": "calm"},
    )
    second_id = store.upsert_entity(
        entity_type="scene",
        source_table="scenes",
        source_id=7,
        title="Scene 7 updated",
        summary="second",
        metadata={"mood": "energetic"},
    )

    assert second_id == first_id
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT title, summary, metadata_json FROM brain_entity WHERE id = :id"),
            {"id": first_id},
        ).fetchone()
    assert row is not None
    assert row[0] == "Scene 7 updated"
    assert row[1] == "second"
    assert json.loads(row[2]) == {"mood": "energetic"}


def test_add_fact_and_record_decision_roundtrip_json(tmp_path: Path) -> None:
    engine, Session = _session_factory(tmp_path)
    store = BrainStore(Session)
    audio_id = store.upsert_entity("track", "audio_tracks", 1, "Track", "", {})
    clip_id = store.upsert_entity("scene", "scenes", 2, "Scene", "", {})

    fact_id = store.add_fact(
        entity_id=clip_id,
        fact_type="clip_tag",
        key="mood",
        value={"label": "euphoric"},
        confidence=0.8,
        source="test",
    )
    decision_id = store.record_decision(
        run_id=10,
        decision_id=20,
        audio_entity_id=audio_id,
        clip_entity_id=clip_id,
        why_json={"audio": {"section": "DROP"}, "clip": {"scene_id": 2}},
        why_text="DROP needs an energetic scene.",
    )

    with engine.begin() as conn:
        fact = conn.execute(
            text("SELECT value_json, confidence FROM brain_fact WHERE id = :id"),
            {"id": fact_id},
        ).fetchone()
        decision = conn.execute(
            text("SELECT why_json, why_text FROM brain_decision WHERE id = :id"),
            {"id": decision_id},
        ).fetchone()

    assert fact is not None
    assert json.loads(fact[0]) == {"label": "euphoric"}
    assert abs(fact[1] - 0.8) < 1e-6
    assert decision is not None
    assert json.loads(decision[0])["audio"]["section"] == "DROP"
    assert decision[1] == "DROP needs an energetic scene."


def test_import_knowledge_notes_is_idempotent(tmp_path: Path) -> None:
    engine, Session = _session_factory(tmp_path)
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "pacing_rules.md").write_text("# Pacing\n\nUse drops.", encoding="utf-8")

    store = BrainStore(Session)
    first = store.import_knowledge_notes(knowledge_dir)
    second = store.import_knowledge_notes(knowledge_dir)

    assert first.imported_count == 1
    assert second.imported_count == 1
    with engine.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM brain_note")).scalar()
    assert count == 1
