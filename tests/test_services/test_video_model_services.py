"""Phase 31/32/33 — Model-Service Tests (mockable + optional live_gpu).

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


# ===== Phase 33: VLM-Caption-Service =====

def test_vlm_stub_mode_returns_dummy(tmp_path: Path):
    from services.video_pipeline.stages.vlm_caption_service import VlmCaptionService
    svc = VlmCaptionService()
    assert svc.is_stub is True
    frame = tmp_path / "f1.jpg"
    frame.touch()
    caps = svc.caption_keyframes([frame])
    assert len(caps) == 1
    assert caps[0].path == frame
    assert "[VLM not wired" in caps[0].text


def test_vlm_with_backend_calls_through(tmp_path: Path):
    from services.video_pipeline.stages.vlm_caption_service import (
        VlmCaptionService, Caption,
    )

    class _FakeBackend:
        def caption_image(self, image_path):
            return Caption(path=image_path, text=f"caption for {image_path.name}",
                           model_id="fake-model")

    svc = VlmCaptionService(llm_backend=_FakeBackend())
    assert svc.is_stub is False
    frame = tmp_path / "f.jpg"
    frame.touch()
    caps = svc.caption_keyframes([frame])
    assert caps[0].text == "caption for f.jpg"
    assert caps[0].model_id == "fake-model"


# ===== Phase 31: SigLIP-Embed-Service =====

def test_siglip_service_constructor_no_load():
    from services.video_pipeline.stages.siglip_embed_service import SigLipEmbedService
    svc = SigLipEmbedService()
    assert svc.is_loaded is False
    assert svc.model_id == "google/siglip-so400m-patch14-384"
    assert svc.dtype == "float16"


def test_siglip_service_unload_idempotent():
    from services.video_pipeline.stages.siglip_embed_service import SigLipEmbedService
    svc = SigLipEmbedService()
    svc.unload()
    svc.unload()
    assert svc.is_loaded is False


@pytest.mark.live_gpu
def test_siglip_live_embed_batch():
    """Slow: laedt echtes SigLIP-Modell auf GPU (~600MB VRAM)."""
    from services.video_pipeline.stages.siglip_embed_service import SigLipEmbedService
    import torch
    if not torch.cuda.is_available():
        pytest.skip("no CUDA")

    svc = SigLipEmbedService()
    frames = [np.random.randint(0, 255, (240, 320, 3), dtype=np.uint8)
              for _ in range(2)]
    arr = svc.embed_batch(frames)
    assert arr.shape == (2, 1152)
    assert arr.dtype == np.float16
    svc.unload()


# ===== Phase 32: RAFT-Motion-Service =====

def test_raft_service_constructor_variants():
    from services.video_pipeline.stages.raft_motion_service import RaftMotionService
    svc_l = RaftMotionService(variant="raft_large")
    svc_s = RaftMotionService(variant="raft_small")
    assert svc_l.variant == "raft_large"
    assert svc_s.variant == "raft_small"
    assert svc_l.is_loaded is False


def test_raft_service_invalid_variant_raises():
    from services.video_pipeline.stages.raft_motion_service import RaftMotionService
    with pytest.raises(ValueError):
        RaftMotionService(variant="bogus")


def test_raft_aggregate_pure_function():
    from services.video_pipeline.stages.raft_motion_service import RaftMotionService
    # Synthetic flow: alle Vektoren zeigen nach rechts (+x)
    flow = np.zeros((10, 10, 2), dtype=np.float32)
    flow[..., 0] = 5.0   # dx=5
    stats = RaftMotionService.aggregate(flow)
    assert stats.mean_magnitude == pytest.approx(5.0)
    assert stats.std_magnitude == pytest.approx(0.0, abs=0.01)
    assert stats.dominant_direction_rad == pytest.approx(0.0, abs=0.01)


def test_raft_aggregate_diagonal_motion():
    from services.video_pipeline.stages.raft_motion_service import RaftMotionService
    flow = np.zeros((5, 5, 2), dtype=np.float32)
    flow[..., 0] = 1.0
    flow[..., 1] = 1.0   # diagonal nach rechts-unten
    stats = RaftMotionService.aggregate(flow)
    assert stats.mean_magnitude == pytest.approx(np.sqrt(2), abs=0.01)
    # atan2(1, 1) = pi/4
    assert stats.dominant_direction_rad == pytest.approx(np.pi / 4, abs=0.01)


@pytest.mark.live_gpu
def test_raft_live_compute_flow():
    """Slow: laedt RAFT-Modell, rechnet Optical-Flow."""
    from services.video_pipeline.stages.raft_motion_service import RaftMotionService
    import torch
    if not torch.cuda.is_available():
        pytest.skip("no CUDA")

    svc = RaftMotionService(variant="raft_small", iter_count=4)
    a = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    b = np.random.randint(0, 255, (64, 64, 3), dtype=np.uint8)
    flow = svc.compute_flow(a, b)
    assert flow.shape == (64, 64, 2)
    svc.unload()
