"""Phase 31/32/33/39 — Stage-Wrapper Tests (mocked Services).

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg missing"
)


def _make_keyframes(storage: Path, n: int = 4):
    kf_dir = storage / "keyframes"
    kf_dir.mkdir(parents=True, exist_ok=True)
    payload = []
    for i in range(n):
        fp = kf_dir / f"scene{i:04d}_mid_{float(i):.2f}.jpg"
        Image.fromarray(np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)).save(fp)
        payload.append({"scene_idx": i, "role": "mid", "time_s": float(i),
                        "path": f"keyframes/scene{i:04d}_mid_{float(i):.2f}.jpg"})
    (storage / "keyframes.json").write_text(json.dumps(payload))
    return payload


# ===== Phase 31 Stage: SigLIP-Embed-Stage =====

def test_siglip_stage_with_mock_service(tmp_path: Path):
    from services.video_pipeline.stages.siglip_embed_stage import SigLipEmbedStage

    class _MockService:
        model_id = "mock-siglip"
        def embed_batch(self, frames):
            return np.zeros((len(frames), 1152), dtype=np.float16)

    storage = tmp_path / "out"
    _make_keyframes(storage, n=4)
    stage = SigLipEmbedStage(service=_MockService(), batch_size=2)
    res = stage.run(tmp_path / "ignored.mp4", storage)
    assert res.status == "done"
    assert res.metrics["embeddings_count"] == 4
    assert res.metrics["embedding_dim"] == 1152
    npy = np.load(storage / "embeddings.npy")
    assert npy.shape == (4, 1152)


def test_siglip_stage_no_keyframes_fails(tmp_path: Path):
    from services.video_pipeline.stages.siglip_embed_stage import SigLipEmbedStage
    res = SigLipEmbedStage().run(tmp_path / "ignored.mp4", tmp_path / "empty")
    assert res.status == "failed"


# ===== Phase 33 Stage: VLM-Caption-Stage =====

def test_vlm_stage_stub_mode(tmp_path: Path):
    from services.video_pipeline.stages.vlm_caption_stage import VlmCaptionStage
    storage = tmp_path / "out"
    _make_keyframes(storage, n=3)
    res = VlmCaptionStage().run(tmp_path / "ignored.mp4", storage)
    assert res.status == "done"
    assert res.metrics["caption_count"] == 3
    assert res.metrics["is_stub"] is True
    data = json.loads((storage / "captions.json").read_text())
    assert len(data) == 3
    assert "[VLM not wired" in data[0]["text"]


# ===== Phase 39 Stage: Cross-Modal-Stage =====

def test_cross_modal_stage_skipped_if_no_audio_dir(tmp_path: Path):
    from services.video_pipeline.stages.cross_modal_stage import CrossModalStage
    storage = tmp_path / "out"
    storage.mkdir(parents=True)
    (storage / "scenes.json").write_text(json.dumps([
        {"index": 0, "start_s": 0.0, "end_s": 4.0},
    ]))
    res = CrossModalStage().run(tmp_path / "ignored.mp4", storage)
    assert res.status == "skipped"
    assert "audio_outputs_dir" in (res.metrics.get("reason") or "")


def test_cross_modal_stage_done_with_audio(tmp_path: Path):
    from services.video_pipeline.stages.cross_modal_stage import CrossModalStage
    storage = tmp_path / "out"
    storage.mkdir(parents=True)
    (storage / "scenes.json").write_text(json.dumps([
        {"index": 0, "start_s": 0.0, "end_s": 4.0},
        {"index": 1, "start_s": 4.0, "end_s": 8.0},
    ]))
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    (audio_dir / "beats.json").write_text(json.dumps([4.05, 5.0, 6.0]))

    res = CrossModalStage(audio_outputs_dir=audio_dir).run(
        tmp_path / "ignored.mp4", storage,
    )
    assert res.status == "done"
    plan = json.loads((storage / "cut_plan.json").read_text())
    assert len(plan) >= 1


# ===== Phase 32 Stage: RAFT-Motion-Stage (mock) =====

def test_raft_stage_with_mock_service(tmp_path: Path):
    from services.video_pipeline.stages.raft_motion_stage import RaftMotionStage
    from services.video_pipeline.stages.raft_motion_service import RaftMotionService

    # Synth 2s video
    src = tmp_path / "src.mp4"
    subprocess.run(
        [shutil.which("ffmpeg"), "-y", "-f", "lavfi",
         "-i", "testsrc=duration=2:size=160x120:rate=10",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)],
        check=True, capture_output=True, timeout=30,
    )

    class _MockService:
        variant = "mock"
        def compute_flow(self, a, b):
            return np.zeros((10, 10, 2), dtype=np.float32)

    stage = RaftMotionStage(service=_MockService(), sample_rate_s=1.0)
    res = stage.run(src, tmp_path / "out")
    assert res.status == "done"
    assert (tmp_path / "out" / "motion.json").exists()
    data = json.loads((tmp_path / "out" / "motion.json").read_text())
    assert len(data) >= 1
    assert "mean_magnitude" in data[0]
