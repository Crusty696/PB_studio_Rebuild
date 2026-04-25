"""Cycle 5 MED batch — RED-Tests fuer B-158, B-160, B-161.

Source-inspection-Tests (kein DB/GPU).
"""
from __future__ import annotations

import inspect


def test_b158_auto_edit_phase3_uses_try_finally_for_engine():
    """B-158: auto_edit_phase3 muss _ae_eng in try/finally disposen,
    damit unaccaught Exceptions keine Engine-Leaks erzeugen."""
    from services import pacing_service

    src = inspect.getsource(pacing_service.auto_edit_phase3)
    # Try-Block muss VOR der Engine-Erzeugung oder direkt danach starten,
    # finally-Block muss dispose() rufen.
    assert "try:" in src and "finally:" in src, (
        "auto_edit_phase3 muss try/finally fuer Engine-Cleanup nutzen (B-158)."
    )
    # Heuristik: dispose-Call im finally-Bereich.
    finally_idx = src.find("finally:")
    after_finally = src[finally_idx:] if finally_idx >= 0 else ""
    assert "dispose()" in after_finally, (
        "finally-Block muss _ae_eng.dispose() rufen (B-158)."
    )


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
