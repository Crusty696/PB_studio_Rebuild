"""GPU serialization contract tests for the full-project audit fix plan."""
from __future__ import annotations

import inspect
import threading


def test_model_manager_uses_single_execution_lock_for_loaded_models():
    from services import model_manager

    assert isinstance(model_manager.GPU_LOAD_LOCK, type(threading.RLock()))
    assert isinstance(model_manager.GPU_EXECUTION_LOCK, type(threading.RLock()))
    source = inspect.getsource(model_manager.ModelManager.ensure_loaded)

    assert "gpu_resource_lease" in source
    assert 'gpu_resource_lease(f"ensure_loaded:{model_type}")' in source


def test_brain_gpu_serializer_bridges_to_model_manager_execution_lock():
    from services import model_manager
    from services.brain.gpu_serializer import GpuSerializer

    serializer = GpuSerializer()

    assert serializer._legacy_gpu_execution_lock() is model_manager.GPU_EXECUTION_LOCK
    source = inspect.getsource(GpuSerializer.acquire)
    assert "_legacy_gpu_execution_lock" in source
    # B-503: Acquire laeuft jetzt ueber _timed_acquire (Timeout + Holder-Log),
    # die Bridge auf den legacy Lock bleibt bestehen.
    assert "_timed_acquire(legacy_lock" in source


def test_siglip_stage_runs_gpu_work_under_default_serializer():
    from services.video_pipeline.stages.siglip_embed_stage import SigLipEmbedStage

    source = inspect.getsource(SigLipEmbedStage.run)

    assert "get_default_serializer" in source
    assert 'acquire("video_pipeline_siglip")' in source
    assert "self.service.embed_batch" in source


def test_raft_stage_runs_gpu_work_under_default_serializer():
    from services.video_pipeline.stages.raft_motion_stage import RaftMotionStage

    source = inspect.getsource(RaftMotionStage.run)

    assert "get_default_serializer" in source
    assert 'acquire("video_pipeline_raft")' in source
    assert "self.service.compute_flow" in source
