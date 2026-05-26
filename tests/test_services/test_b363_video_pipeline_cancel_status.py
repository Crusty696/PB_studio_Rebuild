import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from services.video_pipeline.orchestrator import VideoAnalysisPipeline
from services.video_pipeline.primitives.resume_checkpoint import ResumeCheckpoint
from services.video_pipeline.stages.base import StageResult
from services.video_pipeline.stages.keyframe_extract_stage import KeyframeExtractStage
from services.video_pipeline.stages.raft_motion_stage import RaftMotionStage
from services.video_pipeline.stages.siglip_embed_stage import SigLipEmbedStage


class _CancelOnSecondCheck:
    def __init__(self):
        self.calls = 0

    @property
    def cancelled(self) -> bool:
        self.calls += 1
        return self.calls >= 2


class _NoopSerializer:
    @contextmanager
    def acquire(self, _holder):
        yield


def test_b363_raft_cancel_after_first_pair_is_not_done(monkeypatch, tmp_path: Path):
    import services.brain_v3.gpu_serializer as gpu_serializer

    monkeypatch.setattr(gpu_serializer, "get_default_serializer", lambda: _NoopSerializer())

    class _Decoder:
        def probe(self, _source_path):
            return SimpleNamespace(duration_s=4.0, fps=30.0)

        def extract_frame(self, _source_path, _time_s):
            return np.zeros((2, 2, 3), dtype=np.uint8)

    class _Service:
        variant = "fake"

        def compute_flow(self, _a, _b):
            return np.zeros((2, 2, 2), dtype=np.float32)

        @staticmethod
        def aggregate(_flow):
            return SimpleNamespace(mean_magnitude=1.0, std_magnitude=0.0, dominant_direction_rad=0.0)

        def unload(self):
            pass

    result = RaftMotionStage(service=_Service(), decoder=_Decoder(), sample_rate_s=1.0).run(
        tmp_path / "source.mp4",
        tmp_path / "storage",
        cancel_token=_CancelOnSecondCheck(),
    )

    assert result.status != "done"
    assert result.error == "cancelled"


def test_b363_siglip_cancel_after_first_batch_is_not_done(monkeypatch, tmp_path: Path):
    import services.brain_v3.gpu_serializer as gpu_serializer

    monkeypatch.setattr(gpu_serializer, "get_default_serializer", lambda: _NoopSerializer())
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "a.jpg").write_bytes(b"fake")
    (storage / "b.jpg").write_bytes(b"fake")
    (storage / "keyframes.json").write_text(json.dumps([{"path": "a.jpg"}, {"path": "b.jpg"}]))
    monkeypatch.setattr(
        "services.video_pipeline.stages.siglip_embed_stage.Image.open",
        lambda _path: SimpleNamespace(convert=lambda _mode: np.zeros((2, 2, 3), dtype=np.uint8)),
    )

    class _Service:
        model_id = "fake"

        def embed_batch(self, imgs):
            return np.ones((len(imgs), 3), dtype=np.float32)

        def unload(self):
            pass

    result = SigLipEmbedStage(service=_Service(), batch_size=1).run(
        tmp_path / "source.mp4",
        storage,
        cancel_token=_CancelOnSecondCheck(),
    )

    assert result.status != "done"
    assert result.error == "cancelled"


def test_b363_keyframe_cancel_after_first_frame_is_not_done(monkeypatch, tmp_path: Path):
    import services.video_pipeline.stages.keyframe_extract_stage as keyframe_stage

    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "scenes.json").write_text(json.dumps([{"index": 1, "start_s": 0.0, "end_s": 4.0}]))
    monkeypatch.setattr(
        keyframe_stage,
        "select_keyframes",
        lambda *_a, **_k: [
            keyframe_stage.Keyframe(scene_idx=1, role="a", time_s=1.0),
            keyframe_stage.Keyframe(scene_idx=1, role="b", time_s=2.0),
        ],
    )

    class _Decoder:
        def extract_frame(self, _source_path, time_s):
            return np.zeros((2, 2, 3), dtype=np.uint8)

    result = KeyframeExtractStage(decoder=_Decoder()).run(
        tmp_path / "source.mp4",
        storage,
        cancel_token=_CancelOnSecondCheck(),
    )

    assert result.status != "done"
    assert result.error == "cancelled"


def test_b363_orchestrator_does_not_checkpoint_done_when_cancelled_stage_returns_done(tmp_path: Path):
    class _CancellingDoneStage:
        stage_id = "cancel_done"

        def run(self, _source_path, _storage_dir, *, cancel_token=None):
            cancel_token.cancel()
            return StageResult(stage_id=self.stage_id, status="done", duration_s=0.01)

    checkpoint = ResumeCheckpoint(tmp_path / "checkpoint.json", track_id=1, stream_sha256="sha")
    result = VideoAnalysisPipeline(
        track_id=1,
        source_path=tmp_path / "source.mp4",
        storage_dir=tmp_path / "storage",
        stages=[_CancellingDoneStage()],
        checkpoint=checkpoint,
    ).run()

    assert result.cancelled is True
    assert checkpoint.stages["cancel_done"]["status"] != "done"
