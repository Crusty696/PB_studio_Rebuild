"""F-8 (B-340): scene<->embedding alignment when a frame is unreadable.

_sample_frames must drop an unreadable scene from BOTH the kept-scenes list
and the frames list, so the caller's zip(scenes, embeddings) cannot shift
embeddings onto the wrong scenes.
"""
from __future__ import annotations

import numpy as np

from services.brain_v3.video.video_embedder import SceneSpec, Siglip2VideoEmbedder


class _FakeCV2:
    CAP_PROP_POS_FRAMES = 1
    COLOR_BGR2RGB = 4

    @staticmethod
    def cvtColor(frame, _code):
        return frame


class _FakeCap:
    """Reads succeed for every scene except the one at fail_index."""

    def __init__(self, fail_index: int):
        self._i = -1
        self._fail = fail_index

    def set(self, _prop, _val):
        # set is called once per scene before read; track scene index
        self._i += 1

    def read(self):
        if self._i == self._fail:
            return False, None
        return True, np.zeros((4, 4, 3), dtype=np.uint8)


def test_sample_frames_keeps_scene_frame_alignment():
    scenes = [
        SceneSpec(start_time=0.0, end_time=1.0),
        SceneSpec(start_time=1.0, end_time=2.0),   # this frame will be unreadable
        SceneSpec(start_time=2.0, end_time=3.0),
    ]
    cap = _FakeCap(fail_index=1)
    kept_scenes, frames = Siglip2VideoEmbedder._sample_frames(
        object(), cap, scenes, fps=30.0, n_frames=300, cv2_mod=_FakeCV2()
    )
    # The middle scene is dropped from BOTH lists -> equal length, aligned.
    assert len(kept_scenes) == len(frames) == 2
    assert kept_scenes[0].start_time == 0.0
    assert kept_scenes[1].start_time == 2.0  # NOT 1.0 (the dropped one)
