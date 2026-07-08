"""NEUBAU-VOLLINTEGRATION T1.4 (USE-006): RL-Stack v2 an Feedback.

Vorher: rl_memory_v2/rl_policy/variety_memory nur in Tests instanziert.
Jetzt: FeedbackService.record_verdict speist nach erfolgreichem Commit den
prozessweiten RLPacingMemoryV2-Singleton (Verdict-Replay + SectionPolicy +
VarietyMemory) und den Brain-V3-WeightStore (accept->'fits',
reject->'no_match'). Kein Doppel-Write: v2-Singleton laeuft OHNE
db_session_factory, mem_decision schreibt nur record_verdict selbst.
"""
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from services.feedback_service import FeedbackService
from services.pacing.rl_memory_v2 import (
    get_default_rl_memory,
    reset_default_rl_memory_for_test,
)


@pytest.fixture(autouse=True)
def _fresh_singleton():
    reset_default_rl_memory_for_test()
    yield
    reset_default_rl_memory_for_test()


def _make_db(tmp_path):
    eng = create_engine(f"sqlite:///{(tmp_path / 'fb.db').as_posix()}")
    with eng.begin() as c:
        c.execute(text("""
            CREATE TABLE mem_decision (
                id INTEGER PRIMARY KEY,
                run_id INTEGER, scene_id INTEGER, sequence_idx INTEGER,
                at_section_type TEXT, at_timestamp_sec REAL,
                user_verdict TEXT, user_verdict_at TEXT, user_rating INTEGER
            )
        """))
        c.execute(text("""
            CREATE TABLE mem_user_feedback_event (
                id INTEGER PRIMARY KEY,
                decision_id INTEGER, run_id INTEGER,
                event_type TEXT, payload TEXT, created_at TEXT
            )
        """))
        c.execute(text("""
            INSERT INTO mem_decision
            (run_id, scene_id, sequence_idx, at_section_type, at_timestamp_sec)
            VALUES (7, 42, 3, 'DROP', 12.5)
        """))
    Session = sessionmaker(bind=eng)

    @contextmanager
    def factory():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    return factory


def test_accept_feeds_rl_v2_singleton(tmp_path, monkeypatch):
    svc = FeedbackService(session_factory=_make_db(tmp_path))
    # WeightStore-Pfad wegmocken (kein echtes weights.db im Unit-Test)
    monkeypatch.setattr(
        FeedbackService, "_SECTION_TO_BRAIN", FeedbackService._SECTION_TO_BRAIN)
    import services.brain.brain_v3_service as bv3

    class _FakeSvc:
        def feedback(self, request, context=None):
            _FakeSvc.last = (request, context)

            class R:
                n_buckets_updated = 5
            return R()

    monkeypatch.setattr(bv3, "BrainV3Service", _FakeSvc)

    result = svc.record_verdict(7, 42, "accept")
    assert result.success

    mem = get_default_rl_memory()
    assert mem.count(run_id=7, verdict="good") == 1
    assert mem.section_acceptance_rate("DROP") == 1.0
    # WeightStore-Pfad wurde mit 'fits' + gemapptem Section-Context gerufen
    req, ctx = _FakeSvc.last
    assert req.rating == "fits"
    assert ctx.audio_section_type == "drop"


def test_reject_maps_to_bad_and_no_match(tmp_path, monkeypatch):
    svc = FeedbackService(session_factory=_make_db(tmp_path))
    import services.brain.brain_v3_service as bv3

    class _FakeSvc:
        last = None

        def feedback(self, request, context=None):
            _FakeSvc.last = (request, context)

            class R:
                n_buckets_updated = 5
            return R()

    monkeypatch.setattr(bv3, "BrainV3Service", _FakeSvc)

    assert svc.record_verdict(7, 42, "reject").success
    mem = get_default_rl_memory()
    assert mem.count(run_id=7, verdict="bad") == 1
    assert mem.section_acceptance_rate("DROP") == 0.0
    assert _FakeSvc.last[0].rating == "no_match"


def test_skip_records_no_weight_signal(tmp_path, monkeypatch):
    svc = FeedbackService(session_factory=_make_db(tmp_path))
    import services.brain.brain_v3_service as bv3

    called = {"n": 0}

    class _FakeSvc:
        def feedback(self, request, context=None):
            called["n"] += 1

    monkeypatch.setattr(bv3, "BrainV3Service", _FakeSvc)

    assert svc.record_verdict(7, 42, "skip").success
    # Verdict-Replay ohne good/bad, kein Policy/Weight-Signal
    mem = get_default_rl_memory()
    assert mem.count(run_id=7) == 1
    assert mem.count(run_id=7, verdict="good") == 0
    assert called["n"] == 0


def test_rl_failure_does_not_break_feedback(tmp_path, monkeypatch):
    """RL/WeightStore-Fehler duerfen record_verdict nicht scheitern lassen."""
    svc = FeedbackService(session_factory=_make_db(tmp_path))
    import services.pacing.rl_memory_v2 as rlv2

    def boom():
        raise RuntimeError("rl kaputt")

    monkeypatch.setattr(rlv2, "get_default_rl_memory", boom)
    result = svc.record_verdict(7, 42, "accept")
    assert result.success


def test_no_double_writer_contract():
    """Koexistenz-Vertrag: der Singleton laeuft ohne db_session_factory —
    mem_decision wird nur von record_verdict selbst geschrieben."""
    mem = get_default_rl_memory()
    assert mem._db_session_factory is None
