"""Phase 37/38 — Status-Reporter + Trigger-Queue Tests.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
"""
from __future__ import annotations

import pytest


# ===== Phase 38: TriggerQueue =====

def test_trigger_queue_enqueue_and_get():
    from services.video_pipeline.trigger_queue import TriggerQueue, TriggerJob
    q = TriggerQueue()
    q.enqueue(TriggerJob("a", runner=lambda: "ok"))
    q.enqueue(TriggerJob("b", runner=lambda: "ok"))
    assert len(q.jobs()) == 2
    assert q.get_job("a").stage_id == "a"


def test_trigger_queue_duplicate_raises():
    from services.video_pipeline.trigger_queue import TriggerQueue, TriggerJob
    q = TriggerQueue()
    q.enqueue(TriggerJob("a", runner=lambda: None))
    with pytest.raises(ValueError):
        q.enqueue(TriggerJob("a", runner=lambda: None))


def test_trigger_queue_run_single():
    from services.video_pipeline.trigger_queue import TriggerQueue, TriggerJob
    q = TriggerQueue()
    q.enqueue(TriggerJob("a", runner=lambda: 42))
    res = q.run_single("a")
    assert res.status == "done"
    assert res.result == 42


def test_trigger_queue_run_all_in_order():
    from services.video_pipeline.trigger_queue import TriggerQueue, TriggerJob
    q = TriggerQueue()
    order = []
    q.enqueue(TriggerJob("a", runner=lambda: order.append("a") or "A"))
    q.enqueue(TriggerJob("b", runner=lambda: order.append("b") or "B"))
    q.enqueue(TriggerJob("c", runner=lambda: order.append("c") or "C"))
    q.run_all()
    assert order == ["a", "b", "c"]
    assert all(j.status == "done" for j in q.jobs())


def test_trigger_queue_failed_continues():
    from services.video_pipeline.trigger_queue import TriggerQueue, TriggerJob
    q = TriggerQueue()
    def _bad():
        raise RuntimeError("boom")
    q.enqueue(TriggerJob("a", runner=_bad))
    q.enqueue(TriggerJob("b", runner=lambda: "ok"))
    q.run_all()
    assert q.get_job("a").status == "failed"
    assert q.get_job("b").status == "done"


def test_trigger_queue_cancel_stops_remaining():
    from services.video_pipeline.trigger_queue import TriggerQueue, TriggerJob
    q = TriggerQueue()
    q.enqueue(TriggerJob("a", runner=lambda: q.cancel() or "a"))
    q.enqueue(TriggerJob("b", runner=lambda: "b"))
    q.run_all()
    assert q.get_job("a").status == "done"
    assert q.get_job("b").status == "pending"


def test_trigger_queue_re_run_failed_via_run_all():
    from services.video_pipeline.trigger_queue import TriggerQueue, TriggerJob
    q = TriggerQueue()
    state = {"count": 0}
    def _maybe_fail():
        state["count"] += 1
        if state["count"] == 1:
            raise RuntimeError("first fails")
        return "ok"
    q.enqueue(TriggerJob("a", runner=_maybe_fail))
    q.run_all()
    assert q.get_job("a").status == "failed"
    q.run_all()
    assert q.get_job("a").status == "done"


# ===== Phase 37: StatusReporter =====

def test_status_reporter_initial_pending():
    from services.video_pipeline.status_reporter import StatusReporter
    rep = StatusReporter(["a", "b", "c"])
    snap = rep.snapshot()
    assert set(snap.keys()) == {"a", "b", "c"}
    assert all(s.status == "pending" for s in snap.values())


def test_status_reporter_emits_to_subscribers():
    from services.video_pipeline.status_reporter import StatusReporter
    from services.video_pipeline.stages.base import StageResult
    events = []
    rep = StatusReporter(["a"])
    rep.subscribe(lambda st: events.append(st.status))

    rep.on_stage_started(1, "a")
    rep.on_stage_done(1, StageResult(stage_id="a", status="done",
                                     duration_s=0.5, metrics={"x": 1}))

    assert events == ["running", "done"]
    assert rep.status_of("a").duration_s == 0.5
    assert rep.status_of("a").metrics == {"x": 1}


def test_status_reporter_progress_summary():
    from services.video_pipeline.status_reporter import StatusReporter
    from services.video_pipeline.stages.base import StageResult
    rep = StatusReporter(["a", "b", "c"])
    rep.on_stage_done(1, StageResult(stage_id="a", status="done", duration_s=1))
    rep.on_stage_failed(1, StageResult(stage_id="b", status="failed",
                                       duration_s=0.1, error="boom"))
    sum_ = rep.progress_summary()
    assert sum_["done"] == 1
    assert sum_["failed"] == 1
    assert sum_["pending"] == 1
    assert sum_["total"] == 3


def test_status_reporter_integrates_with_orchestrator(tmp_path):
    from services.video_pipeline.orchestrator import VideoAnalysisPipeline
    from services.video_pipeline.status_reporter import StatusReporter
    from services.video_pipeline.stages.base import StageResult

    class _FakeStage:
        def __init__(self, sid): self.stage_id = sid
        def run(self, *a, **k): return StageResult(stage_id=self.stage_id,
                                                   status="done", duration_s=0.01)

    rep = StatusReporter(["a", "b"])
    pipe = VideoAnalysisPipeline(
        track_id=1, source_path=tmp_path / "x.mp4",
        storage_dir=tmp_path / "out",
        stages=[_FakeStage("a"), _FakeStage("b")],
        listener=rep,
    )
    pipe.run()
    sum_ = rep.progress_summary()
    assert sum_["done"] == 2


def test_trigger_queue_pause_and_resume():
    import time
    import threading
    from services.video_pipeline.trigger_queue import TriggerQueue, TriggerJob
    
    q = TriggerQueue()
    order = []
    
    def run_a():
        order.append("a")
        q.pause()  # Pausiert die Queue nach Job a
        
    q.enqueue(TriggerJob("a", runner=run_a))
    q.enqueue(TriggerJob("b", runner=lambda: order.append("b") or "B"))
    
    # Timer-Thread, der nach 0.1s resume() aufruft
    t = threading.Timer(0.1, q.resume)
    t.start()
    
    t0 = time.monotonic()
    q.run_all()
    duration = time.monotonic() - t0
    
    # Der Timer-Thread muss beendet sein
    t.join()
    
    assert order == ["a", "b"]  # Beide Jobs müssen gelaufen sein, keiner verloren (no drops)
    assert duration >= 0.05      # Verifiziert, dass blockiert wurde und nicht sofort zurückgekehrt wurde
