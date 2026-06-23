"""Phase 12 — Frame-Sampler RED.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 12 (Tier 2 Building-Blocks)
"""
from __future__ import annotations

import pytest


def test_uniform_sampling_basic():
    from services.video_pipeline.primitives.frame_sampler import sample_frame_times
    ts = sample_frame_times(duration_s=10.0, fps=30.0, strategy="uniform", rate_s=2.0)
    # Erwartet: [0, 2, 4, 6, 8] -- 10s exklusiv
    assert ts == [0.0, 2.0, 4.0, 6.0, 8.0]


def test_uniform_sampling_short_clip():
    from services.video_pipeline.primitives.frame_sampler import sample_frame_times
    ts = sample_frame_times(duration_s=1.0, fps=30.0, strategy="uniform", rate_s=2.0)
    assert ts == [0.0]


def test_b573_uniform_excludes_timestamp_inside_final_frame_interval():
    from services.video_pipeline.primitives.frame_sampler import sample_frame_times

    ts = sample_frame_times(
        duration_s=14400.154297,
        fps=5.0,
        strategy="uniform",
        rate_s=1.0,
    )

    assert ts[-1] == 14399.0
    assert 14400.0 not in ts


def test_scene_anchored_k3():
    from services.video_pipeline.primitives.frame_sampler import sample_frame_times
    scenes = [
        {"start_s": 0.0, "end_s": 4.0},
        {"start_s": 4.0, "end_s": 10.0},
    ]
    ts = sample_frame_times(
        duration_s=10.0, fps=30.0, strategy="scene_anchored",
        scenes=scenes, k=3,
    )
    # 2 scenes * 3 anchors = 6
    assert len(ts) == 6
    # Scene 1: start=0, mid=2, end ~ < 4
    assert ts[0] == pytest.approx(0.0)
    assert ts[1] == pytest.approx(2.0)
    assert ts[2] < 4.0
    # Scene 2: start=4, mid=7, end ~ < 10
    assert ts[3] == pytest.approx(4.0)
    assert ts[4] == pytest.approx(7.0)


def test_dense_until():
    from services.video_pipeline.primitives.frame_sampler import sample_frame_times
    ts = sample_frame_times(
        duration_s=2.0, fps=10.0, strategy="dense_until", n_max=10,
    )
    # 2s * 10fps = 20 frames -> n_max=10 limitiert
    assert len(ts) == 10
    assert ts[0] == 0.0
    assert ts[-1] < 2.0


def test_mixed_strategy_unioned():
    from services.video_pipeline.primitives.frame_sampler import sample_frame_times
    scenes = [{"start_s": 0.0, "end_s": 10.0}]
    ts = sample_frame_times(
        duration_s=10.0, fps=30.0, strategy="mixed",
        scenes=scenes, rate_s=2.0, k=3,
    )
    # Mixed: union(uniform + scene_anchored), sortiert, eindeutig
    assert ts == sorted(ts)
    assert len(ts) == len(set(ts))
    # Mindestens die uniform-Anker [0,2,4,6,8] enthalten
    for t in [0.0, 2.0, 4.0, 6.0, 8.0]:
        assert t in ts


def test_invalid_strategy_raises():
    from services.video_pipeline.primitives.frame_sampler import sample_frame_times
    with pytest.raises(ValueError):
        sample_frame_times(duration_s=10.0, fps=30.0, strategy="bogus")


def test_scene_anchored_without_scenes_raises():
    from services.video_pipeline.primitives.frame_sampler import sample_frame_times
    with pytest.raises(ValueError):
        sample_frame_times(
            duration_s=10.0, fps=30.0, strategy="scene_anchored",
        )
