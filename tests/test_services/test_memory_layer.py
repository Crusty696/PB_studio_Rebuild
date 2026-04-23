import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database.models import Base, MemPacingRun, MemDecision, MemLearnedPattern, MemUserFeedbackEvent
from services.memory.decision_recorder import DecisionRecorder
from services.memory.pattern_aggregator import PatternAggregator

from unittest.mock import patch, MagicMock

@pytest.fixture
def test_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_decision_recording_and_aggregation(test_db):
    """Prüft, ob Entscheidungen gespeichert und zu Patterns aggregiert werden können."""
    recorder = DecisionRecorder()
    aggregator = PatternAggregator()
    
    # 1. Simulate a Pacing Run
    run = MemPacingRun(id=1, audio_track_id=1, is_dj_mix=False)
    test_db.add(run)
    test_db.commit()
    
    # Mock nullpool_session to use our test memory DB
    with patch("services.memory.decision_recorder.nullpool_session", return_value=MagicMock(__enter__=lambda s: test_db, __exit__=lambda s, *a: None)):
        # 2. Record a decision
        decision_id = recorder.record(
            run_id=run.id,
            sequence_idx=0,
            audio_ctx={"timestamp_sec": 10.5, "bpm": 120, "energy": 0.8},
            scene_id=10,
            video_ctx={"role": "action", "mood_refined": "energetic"},
            agent_score=0.95,
            agent_rationale={"best_match": True}
        )
        assert decision_id is not None
    
    # 3. Simulate User Feedback (Positive)
    feedback = MemUserFeedbackEvent(
        decision_id=decision_id,
        run_id=run.id,
        event_type="accept",
        payload={"source": "ui_shortcut"}
    )
    test_db.add(feedback)
    test_db.commit()
    
    # 4. Aggregate Patterns
    with patch("services.memory.pattern_aggregator.nullpool_session", return_value=MagicMock(__enter__=lambda s: test_db, __exit__=lambda s, *a: None)):
        aggregator.run_aggregation_cycle()
    
    # 5. Verify Pattern creation
    patterns = test_db.query(MemLearnedPattern).all()
    assert len(patterns) > 0
    assert patterns[0].stat_accept_count > 0
    assert patterns[0].confidence > 0.0 # Wilson Score sollte > 0 sein bei 1 Positiv-Bewertung
