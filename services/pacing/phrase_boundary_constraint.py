"""Slice 1 / FR-S1-5: Phrase-Boundary forced cluster-switch.

An 4/8/16-bar Phrase-Boundaries soll der nächste Clip einen anderen
Mood-Cluster haben als der Vorgänger — das verhindert dass die Section
"hängen bleibt".

Penalty (1.0) wenn an Boundary derselbe mood; sonst 0.0. Wird im Scorer
als negative Reward-Komponente konsumiert.
"""
from __future__ import annotations

from typing import Sequence


def is_phrase_boundary(
    beat_idx: int,
    beats_per_bar: int = 4,
    phrase_bars: Sequence[int] = (4, 8, 16),
) -> bool:
    """True wenn `beat_idx` exakt auf einer Phrase-Grenze liegt.

    Beat 0 (Track-Start) zählt nicht als Boundary.
    """
    if beat_idx <= 0 or beats_per_bar <= 0:
        return False
    for bars in phrase_bars:
        period = bars * beats_per_bar
        if period > 0 and beat_idx % period == 0:
            return True
    return False


def phrase_boundary_penalty(
    beat_idx: int,
    prev_mood: str | None,
    candidate_mood: str | None,
    beats_per_bar: int = 4,
    phrase_bars: Sequence[int] = (4, 8, 16),
) -> float:
    """1.0 wenn Boundary + selber mood-Cluster, sonst 0.0.

    Kein Vorgänger oder kein Boundary → 0.0.
    """
    if prev_mood is None or candidate_mood is None:
        return 0.0
    if not is_phrase_boundary(beat_idx, beats_per_bar, phrase_bars):
        return 0.0
    return 1.0 if prev_mood == candidate_mood else 0.0
