"""B-832: gesetzter Vibe beeinflusst regulaeres Clip-Matching aktiv."""

from dataclasses import dataclass

import numpy as np

from services.pacing_edit_helpers import (
    AudioContext,
    CrossModalMatcher,
    _match_video_for_segment,
)
from services.pacing_service import _apply_vibe_to_audio_context


def _world():
    video_info = {
        1: {"path": "/v/one.mp4", "duration": 8.0},
        2: {"path": "/v/two.mp4", "duration": 8.0},
    }
    metadata = [
        {"video_path": "/v/one.mp4", "scene_start": 0.0,
         "scene_end": 8.0, "motion_score": 0.5},
        {"video_path": "/v/two.mp4", "scene_start": 0.0,
         "scene_end": 8.0, "motion_score": 0.5},
    ]
    fitness = {(0, "TRANSITION"): 0.5, (1, "TRANSITION"): 0.5}
    embeddings = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    return video_info, metadata, fitness, embeddings


def _pick(vibe="", vibe_embedding=None, cross_modal_matcher=None):
    video_info, metadata, fitness, embeddings = _world()
    return _match_video_for_segment(
        seg_start=0.0,
        seg_end=4.0,
        vibe=vibe,
        video_info=video_info,
        available_ids=[1, 2],
        clip_offsets={1: 0.0, 2: 0.0},
        used_recently=[],
        energy_per_beat=[0.5] * 10,
        beats=[float(i) for i in range(10)],
        section_type="TRANSITION",
        fitness_matrix=fitness,
        clip_embeddings=embeddings,
        clip_metadata=metadata,
        cross_modal_matcher=cross_modal_matcher,
        vibe_embedding=vibe_embedding,
    )


def test_vibe_kippt_basisgleichen_legacy_match_auf_semantischen_treffer():
    assert _pick()[0] == 1  # kanonischer Tie-Break ohne Vibe

    chosen = _pick(vibe="blue water", vibe_embedding=np.array([0.0, 1.0]))

    assert chosen[0] == 2


def test_vibe_wirkt_auch_im_cross_modal_matcher():
    matcher = CrossModalMatcher(AudioContext())

    chosen = _pick(
        vibe="blue water",
        vibe_embedding=np.array([0.0, 1.0]),
        cross_modal_matcher=matcher,
    )

    assert chosen[0] == 2


def test_leerer_vibe_ignoriert_vorbereitetes_embedding():
    chosen = _pick(vibe="", vibe_embedding=np.array([0.0, 1.0]))

    assert chosen[0] == 1


def test_vibe_ersetzt_studio_brain_mood_vektor():
    @dataclass(frozen=True)
    class Context:
        at_audio_mood_vec: np.ndarray | None

    original = Context(at_audio_mood_vec=np.array([1.0, 0.0]))

    updated = _apply_vibe_to_audio_context(
        original, np.array([0.0, 1.0]))

    assert np.array_equal(updated.at_audio_mood_vec, np.array([0.0, 1.0]))
    assert np.array_equal(original.at_audio_mood_vec, np.array([1.0, 0.0]))
