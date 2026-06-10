"""Plan: AUDIO-ANALYSIS-V2-STRICT-SEQUENTIAL-2026-05-17

T1.4: PipelineContext - Track-State-Container.
"""
from __future__ import annotations

import threading
import pytest


def test_context_holds_results_per_stage():
    from services.audio_pipeline.context import PipelineContext

    ctx = PipelineContext(track_id=42, original_path="/tmp/track.wav")
    ctx.set_result("stem_gen", {"vocals": "/tmp/vocals.wav"})
    assert ctx.results["stem_gen"] == {"vocals": "/tmp/vocals.wav"}


def test_context_default_fields():
    from services.audio_pipeline.context import PipelineContext

    ctx = PipelineContext(track_id=1, original_path="/x.wav")
    assert ctx.track_id == 1
    assert ctx.original_path == "/x.wav"
    assert ctx.stem_paths == {}
    assert ctx.results == {}
    assert ctx.status == "pending"
    assert isinstance(ctx.save_lock, type(threading.RLock()))


def test_context_set_result_rejects_large_tensor():
    """A-5: Tensor-Guard - keine grossen Tensoren / ndarrays in Context."""
    import numpy as np
    from services.audio_pipeline.context import PipelineContext, ContextTensorRejected

    ctx = PipelineContext(track_id=1, original_path="/x.wav")
    # >1 MB ndarray -> reject
    big = np.zeros(2_000_000, dtype=np.float32)  # 8 MB
    with pytest.raises(ContextTensorRejected):
        ctx.set_result("stage", big)


def test_context_set_result_rejects_torch_tensor_if_available():
    """A-5 Tensor-Guard fuer torch.Tensor."""
    try:
        import torch
    except ImportError:
        pytest.skip("torch not available")
    from services.audio_pipeline.context import PipelineContext, ContextTensorRejected

    ctx = PipelineContext(track_id=1, original_path="/x.wav")
    t = torch.zeros(500_000, dtype=torch.float32)  # 2 MB
    with pytest.raises(ContextTensorRejected):
        ctx.set_result("stage", t)


def test_context_set_result_accepts_small_scalar_results():
    """Scalar / dict / small primitive ok."""
    from services.audio_pipeline.context import PipelineContext

    ctx = PipelineContext(track_id=1, original_path="/x.wav")
    ctx.set_result("beat_grid", {"bpm": 128.0, "beat_positions": [0.0, 0.46]})
    assert ctx.results["beat_grid"]["bpm"] == 128.0


def test_context_save_lock_is_reentrant():
    from services.audio_pipeline.context import PipelineContext

    ctx = PipelineContext(track_id=1, original_path="/x.wav")
    # RLock = reentrant
    with ctx.save_lock:
        with ctx.save_lock:
            ctx.set_result("x", {"k": "v"})
    assert ctx.results["x"] == {"k": "v"}
