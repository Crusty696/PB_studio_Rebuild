"""Fixplan 2026-07-07: Caption-Mood (scenes.ai_mood) fliesst in die Clip-Fitness.

Vorher wurde der vom Vision-LLM erkannte Bildinhalt (mood) im Standard-
Auto-Edit ueberhaupt nicht verwendet — nur SigLIP-Vektor-Naehe.
"""
import numpy as np

from services.pacing_edit_helpers import (
    _caption_mood_score,
    _compute_clip_fitness,
)


class TestCaptionMoodScore:
    def test_drop_prefers_energetic(self):
        assert _caption_mood_score("DROP", "energetic") > _caption_mood_score("DROP", "calm")

    def test_breakdown_prefers_calm_ambient(self):
        assert _caption_mood_score("BREAKDOWN", "ambient") > _caption_mood_score("BREAKDOWN", "energetic")
        assert _caption_mood_score("BREAKDOWN", "calm") > 0.8

    def test_missing_mood_returns_none(self):
        assert _caption_mood_score("DROP", None) is None
        assert _caption_mood_score("DROP", "") is None

    def test_unknown_section_or_mood_neutral(self):
        assert _caption_mood_score("INTERLUDE", "energetic") == 0.5
        assert _caption_mood_score("DROP", "melancholic") == 0.5

    def test_case_insensitive(self):
        assert _caption_mood_score("drop", "Energetic") == _caption_mood_score("DROP", "energetic")


class TestFitnessBlend:
    def _fitness(self, section, ai_mood):
        emb = np.ones((2, 4), dtype=np.float32)
        return _compute_clip_fitness(
            clip_idx=0, section_type=section, energy_value=0.5,
            motion_score=0.5, scene_duration=5.0, segment_duration=5.0,
            prev_clip_idx=None, clip_embeddings=emb, used_recently=[],
            fitness_matrix={(0, section): 0.5}, video_id=1,
            ai_mood=ai_mood,
        )

    def test_matching_mood_raises_fitness_on_drop(self):
        assert self._fitness("DROP", "energetic") > self._fitness("DROP", None)
        assert self._fitness("DROP", "energetic") > self._fitness("DROP", "calm")

    def test_matching_mood_raises_fitness_on_breakdown(self):
        assert self._fitness("BREAKDOWN", "ambient") > self._fitness("BREAKDOWN", "energetic")

    def test_without_mood_unchanged_baseline(self):
        """Ohne ai_mood identisches Verhalten wie vor dem Feature."""
        assert self._fitness("DROP", None) == self._fitness("DROP", "")
