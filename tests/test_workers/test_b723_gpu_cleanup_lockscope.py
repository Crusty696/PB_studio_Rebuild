"""B-723: Stem-CUDA-Cleanup darf GPU-Execution-Lease nicht verlassen."""

from __future__ import annotations

import sys
import inspect
from types import SimpleNamespace


class _TrackingLock:
    def __init__(self) -> None:
        self.held = False

    def __enter__(self):
        assert not self.held
        self.held = True
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.held = False


def test_stem_cuda_cleanup_runs_inside_execution_lock(monkeypatch) -> None:
    """empty_cache must see the same execution lock held by stem inference."""
    import services.model_manager as model_manager
    import workers.audio as audio

    lock = _TrackingLock()
    cleanup_lock_states: list[bool] = []

    class _Cuda:
        @staticmethod
        def is_available() -> bool:
            return True

        @staticmethod
        def empty_cache() -> None:
            cleanup_lock_states.append(lock.held)

    class _Separator:
        def separate_and_store(self, *_args, **_kwargs):
            return {"stem_count": 4}

    monkeypatch.setattr(model_manager, "GPU_EXECUTION_LOCK", lock)
    monkeypatch.setattr("services.ai_audio_service.StemSeparator", _Separator)
    monkeypatch.setattr(audio, "mark_started", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(audio, "mark_done", lambda *_args, **_kwargs: None)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=_Cuda()))

    audio.StemSeparationWorker(track_id=1).run()

    assert cleanup_lock_states == [True]


def test_video_exception_cleanup_has_execution_lease() -> None:
    """Outer-finally RAFT/SigLIP cleanup must not run after the batch lease."""
    from workers.video import VideoAnalysisPipelineWorker

    source = inspect.getsource(VideoAnalysisPipelineWorker.run)
    cleanup = source[source.index("RAFT + SigLIP Cleanup auch bei unerwarteten Exceptions"):]

    assert 'gpu_execution_lease("video_analysis_exception_cleanup")' in cleanup
