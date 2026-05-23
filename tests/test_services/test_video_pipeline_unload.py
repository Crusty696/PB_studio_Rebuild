"""F-1 (B-333): orchestrator frees GPU models after each stage.

Verifies the orchestrator calls ``stage.unload()`` once a stage finishes,
so siglip + raft do not stay resident together on the 6 GB GTX 1060.
"""
from __future__ import annotations

from pathlib import Path

from services.video_pipeline.orchestrator import VideoAnalysisPipeline
from services.video_pipeline.stages.base import StageResult


class _FakeStage:
    def __init__(self, stage_id: str, status: str = "done"):
        self.stage_id = stage_id
        self._status = status
        self.unloaded = 0

    def run(self, source_path, storage_dir, *, cancel_token=None) -> StageResult:
        return StageResult(stage_id=self.stage_id, status=self._status, duration_s=0.0)

    def unload(self) -> None:
        self.unloaded += 1


class _NoUnloadStage:
    stage_id = "no_unload"

    def run(self, source_path, storage_dir, *, cancel_token=None) -> StageResult:
        return StageResult(stage_id=self.stage_id, status="done", duration_s=0.0)


def test_orchestrator_unloads_each_stage(tmp_path: Path):
    s1 = _FakeStage("a")
    s2 = _FakeStage("b", status="failed")
    pipe = VideoAnalysisPipeline(
        track_id=1, source_path=tmp_path / "v.mp4",
        storage_dir=tmp_path / "store", stages=[s1, s2],
    )
    pipe.run()
    # F-1: unload called once per stage regardless of done/failed.
    assert s1.unloaded == 1
    assert s2.unloaded == 1


def test_orchestrator_tolerates_stage_without_unload(tmp_path: Path):
    pipe = VideoAnalysisPipeline(
        track_id=1, source_path=tmp_path / "v.mp4",
        storage_dir=tmp_path / "store", stages=[_NoUnloadStage()],
    )
    res = pipe.run()  # must not raise
    assert res.completed_count == 1
