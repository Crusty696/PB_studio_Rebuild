"""F-16 (B-348): RAFT stage reuses the previous frame instead of decoding
every interior timestamp twice."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from services.video_pipeline.stages.raft_motion_stage import RaftMotionStage


class _FakeMeta:
    def __init__(self, duration_s: float, fps: float):
        self.duration_s = duration_s
        self.fps = fps


class _CountingDecoder:
    def __init__(self):
        self.extract_calls = 0

    def probe(self, _path):
        return _FakeMeta(duration_s=10.0, fps=30.0)

    def extract_frame(self, _path, _t):
        self.extract_calls += 1
        return np.zeros((4, 4, 3), dtype=np.uint8)


class _FakeService:
    variant = "raft_large"

    def compute_flow(self, _a, _b):
        return np.zeros((4, 4, 2), dtype=np.float32)

    def unload(self):
        pass


def test_raft_decodes_each_timestamp_once(tmp_path: Path):
    dec = _CountingDecoder()
    stage = RaftMotionStage(service=_FakeService(), decoder=dec, sample_rate_s=2.0)
    src = tmp_path / "v.mp4"
    src.write_bytes(b"x")
    res = stage.run(src, tmp_path / "store")
    assert res.status == "done"
    n_pairs = res.metrics["pairs"]
    # Old behaviour decoded 2 frames per pair (2*n_pairs). With reuse it is
    # n_pairs + 1 (one initial frame + one new frame per pair).
    assert dec.extract_calls == n_pairs + 1
    assert dec.extract_calls < 2 * n_pairs  # strictly fewer than the old path
