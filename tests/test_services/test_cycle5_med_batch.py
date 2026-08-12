"""Cycle 5 MED batch — RED-Tests fuer B-158, B-160, B-161.

Source-inspection-Tests (kein DB/GPU).
"""
from __future__ import annotations

import inspect


def test_b158_auto_edit_phase3_uses_cached_engine_without_dispose(monkeypatch):
    """Auto-Edit nutzt die kanonische Cache-Engine und disposed sie nicht."""
    import database.session as session_module
    from services import pacing_service
    from services.pacing import bridge

    class CachedEngine:
        dispose_calls = 0

        def dispose(self):
            self.dispose_calls += 1

    cached = CachedEngine()
    seen = {}
    monkeypatch.setattr(session_module, "_get_cached_nullpool_engine", lambda: cached)
    monkeypatch.setattr(
        bridge, "maybe_use_studio_brain_pipeline", lambda **_kwargs: False,
    )

    def fake_inner(engine, audio_id, video_clip_ids, settings, **kwargs):
        seen.update(
            engine=engine,
            audio_id=audio_id,
            video_clip_ids=video_clip_ids,
            settings=settings,
            kwargs=kwargs,
        )
        return ["segment"], ["cut"]

    monkeypatch.setattr(pacing_service, "_auto_edit_phase3_inner", fake_inner)
    settings = object()

    result = pacing_service.auto_edit_phase3(7, [11, 12], settings)

    assert result == (["segment"], ["cut"])
    assert seen["engine"] is cached
    assert seen["audio_id"] == 7
    assert seen["video_clip_ids"] == [11, 12]
    assert seen["settings"] is settings
    assert cached.dispose_calls == 0


def test_b160_get_section_at_time_no_id_based_cache():
    """B-160: get_section_at_time darf id(sections) nicht als Cache-Key
    verwenden — nach GC kollidiert die id und der Cache liefert alte Daten."""
    from services import pacing_beat_grid

    src = inspect.getsource(pacing_beat_grid.get_section_at_time)
    assert "id(sections)" not in src, (
        "get_section_at_time darf id(sections) nicht als Cache-Key nutzen "
        "(B-160: id-Reuse nach GC liefert Stale-Cache)."
    )


def test_b161_decision_recorder_queue_lock_present():
    """B-161: DecisionRecorder._queue muss durch threading.Lock geschuetzt sein,
    sonst Race zwischen record() (Worker-Thread) und flush_queue() (Main-Thread).
    """
    from services.pacing import decision_recorder

    init_src = inspect.getsource(decision_recorder.DecisionRecorder.__init__)
    record_src = inspect.getsource(decision_recorder.DecisionRecorder.record)
    flush_src = inspect.getsource(decision_recorder.DecisionRecorder.flush_queue)

    assert "Lock" in init_src or "_queue_lock" in init_src, (
        "DecisionRecorder.__init__ muss einen Lock fuer _queue anlegen (B-161)."
    )
    # Mutation in record() muss durch with self._queue_lock geschuetzt sein.
    assert "_queue_lock" in record_src, (
        "DecisionRecorder.record muss _queue unter _queue_lock anhaengen (B-161)."
    )
    assert "_queue_lock" in flush_src, (
        "DecisionRecorder.flush_queue muss _queue unter _queue_lock iterieren (B-161)."
    )
