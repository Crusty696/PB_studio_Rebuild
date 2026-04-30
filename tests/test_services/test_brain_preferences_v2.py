from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from services.brain_v2.preferences import BrainPreferenceService, VALID_FEEDBACK_TYPES
from services.brain_v2.store import BrainStore, ensure_brain_v2_schema


def _setup(tmp_path: Path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'prefs.db').as_posix()}", future=True)
    ensure_brain_v2_schema(engine)
    Session = sessionmaker(bind=engine)
    store = BrainStore(Session)
    audio_id = store.upsert_entity("section", "structure_segments", 1, "DROP", "", {"section_type": "DROP"})
    clip_id = store.upsert_entity("scene", "scenes", 2, "Scene", "", {"role": "hero", "mood": "euphoric"})
    brain_decision_id = store.record_decision(
        run_id=1,
        decision_id=100,
        audio_entity_id=audio_id,
        clip_entity_id=clip_id,
        why_json={"audio": {"section": "DROP"}, "clip": {"role": "hero", "mood": "euphoric"}},
        why_text="test",
    )
    return engine, Session, brain_decision_id


def test_valid_feedback_types_are_fixed() -> None:
    assert VALID_FEEDBACK_TYPES == {
        "fits",
        "wrong_mood",
        "too_hectic",
        "too_calm",
        "wrong_moment",
        "too_repetitive",
        "visual_mismatch",
        "drop_needs_more_impact",
    }


def test_record_feedback_updates_memory_scopes(tmp_path: Path) -> None:
    engine, Session, brain_decision_id = _setup(tmp_path)
    update = BrainPreferenceService(Session).record_feedback(
        decision_id=brain_decision_id,
        feedback_type="fits",
        comment="works",
    )
    assert update.updated_count >= 3

    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT scope, positive_count, negative_count, payload_json FROM brain_memory")
        ).fetchall()
    scopes = {r[0] for r in rows}
    assert "global" in scopes
    assert "section:DROP" in scopes
    assert "clip_role:hero" in scopes
    assert all(r[1] == 1 for r in rows)
    assert all(r[2] == 0 for r in rows)
    assert any(json.loads(r[3])["last_feedback_type"] == "fits" for r in rows)


def test_negative_feedback_increments_negative_count(tmp_path: Path) -> None:
    engine, Session, brain_decision_id = _setup(tmp_path)
    svc = BrainPreferenceService(Session)
    svc.record_feedback(brain_decision_id, "wrong_mood")
    svc.record_feedback(brain_decision_id, "wrong_mood")

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT positive_count, negative_count, confidence FROM brain_memory WHERE scope = 'global'")
        ).fetchone()
    assert row is not None
    assert row[0] == 0
    assert row[1] == 2
    assert 0.0 <= row[2] <= 1.0
