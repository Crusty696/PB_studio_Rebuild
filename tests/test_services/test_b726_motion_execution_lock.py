"""B-726: Direkte RAFT-Motion-API muss GPU-Execution-Lease nehmen."""

from __future__ import annotations

from contextlib import contextmanager


def test_direct_motion_call_enters_execution_lease(monkeypatch) -> None:
    import services.model_manager as model_manager
    import services.video_analysis_service as vas

    events: list[str] = []

    @contextmanager
    def _lease(reason: str):
        events.append(reason)
        yield

    monkeypatch.setattr(model_manager, "gpu_execution_lease", _lease)

    assert vas.compute_motion_scores("missing.mp4", []) == []
    assert events == ["motion_scores"]


def test_batch_motion_call_does_not_take_second_lease(monkeypatch) -> None:
    import services.model_manager as model_manager
    import services.video_analysis_service as vas

    monkeypatch.setattr(
        model_manager,
        "gpu_execution_lease",
        lambda _reason: (_ for _ in ()).throw(AssertionError("second lease")),
    )

    assert vas.compute_motion_scores("missing.mp4", [], raft_model_device=(object(), "cuda:0")) == []
