"""Cross-Cutting Phase 71 + 73 Tests.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_probe_disk(tmp_path: Path):
    from services.video_pipeline.disk_budget import probe_disk
    info = probe_disk(tmp_path)
    assert info.total_gb > 0
    assert info.free_gb >= 0


def test_has_disk_budget_true_for_small(tmp_path: Path):
    from services.video_pipeline.disk_budget import has_disk_budget
    assert has_disk_budget(tmp_path, required_gb=0.001) is True


def test_assert_disk_budget_raises_when_huge(tmp_path: Path):
    from services.video_pipeline.disk_budget import assert_disk_budget, DiskFull
    with pytest.raises(DiskFull):
        assert_disk_budget(tmp_path, required_gb=99999.0)


def test_jsonl_observer_writes_events(tmp_path: Path):
    from services.video_pipeline.observability import JsonlObserver
    from services.video_pipeline.stages.base import StageResult

    log = tmp_path / "obs.jsonl"
    obs = JsonlObserver(log)
    obs.on_stage_started(track_id=1, stage_id="a")
    obs.on_stage_done(
        track_id=1,
        result=StageResult(stage_id="a", status="done", duration_s=0.5,
                           metrics={"count": 10}),
    )
    obs.on_stage_failed(
        track_id=1,
        result=StageResult(stage_id="b", status="failed", duration_s=0.1,
                           error="boom"),
    )
    obs.on_pipeline_done(track_id=1)

    lines = log.read_text().strip().split("\n")
    assert len(lines) == 4
    events = [json.loads(l) for l in lines]
    assert events[0]["event"] == "stage_started"
    assert events[1]["event"] == "stage_done"
    assert events[1]["status"] == "done"
    assert events[2]["event"] == "stage_failed"
    assert events[2]["error"] == "boom"
    assert events[3]["event"] == "pipeline_done"


def test_jsonl_observer_works_with_orchestrator(tmp_path: Path):
    from services.video_pipeline.orchestrator import VideoAnalysisPipeline
    from services.video_pipeline.observability import JsonlObserver
    from services.video_pipeline.stages.base import StageResult

    class _Stage:
        def __init__(self, sid): self.stage_id = sid
        def run(self, *a, **k): return StageResult(stage_id=self.stage_id,
                                                   status="done", duration_s=0.01)

    log = tmp_path / "obs.jsonl"
    obs = JsonlObserver(log)
    pipe = VideoAnalysisPipeline(
        track_id=42, source_path=tmp_path / "x.mp4",
        storage_dir=tmp_path / "out", stages=[_Stage("a"), _Stage("b")],
        listener=obs,
    )
    pipe.run()
    lines = log.read_text().strip().split("\n")
    # 2 stage_started + 2 stage_done + 1 pipeline_done = 5
    assert len(lines) == 5
