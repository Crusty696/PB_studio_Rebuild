from pathlib import Path

import pytest

from services.video_pipeline.orchestrator import VideoAnalysisPipeline
from services.video_pipeline.stages.base import StageResult


class _UnloadTrackedStage:
    stage_id = "tracked"

    def __init__(self):
        self.unload_called = False

    def run(self, _source_path, _storage_dir, *, cancel_token=None):
        return StageResult(stage_id=self.stage_id, status="done", duration_s=0.01)

    def unload(self):
        self.unload_called = True


class _FailingDoneListener:
    def on_stage_started(self, _track_id, _stage_id):
        pass

    def on_stage_done(self, _track_id, _result):
        raise RuntimeError("listener failed")

    def on_stage_failed(self, _track_id, _result):
        pass

    def on_pipeline_done(self, _track_id):
        pass


class _FailingCheckpoint:
    def completed_stages(self):
        return []

    def update_stage(self, *_args, **_kwargs):
        pass

    def save(self):
        raise RuntimeError("checkpoint save failed")


def test_b364_stage_unload_runs_when_listener_done_callback_raises(tmp_path: Path):
    stage = _UnloadTrackedStage()
    pipeline = VideoAnalysisPipeline(
        track_id=1,
        source_path=tmp_path / "source.mp4",
        storage_dir=tmp_path / "storage",
        stages=[stage],
        listener=_FailingDoneListener(),
    )

    with pytest.raises(RuntimeError, match="listener failed"):
        pipeline.run()

    assert stage.unload_called is True


def test_b364_stage_unload_runs_when_checkpoint_save_raises(tmp_path: Path):
    stage = _UnloadTrackedStage()
    pipeline = VideoAnalysisPipeline(
        track_id=1,
        source_path=tmp_path / "source.mp4",
        storage_dir=tmp_path / "storage",
        stages=[stage],
        checkpoint=_FailingCheckpoint(),
    )

    with pytest.raises(RuntimeError, match="checkpoint save failed"):
        pipeline.run()

    assert stage.unload_called is True
