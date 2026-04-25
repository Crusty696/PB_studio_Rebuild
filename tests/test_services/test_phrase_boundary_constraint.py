"""FR-S1-5 / Task-S1-5: Phrase-Boundary forced cluster-switch.

An 4/8/16-Bar-Boundaries soll der gewählte Clip einen anderen mood-cluster
haben als sein Vorgänger. Der Constraint liefert einen Penalty (0..1)
pro Kandidat.
"""
import pytest

from services.pacing.phrase_boundary_constraint import (
    is_phrase_boundary,
    phrase_boundary_penalty,
)


def test_phrase_boundary_at_4_bars():
    # bpm 120, 4 beats/bar → bar = 2s, 4-bar phrase = 8s
    assert is_phrase_boundary(beat_idx=16, beats_per_bar=4, phrase_bars=(4,))
    assert is_phrase_boundary(beat_idx=32, beats_per_bar=4, phrase_bars=(4, 8))


def test_not_phrase_boundary_off_grid():
    assert not is_phrase_boundary(beat_idx=15, beats_per_bar=4, phrase_bars=(4,))
    assert not is_phrase_boundary(beat_idx=17, beats_per_bar=4, phrase_bars=(4,))


def test_phrase_boundary_zero_is_not_a_boundary():
    """Beat 0 = Track-Start, kein logischer Boundary."""
    assert not is_phrase_boundary(beat_idx=0, beats_per_bar=4, phrase_bars=(4,))


def test_penalty_high_when_same_cluster_at_boundary():
    p = phrase_boundary_penalty(
        beat_idx=16, prev_mood="energetic", candidate_mood="energetic",
        beats_per_bar=4, phrase_bars=(4,),
    )
    assert p == 1.0


def test_penalty_zero_when_different_cluster_at_boundary():
    p = phrase_boundary_penalty(
        beat_idx=16, prev_mood="energetic", candidate_mood="calm",
        beats_per_bar=4, phrase_bars=(4,),
    )
    assert p == 0.0


def test_no_penalty_off_boundary_even_same_cluster():
    p = phrase_boundary_penalty(
        beat_idx=15, prev_mood="energetic", candidate_mood="energetic",
        beats_per_bar=4, phrase_bars=(4,),
    )
    assert p == 0.0


def test_no_penalty_when_no_predecessor():
    p = phrase_boundary_penalty(
        beat_idx=16, prev_mood=None, candidate_mood="energetic",
        beats_per_bar=4, phrase_bars=(4,),
    )
    assert p == 0.0
