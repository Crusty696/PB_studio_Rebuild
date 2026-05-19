"""Phase 14 — Keyframe-Selector RED.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 14 (Tier 2 Building-Blocks)
"""
from __future__ import annotations

import pytest


@pytest.fixture
def scenes_two():
    from services.video_pipeline.primitives.scene_detect import Scene
    return [
        Scene(start_s=0.0, end_s=4.0, index=0),
        Scene(start_s=4.0, end_s=10.0, index=1),
    ]


def test_mode_mid_one_per_scene(scenes_two):
    from services.video_pipeline.primitives.keyframe_selector import select_keyframes
    kfs = select_keyframes(scenes_two, mode="mid")
    assert len(kfs) == 2
    assert kfs[0].scene_idx == 0
    assert kfs[0].role == "mid"
    assert kfs[0].time_s == pytest.approx(2.0)
    assert kfs[1].scene_idx == 1
    assert kfs[1].time_s == pytest.approx(7.0)


def test_mode_anchors_3_three_per_scene(scenes_two):
    from services.video_pipeline.primitives.keyframe_selector import select_keyframes
    kfs = select_keyframes(scenes_two, mode="anchors_3")
    assert len(kfs) == 6
    roles = [k.role for k in kfs]
    assert roles.count("start") == 2
    assert roles.count("mid") == 2
    assert roles.count("end") == 2


def test_anchors_within_scene_bounds(scenes_two):
    from services.video_pipeline.primitives.keyframe_selector import select_keyframes
    kfs = select_keyframes(scenes_two, mode="anchors_3")
    by_scene = {0: [k for k in kfs if k.scene_idx == 0],
                1: [k for k in kfs if k.scene_idx == 1]}
    for idx, sc in enumerate(scenes_two):
        for k in by_scene[idx]:
            assert sc.start_s <= k.time_s < sc.end_s


def test_uniform_extras_added(scenes_two):
    from services.video_pipeline.primitives.keyframe_selector import select_keyframes
    kfs = select_keyframes(scenes_two, mode="mid", uniform_every_s=2.0)
    # uniform-extras zwischen 0 und 10s alle 2s = 5 extras (0,2,4,6,8)
    # + 2 mid keyframes - dedupe (mid bei 2 und 7 sind nicht 0/2/4/6/8 collision?)
    # mid scene 0 = 2.0 (Kollision mit uniform 2.0 -> dedupe)
    # mid scene 1 = 7.0 (kein collision)
    # Erwartet >= 6
    assert len(kfs) >= 6
    times = sorted(k.time_s for k in kfs)
    assert 0.0 in times
    assert 2.0 in times
    assert 7.0 in times


def test_invalid_mode_raises(scenes_two):
    from services.video_pipeline.primitives.keyframe_selector import select_keyframes
    with pytest.raises(ValueError):
        select_keyframes(scenes_two, mode="bogus")


def test_empty_scenes_returns_empty():
    from services.video_pipeline.primitives.keyframe_selector import select_keyframes
    assert select_keyframes([], mode="mid") == []
