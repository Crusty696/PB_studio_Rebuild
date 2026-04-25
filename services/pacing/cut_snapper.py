"""Slice 1 / FR-S1-1: Onset-Snap für Cut-Zeitpunkte.

Nimmt Beat-aligned Cuts und schiebt sie auf den nächsten percussiven Onset,
sofern dieser innerhalb von ±max_shift_ms liegt. Subtile aber merklich
hörbare Verbesserung der Schnitt-Präzision auf Trommelschlägen / Snares.

Reuse: `services/onset_rhythm_service.py:OnsetRhythmService.refine_cut_points`
ist die volle Variante mit RhythmAnalysis. Dieser Helper ist die thin-Wrapper-
Variante für die Pacing-Pipeline (FR-S1-1) ohne Service-Dependency.
"""
from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np


def snap_to_onset(
    beat_time: float,
    onsets: Sequence[float] | np.ndarray,
    max_shift_ms: float = 50.0,
) -> float:
    """Snappe `beat_time` auf den nächsten Onset im ±max_shift_ms-Fenster.

    Args:
        beat_time: Cut-Zeitpunkt in Sekunden (typischerweise auf Beat).
        onsets: Liste von Onset-Zeitpunkten in Sekunden.
        max_shift_ms: Maximale Verschiebung in Millisekunden. Default 50ms.

    Returns:
        Geschnappter Zeitpunkt oder unverändert beat_time wenn kein Onset
        im Fenster liegt.
    """
    arr = np.asarray(onsets, dtype=np.float64)
    if arr.size == 0:
        return float(beat_time)
    dists = np.abs(arr - float(beat_time))
    idx = int(np.argmin(dists))
    # Float-Toleranz: 0.05s in float64 ≠ exakt 50.0ms → 1e-6 Slack akzeptiert.
    if float(dists[idx]) * 1000.0 <= max_shift_ms + 1e-6:
        return float(arr[idx])
    return float(beat_time)


def snap_cuts(
    cut_times: Iterable[float],
    onsets: Sequence[float] | np.ndarray,
    max_shift_ms: float = 50.0,
) -> list[float]:
    """Batch-Variante: snappt eine Liste von Cuts, dedupliziert + sortiert."""
    snapped = {round(snap_to_onset(t, onsets, max_shift_ms), 6) for t in cut_times}
    return sorted(snapped)
