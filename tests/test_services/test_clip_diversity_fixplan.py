"""Fixplan 2026-07-07 Schritt 3: Diversitaet der Clip-Auswahl.

Reproduziert das reale Fehlerbild (deterministischer argmax + schwache
Fenster-Freshness -> dasselbe Video gewinnt fast jedes Segment) und sichert:
Nutzungs-Cap, globale Freshness-Strafe, Top-K-Sampling.
"""
import random
from collections import Counter

import numpy as np
import pytest

from services.pacing_edit_helpers import (
    _compute_clip_fitness,
    _match_video_by_motion,
    _match_video_for_segment,
)


N_VIDEOS = 20
N_SEGMENTS = 58


def _make_world(n=N_VIDEOS):
    """Synthetisches Material: Video 0 ist der statische 'Spitzenreiter'."""
    rng = np.random.default_rng(42)
    video_info = {}
    clip_metadata = []
    fitness_matrix = {}
    for i in range(n):
        vid = i + 1
        path = f"/videos/clip_{i:02d}.mp4"
        video_info[vid] = {
            "path": path,
            "duration": 8.0,
            "scenes": [{"id": vid * 100, "start": 0.0, "end": 8.0,
                        "energy": 0.5}],
        }
        clip_metadata.append({
            "video_path": path,
            "scene_start": 0.0,
            "scene_end": 8.0,
            # Spitzenreiter: bester Motion-Match; Rest leicht schlechter
            "motion_score": 0.5 if i == 0 else 0.5 + 0.01 * i,
        })
        # Mood-Matrix: Video 0 dominiert jede Section
        fitness_matrix[(i, "BREAKDOWN")] = 0.95 if i == 0 else 0.5
    clip_embeddings = rng.normal(size=(n, 16)).astype(np.float32)
    return video_info, clip_metadata, fitness_matrix, clip_embeddings


def _run_selection_loop(max_uses, rng, n_segments=N_SEGMENTS):
    video_info, clip_metadata, fitness_matrix, clip_embeddings = _make_world()
    available = list(video_info.keys())
    used_recently: list[int] = []
    usage_counts: dict[int, int] = {}
    picks = []
    prev_idx = None
    for s in range(n_segments):
        vid, _src, clip_idx = _match_video_for_segment(
            seg_start=float(s * 5), seg_end=float(s * 5 + 5), vibe="",
            video_info=video_info, available_ids=available,
            clip_offsets={v: 0.0 for v in available},
            used_recently=used_recently,
            energy_per_beat=[0.5] * 1000, beats=[float(b) for b in range(1000)],
            section_type="BREAKDOWN",
            fitness_matrix=fitness_matrix,
            clip_embeddings=clip_embeddings,
            clip_metadata=clip_metadata,
            prev_clip_idx=prev_idx,
            cross_modal_matcher=None,
            usage_counts=usage_counts,
            max_uses=max_uses,
            rng=rng,
        )
        assert vid != -1
        picks.append(vid)
        used_recently.append(vid)
        used_recently[:] = used_recently[-10:]
        usage_counts[vid] = usage_counts.get(vid, 0) + 1
        prev_idx = clip_idx
    return picks


class TestDiversity:
    def test_usage_cap_is_enforced(self):
        max_uses = int(np.ceil(N_SEGMENTS / N_VIDEOS)) + 1  # = 4
        picks = _run_selection_loop(max_uses, rng=random.Random(7))
        counts = Counter(picks)
        assert max(counts.values()) <= max_uses, counts

    def test_pool_is_broadly_used(self):
        """Abnahme-Kriterium Schritt 9.2: >= 75% des Pools verwendet."""
        max_uses = int(np.ceil(N_SEGMENTS / N_VIDEOS)) + 1
        picks = _run_selection_loop(max_uses, rng=random.Random(7))
        assert len(set(picks)) >= int(0.75 * N_VIDEOS)

    def test_seed_reproducible(self):
        a = _run_selection_loop(4, rng=random.Random(123))
        b = _run_selection_loop(4, rng=random.Random(123))
        assert a == b

    def test_without_cap_and_rng_old_behavior_would_repeat(self):
        """Regressions-Anker: ohne Cap+Sampling dominiert der Spitzenreiter.

        (Dokumentiert das Alt-Verhalten; Fenster-Freshness allein laesst
        Video 1 nach 3 Segmenten wieder gewinnen.)
        """
        picks = _run_selection_loop(max_uses=None, rng=None)
        counts = Counter(picks)
        assert counts[1] > N_SEGMENTS * 0.2  # Spitzenreiter gewinnt oft


class TestFreshnessGlobalPenalty:
    def _fitness(self, usage_count):
        emb = np.ones((3, 4), dtype=np.float32)
        return _compute_clip_fitness(
            clip_idx=0, section_type="BREAKDOWN", energy_value=0.5,
            motion_score=0.5, scene_duration=5.0, segment_duration=5.0,
            prev_clip_idx=None, clip_embeddings=emb, used_recently=[],
            fitness_matrix={(0, "BREAKDOWN"): 0.8}, video_id=1,
            usage_count=usage_count,
        )

    def test_usage_count_lowers_fitness(self):
        assert self._fitness(0) > self._fitness(2) > self._fitness(4)


class TestMatchByMotionCap:
    def test_capped_videos_skipped(self):
        video_info = {
            1: {"path": "a", "scenes": [{"start": 0.0, "energy": 0.5}]},
            2: {"path": "b", "scenes": [{"start": 0.0, "energy": 0.5}]},
        }
        vid, _ = _match_video_by_motion(
            0.5, video_info, [1, 2], used_recently=[],
            usage_counts={1: 5, 2: 0}, max_uses=3,
        )
        assert vid == 2

    def test_all_capped_falls_back(self):
        video_info = {1: {"path": "a", "scenes": [{"start": 0.0, "energy": 0.5}]}}
        vid, _ = _match_video_by_motion(
            0.5, video_info, [1], used_recently=[],
            usage_counts={1: 99}, max_uses=3,
        )
        assert vid == 1
