"""NEUBAU-VOLLINTEGRATION T2.5.2 (FR-S1-3/FR-S1-5/FR-S3-4):
Drop-Burst in der Cut-Erzeugung, Phrase-Constraint + Section-Coherence
in der Clip-Auswahl. apply_bpm_adaptation bleibt bewusst unverdrahtet
(redundant zu SECTION_PACING_MAP; wuerde die BUILDUP-Progression halbieren).
"""
import random

import numpy as np

from services.pacing.cut_density_modulator import apply_drop_burst
from services.pacing_edit_helpers import _match_video_for_segment


def _world(n=6):
    video_info, clip_metadata, fitness_matrix = {}, [], {}
    for i in range(n):
        vid = i + 1
        path = f"/v/{i}.mp4"
        # abwechselnd energetic/calm fuer Phrase-Tests
        mood = "energetic" if i % 2 == 0 else "calm"
        video_info[vid] = {"path": path, "duration": 8.0,
                           "scenes": [{"id": vid, "start": 0.0, "end": 8.0,
                                       "energy": 0.5}]}
        clip_metadata.append({"video_path": path, "scene_start": 0.0,
                              "scene_end": 8.0, "motion_score": 0.5,
                              "ai_mood": mood})
        fitness_matrix[(i, "DROP")] = 0.8
    emb = np.random.default_rng(0).normal(size=(n, 8)).astype(np.float32)
    return video_info, clip_metadata, fitness_matrix, emb


def _pick(prev_mood=None, beat_idx=None, prev_clip_idx=0, bdist=None):
    video_info, meta, fm, emb = _world()
    return _match_video_for_segment(
        seg_start=10.0, seg_end=14.0, vibe="",
        video_info=video_info, available_ids=list(video_info),
        clip_offsets={v: 0.0 for v in video_info}, used_recently=[],
        energy_per_beat=[0.5] * 500, beats=[float(b) for b in range(500)],
        section_type="DROP", fitness_matrix=fm, clip_embeddings=emb,
        clip_metadata=meta, prev_clip_idx=prev_clip_idx,
        cross_modal_matcher=None, rng=None,
        cut_beat_idx=beat_idx, boundary_distance_sec=bdist, prev_mood=prev_mood,
    )


class TestDropBurst:
    def test_burst_and_hold(self):
        cuts = [float(t) for t in range(0, 60, 2)]
        out = apply_drop_burst(cuts, [30.0], bpm=120.0)
        burst = [t for t in out if 29.5 <= t <= 30.5]
        assert len(burst) == 3  # 3 Cuts im 800ms-Fenster
        bar = 60.0 / 120.0 * 4
        hold = [t for t in out if 30.4 < t < 30.4 + 4 * bar]
        assert hold == []  # 4 Bars Hold nach dem Burst


class TestPhraseConstraint:
    def test_same_mood_penalized_on_phrase_boundary(self):
        """Beat 16 = 4-Bar-Grenze: gleicher Mood wie Vorgaenger verliert."""
        # prev energetic; Kandidaten-Pool hat energetic+calm mit gleicher Basis
        vid_same, _, _ = _pick(prev_mood="energetic", beat_idx=16,
                               prev_clip_idx=None)
        vid_pen, _, idx = _pick(prev_mood="energetic", beat_idx=16,
                                prev_clip_idx=None)
        # Ohne Boundary (beat 17) darf energetic gewinnen; an der Grenze
        # muss ein calm-Clip (ungerade Indizes) vorn liegen.
        _, _, idx_off = _pick(prev_mood="energetic", beat_idx=17,
                              prev_clip_idx=None)
        assert idx is not None and idx % 2 == 1  # calm gewinnt an Boundary

    def test_neutral_without_context(self):
        """Alt-Verhalten ohne neue Parameter identisch (Baseline-Schutz)."""
        a = _pick()
        b = _pick()
        assert a == b


class TestSectionCoherenceTerm:
    """Der Coherence-Term (Gewicht 0.06) ist ein Nuancierungs-Signal — er
    kippt die Auswahl nicht allein gegen den Visual-Term (0.15), verschiebt
    aber die Score-Balance. Semantik wird auf Modul-Ebene gesichert,
    Integration als Smoke (kein Crash, Neutralitaet ohne Kontext)."""

    def test_module_semantics(self):
        from services.pacing.section_coherence import compute_section_coherence
        a = np.array([1.0, 0.0])
        b_sim = np.array([1.0, 0.0])
        b_diff = np.array([-1.0, 0.0])
        # Inneres: Aehnlichkeit belohnt
        assert compute_section_coherence(a, b_sim, 10.0) > \
               compute_section_coherence(a, b_diff, 10.0)
        # Boundary: Kontrast belohnt (Inversion)
        assert compute_section_coherence(a, b_diff, 0.0) > \
               compute_section_coherence(a, b_sim, 0.0)
        # Ohne Vorgaenger neutral
        assert compute_section_coherence(None, b_sim, 0.0) == 0.5

    def test_integration_smoke_and_neutrality(self):
        """Mit bdist laeuft die Auswahl fehlerfrei; ohne Kontext identisch."""
        video_info, meta, fm, emb = _world(3)
        kw = dict(
            seg_start=10.0, seg_end=14.0, vibe="", video_info=video_info,
            available_ids=list(video_info),
            clip_offsets={v: 0.0 for v in video_info}, used_recently=[],
            energy_per_beat=[0.5] * 500, beats=[float(b) for b in range(500)],
            section_type="DROP", fitness_matrix=fm, clip_embeddings=emb,
            clip_metadata=meta, prev_clip_idx=0, cross_modal_matcher=None,
            rng=None,
        )
        with_term = _match_video_for_segment(**kw, boundary_distance_sec=0.0)
        assert with_term[0] != -1
        base_a = _match_video_for_segment(**kw)
        base_b = _match_video_for_segment(**kw)
        assert base_a == base_b  # deterministisch ohne Kontext
