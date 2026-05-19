"""Phase 30 — Pipeline-Orchestrator Tests.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg missing"
)


@pytest.fixture
def synth_video(tmp_path: Path) -> Path:
    out = tmp_path / "src.mp4"
    subprocess.run(
        [
            shutil.which("ffmpeg"), "-y", "-f", "lavfi",
            "-i", "testsrc=duration=2:size=320x240:rate=10",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
        ],
        check=True, capture_output=True, timeout=30,
    )
    return out


class _FakeStage:
    """Test-only Stage that just emits a result."""
    def __init__(self, stage_id, status="done"):
        self.stage_id = stage_id
        self._status = status
        self.run_count = 0

    def run(self, source_path, storage_dir, *, cancel_token=None):
        from services.video_pipeline.stages.base import StageResult
        self.run_count += 1
        return StageResult(stage_id=self.stage_id, status=self._status,
                           duration_s=0.01, metrics={"runs": self.run_count})


class _RecorderListener:
    def __init__(self):
        self.events = []
    def on_stage_started(self, tid, sid):
        self.events.append(("start", tid, sid))
    def on_stage_done(self, tid, res):
        self.events.append(("done", tid, res.stage_id, res.status))
    def on_stage_failed(self, tid, res):
        self.events.append(("failed", tid, res.stage_id, res.error))
    def on_pipeline_done(self, tid):
        self.events.append(("pipeline_done", tid))


def test_pipeline_runs_stages_in_order(tmp_path: Path):
    from services.video_pipeline.orchestrator import VideoAnalysisPipeline
    a = _FakeStage("a")
    b = _FakeStage("b")
    c = _FakeStage("c")
    listener = _RecorderListener()

    pipe = VideoAnalysisPipeline(
        track_id=1, source_path=tmp_path / "fake.mp4",
        storage_dir=tmp_path / "out", stages=[a, b, c], listener=listener,
    )
    res = pipe.run()
    assert res.completed_count == 3
    assert res.failed_count == 0
    starts = [e for e in listener.events if e[0] == "start"]
    assert [s[2] for s in starts] == ["a", "b", "c"]


def test_pipeline_skips_already_done_via_checkpoint(tmp_path: Path):
    from services.video_pipeline.orchestrator import VideoAnalysisPipeline
    from services.video_pipeline.primitives.resume_checkpoint import ResumeCheckpoint

    cp = ResumeCheckpoint(tmp_path / "cp.json", track_id=1, stream_sha256="x")
    cp.update_stage("a", status="done")
    cp.save()

    a = _FakeStage("a")
    b = _FakeStage("b")
    pipe = VideoAnalysisPipeline(
        track_id=1, source_path=tmp_path / "fake.mp4",
        storage_dir=tmp_path / "out", stages=[a, b], checkpoint=cp,
    )
    pipe.run()
    assert a.run_count == 0   # skipped
    assert b.run_count == 1   # ausgefuehrt


def test_pipeline_failed_stage_continues(tmp_path: Path):
    from services.video_pipeline.orchestrator import VideoAnalysisPipeline
    a = _FakeStage("a", status="failed")
    b = _FakeStage("b")
    pipe = VideoAnalysisPipeline(
        track_id=1, source_path=tmp_path / "fake.mp4",
        storage_dir=tmp_path / "out", stages=[a, b],
    )
    res = pipe.run()
    assert res.failed_count == 1
    assert res.completed_count == 1
    assert b.run_count == 1


def test_pipeline_cancel_token_stops(tmp_path: Path):
    from services.video_pipeline.orchestrator import VideoAnalysisPipeline
    a = _FakeStage("a")
    b = _FakeStage("b")
    pipe = VideoAnalysisPipeline(
        track_id=1, source_path=tmp_path / "fake.mp4",
        storage_dir=tmp_path / "out", stages=[a, b],
    )
    pipe.cancel()  # vor Run
    res = pipe.run()
    assert res.cancelled is True
    assert a.run_count == 0


def test_pipeline_integrates_real_stages(synth_video: Path, tmp_path: Path):
    """E2E: Proxy + Scene-Detect + Keyframe-Extract sequentiell."""
    from services.video_pipeline.orchestrator import VideoAnalysisPipeline
    from services.video_pipeline.stages.proxy_gen_stage import ProxyGenStage
    from services.video_pipeline.stages.scene_detect_stage import SceneDetectStage
    from services.video_pipeline.stages.keyframe_extract_stage import KeyframeExtractStage

    storage = tmp_path / "storage"
    pipe = VideoAnalysisPipeline(
        track_id=42, source_path=synth_video, storage_dir=storage,
        stages=[
            ProxyGenStage(max_width=160, bitrate="200k"),
            SceneDetectStage(),
            KeyframeExtractStage(mode="mid"),
        ],
    )
    res = pipe.run()
    assert res.failed_count == 0
    assert (storage / "proxy.mp4").exists()
    assert (storage / "scenes.json").exists()
    assert (storage / "keyframes.json").exists()
