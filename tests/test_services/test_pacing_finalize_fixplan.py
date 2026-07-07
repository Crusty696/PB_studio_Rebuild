"""Pacing-Tuning 2026-07-07: finalize_cut_beats + section-aware Mindestdauer.

Gemessene Probleme des realen Schnitts (Projekt 6262626, 136.4 BPM):
Cuts nur 44% auf Beat, 2/21 Section-Grenzen geschnitten, Timeline-Ende
!= Audio-Ende, DROP nicht schneller geschnitten als WARMUP.
"""
from types import SimpleNamespace

import numpy as np
import pytest

from services.pacing_beat_grid import HARD_MIN_DURATION
from services.pacing_edit_helpers import (
    _enforce_minimum_durations,
    finalize_cut_beats,
)


def _grid(total=100.0, interval=0.5):
    beats = list(np.arange(0.0, total, interval))
    downbeats = list(np.arange(0.0, total, interval * 4))
    return beats, downbeats


def _sec(start, end, stype):
    return SimpleNamespace(start=start, end=end, section_type=stype)


class TestFinalizeCutBeats:
    def test_all_cuts_snap_to_beats(self):
        beats, downbeats = _grid()
        # Drift wie real gemessen: bis 240ms neben dem Beat
        cuts = [0.0, 10.12, 20.24, 30.18, 40.07, 100.0]
        out = finalize_cut_beats(cuts, beats, downbeats, [], 100.0)
        barr = np.array(beats)
        for t in out[1:-1]:
            assert np.min(np.abs(barr - t)) < 0.011, t

    def test_downbeat_preferred_within_200ms(self):
        beats, downbeats = _grid()
        # 10.1 -> naechster Beat 10.0; 10.0 ist auch Downbeat (interval*4=2.0)
        out = finalize_cut_beats([0.0, 10.1, 100.0], beats, downbeats, [], 100.0)
        assert 10.0 in out

    def test_section_boundaries_become_mandatory_cuts(self):
        beats, downbeats = _grid()
        sections = [_sec(0, 30, "WARMUP"), _sec(30, 60, "DROP"),
                    _sec(60, 100, "BREAKDOWN")]
        out = finalize_cut_beats([0.0, 15.0, 45.0, 100.0], beats, downbeats,
                                 sections, 100.0)
        assert 30.0 in out and 60.0 in out

    def test_non_mandatory_neighbor_removed_near_boundary(self):
        beats, downbeats = _grid()
        sections = [_sec(0, 30, "WARMUP"), _sec(30, 100, "DROP")]
        # 29.5 liegt < HARD_MIN*0.6 neben der Pflicht-Grenze 30.0
        out = finalize_cut_beats([0.0, 29.5, 100.0], beats, downbeats,
                                 sections, 100.0)
        assert 30.0 in out
        assert 29.5 not in out

    def test_end_is_exactly_total_duration(self):
        beats, downbeats = _grid(total=120.0)
        # Cuts hinter dem Audio-Ende (real: Ueberhang 427s bei 421.6s Audio)
        out = finalize_cut_beats([0.0, 50.0, 105.0, 108.5], beats, downbeats,
                                 [], 100.0)
        assert out[-1] == 100.0
        assert all(t <= 100.0 for t in out)

    def test_short_tail_merged(self):
        """Kein 4.6s-Loch mehr: zu kurzer Rest vor dem Ende wird verschmolzen."""
        beats, downbeats = _grid()
        out = finalize_cut_beats([0.0, 50.0, 99.0, 100.0], beats, downbeats,
                                 [], 100.0)
        assert out[-1] == 100.0
        assert (out[-1] - out[-2]) >= HARD_MIN_DURATION

    def test_empty_and_zero_duration_safe(self):
        assert finalize_cut_beats([], [], [], [], 0.0) == []
        out = finalize_cut_beats([0.0], [0.0, 1.0], [], [], 10.0)
        assert out[0] == 0.0 and out[-1] == 10.0


class TestSectionMinDurationAuthoritative:
    def test_drop_allows_two_second_segments(self):
        """Vorher: max(HARD_MIN=3.0, DROP=2.0)=3.0 -> DROP nie unter 3s."""
        sections = [_sec(0, 100, "DROP")]
        cuts = [0.0, 2.0, 4.0, 6.0, 100.0]
        out = _enforce_minimum_durations(cuts, sections, 100.0)
        assert 2.0 in out and 4.0 in out and 6.0 in out

    def test_breakdown_still_enforces_six_seconds(self):
        sections = [_sec(0, 100, "BREAKDOWN")]
        cuts = [0.0, 3.0, 6.0, 12.0, 100.0]
        out = _enforce_minimum_durations(cuts, sections, 100.0)
        assert 3.0 not in out  # 3s < BREAKDOWN-Minimum 6s
        assert 6.0 in out
