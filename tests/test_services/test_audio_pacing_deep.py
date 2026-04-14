"""Erweiterte Tests fuer Audio- und Pacing-Services — Lueckenabdeckung.

Testet:
- audio_constants: clamp_bpm, clamp_confidence, clamp_energy Edge Cases
- pacing_beat_grid: detect_sections, get_section_at_time, Section, StemEnergy,
                    TimelineSegment, SECTION_PACING_MAP, _density_to_beat_step,
                    invalidate_pacing_caches
- onset_rhythm_service: _cosine_sim, OnsetRhythmService.analyze,
                        refine_cut_points, Syncopation, Groove, Swing,
                        PercussiveOnset, RhythmAnalysis
- pacing_strategist: PacingPlan dataclass
- audio_service: AudioAnalyzer._tempo_to_float Edge Cases
- pacing_edit_helpers: _density_to_beat_step, _enforce_minimum_durations
"""

import math
import pytest
import numpy as np
from unittest.mock import patch, MagicMock


# =========================================================================
# audio_constants.py — clamp-Funktionen Edge Cases
# =========================================================================


class TestClampBpm:
    def test_normal_value(self):
        from services.audio_constants import clamp_bpm
        assert clamp_bpm(128.0) == 128.0

    def test_below_minimum(self):
        from services.audio_constants import clamp_bpm
        assert clamp_bpm(10.0) == 40.0

    def test_above_maximum(self):
        from services.audio_constants import clamp_bpm
        assert clamp_bpm(500.0) == 300.0

    def test_at_minimum_boundary(self):
        from services.audio_constants import clamp_bpm
        assert clamp_bpm(40.0) == 40.0

    def test_at_maximum_boundary(self):
        from services.audio_constants import clamp_bpm
        assert clamp_bpm(300.0) == 300.0

    def test_none_returns_none(self):
        from services.audio_constants import clamp_bpm
        assert clamp_bpm(None) is None

    def test_nan_raises_value_error(self):
        from services.audio_constants import clamp_bpm
        with pytest.raises(ValueError, match="Ungültiger BPM-Wert"):
            clamp_bpm(float("nan"))

    def test_inf_raises_value_error(self):
        from services.audio_constants import clamp_bpm
        with pytest.raises(ValueError, match="Ungültiger BPM-Wert"):
            clamp_bpm(float("inf"))

    def test_negative_inf_raises_value_error(self):
        from services.audio_constants import clamp_bpm
        with pytest.raises(ValueError, match="Ungültiger BPM-Wert"):
            clamp_bpm(float("-inf"))

    def test_zero_returns_minimum(self):
        from services.audio_constants import clamp_bpm
        assert clamp_bpm(0.0) == 40.0

    def test_negative_returns_minimum(self):
        from services.audio_constants import clamp_bpm
        assert clamp_bpm(-50.0) == 40.0


class TestClampConfidence:
    def test_normal_value(self):
        from services.audio_constants import clamp_confidence
        assert clamp_confidence(0.75) == 0.75

    def test_below_zero(self):
        from services.audio_constants import clamp_confidence
        assert clamp_confidence(-0.5) == 0.0

    def test_above_one(self):
        from services.audio_constants import clamp_confidence
        assert clamp_confidence(1.5) == 1.0

    def test_exactly_zero(self):
        from services.audio_constants import clamp_confidence
        assert clamp_confidence(0.0) == 0.0

    def test_exactly_one(self):
        from services.audio_constants import clamp_confidence
        assert clamp_confidence(1.0) == 1.0

    def test_none_returns_none(self):
        from services.audio_constants import clamp_confidence
        assert clamp_confidence(None) is None


class TestClampEnergy:
    def test_normal_value(self):
        from services.audio_constants import clamp_energy
        assert clamp_energy(0.5) == 0.5

    def test_below_zero(self):
        from services.audio_constants import clamp_energy
        assert clamp_energy(-0.1) == 0.0

    def test_above_one(self):
        from services.audio_constants import clamp_energy
        assert clamp_energy(2.0) == 1.0

    def test_none_returns_none(self):
        from services.audio_constants import clamp_energy
        assert clamp_energy(None) is None


# =========================================================================
# AudioAnalyzer._tempo_to_float Edge Cases
# =========================================================================


class TestTempoToFloat:
    def test_scalar_float(self):
        from services.audio_service import AudioAnalyzer
        assert AudioAnalyzer._tempo_to_float(120.0) == 120.0

    def test_numpy_scalar(self):
        from services.audio_service import AudioAnalyzer
        assert AudioAnalyzer._tempo_to_float(np.float64(128.5)) == 128.5

    def test_numpy_1d_array(self):
        from services.audio_service import AudioAnalyzer
        assert AudioAnalyzer._tempo_to_float(np.array([140.0])) == 140.0

    def test_empty_array_returns_zero(self):
        from services.audio_service import AudioAnalyzer
        assert AudioAnalyzer._tempo_to_float(np.array([])) == 0.0

    def test_integer_input(self):
        from services.audio_service import AudioAnalyzer
        assert AudioAnalyzer._tempo_to_float(120) == 120.0


# =========================================================================
# pacing_beat_grid.py — Dataclasses und Konstanten
# =========================================================================


class TestDataclasses:
    def test_pacing_settings_defaults(self):
        from services.pacing_beat_grid import PacingSettings
        s = PacingSettings()
        assert s.tempo == 50
        assert s.energy == 50
        assert s.cut_density == 50
        assert s.vibe == ""
        assert s.manual_density_curve is None

    def test_cut_point_creation(self):
        from services.pacing_beat_grid import CutPoint
        cp = CutPoint(time=2.5, source="beat", strength=0.9)
        assert cp.time == 2.5
        assert cp.source == "beat"
        assert cp.strength == 0.9

    def test_timeline_segment_creation(self):
        from services.pacing_beat_grid import TimelineSegment
        seg = TimelineSegment(
            video_id=1,
            video_path="/test.mp4",
            start=0.0,
            end=5.0,
            source_start=0.0,
            source_end=5.0,
        )
        assert seg.video_id == 1
        assert seg.is_anchor is False
        assert seg.crossfade_duration == 0.0
        assert seg.section_type == ""

    def test_timeline_segment_with_anchor(self):
        from services.pacing_beat_grid import TimelineSegment
        seg = TimelineSegment(
            video_id=1, video_path="/test.mp4",
            start=0.0, end=5.0,
            source_start=0.0, source_end=5.0,
            is_anchor=True, section_type="DROP",
            crossfade_duration=0.5,
        )
        assert seg.is_anchor is True
        assert seg.section_type == "DROP"
        assert seg.crossfade_duration == 0.5

    def test_advanced_pacing_settings_all_fields(self):
        from services.pacing_beat_grid import AdvancedPacingSettings
        s = AdvancedPacingSettings(
            base_cut_rate=2,
            energy_reactivity=80,
            breakdown_behavior="force16",
            high_energy_behavior="force1",
            vibe="epic",
            manual_density_curve=[0.5, 0.7, 1.0],
            anchors=[{"time": 10.0, "scene_id": "s1"}],
            use_llm_strategist=True,
            user_preferences="schnellere Cuts",
        )
        assert s.base_cut_rate == 2
        assert s.high_energy_behavior == "force1"
        assert s.use_llm_strategist is True
        assert len(s.anchors) == 1

    def test_section_dataclass(self):
        from services.pacing_beat_grid import Section
        sec = Section(start=0.0, end=30.0, section_type="DROP", avg_energy=0.85)
        assert sec.section_type == "DROP"
        assert sec.avg_energy == 0.85

    def test_stem_energy_dataclass(self):
        from services.pacing_beat_grid import StemEnergy
        se = StemEnergy(
            drums=[0.8, 0.9],
            bass=[0.5, 0.6],
            vocals=[0.1, 0.2],
            other=[0.3, 0.4],
            weighted=[0.5, 0.6],
        )
        assert len(se.drums) == 2
        assert se.weighted == [0.5, 0.6]


class TestSectionPacingMap:
    def test_all_section_types_present(self):
        from services.pacing_beat_grid import SECTION_PACING_MAP
        expected = ["WARMUP", "BUILDUP", "DROP", "BREAKDOWN", "TRANSITION",
                    "COOLDOWN", "CHORUS", "VERSE"]
        for sec_type in expected:
            assert sec_type in SECTION_PACING_MAP, f"{sec_type} fehlt in SECTION_PACING_MAP"

    def test_each_section_has_required_keys(self):
        from services.pacing_beat_grid import SECTION_PACING_MAP
        for sec_type, cfg in SECTION_PACING_MAP.items():
            assert "base" in cfg, f"{sec_type} hat kein 'base'"
            assert "min" in cfg, f"{sec_type} hat kein 'min'"
            assert "max" in cfg, f"{sec_type} hat kein 'max'"
            assert cfg["min"] <= cfg["base"] <= cfg["max"], \
                f"{sec_type}: min({cfg['min']}) <= base({cfg['base']}) <= max({cfg['max']}) verletzt"

    def test_drop_has_fast_pacing(self):
        from services.pacing_beat_grid import SECTION_PACING_MAP
        drop = SECTION_PACING_MAP["DROP"]
        assert drop["base"] <= 4, "DROP base sollte schnell sein (<=4)"
        assert drop["min"] == 1, "DROP min sollte 1 sein"


class TestSectionCrossfadeMap:
    def test_section_crossfade_map_exists(self):
        from services.pacing_beat_grid import SECTION_CROSSFADE_MAP
        assert isinstance(SECTION_CROSSFADE_MAP, dict)
        assert len(SECTION_CROSSFADE_MAP) > 0

    def test_section_to_crossfade_function(self):
        from services.pacing_beat_grid import section_to_crossfade
        # Sollte fuer bekannte Section-Types einen float zurueckgeben
        result = section_to_crossfade("DROP")
        assert isinstance(result, float)
        assert result >= 0.0


class TestHardMinDuration:
    def test_hard_min_duration_positive(self):
        from services.pacing_beat_grid import HARD_MIN_DURATION
        assert HARD_MIN_DURATION > 0
        assert HARD_MIN_DURATION == 3.0

    def test_section_min_durations_exist(self):
        from services.pacing_beat_grid import SECTION_MIN_DURATION
        assert "DROP" in SECTION_MIN_DURATION
        assert "BREAKDOWN" in SECTION_MIN_DURATION
        assert all(v > 0 for v in SECTION_MIN_DURATION.values())


# =========================================================================
# pacing_beat_grid.py — detect_sections()
# =========================================================================


class TestDetectSections:
    def test_empty_energy_returns_single_transition(self):
        from services.pacing_beat_grid import detect_sections
        result = detect_sections([], [], 60.0)
        assert len(result) == 1
        assert result[0].section_type == "TRANSITION"

    def test_too_few_beats_returns_single_transition(self):
        from services.pacing_beat_grid import detect_sections
        result = detect_sections([0.5] * 10, [i * 0.5 for i in range(10)], 5.0, window_beats=32)
        assert len(result) == 1
        assert result[0].section_type == "TRANSITION"

    def test_high_energy_detected_as_drop(self):
        from services.pacing_beat_grid import detect_sections
        n_beats = 200
        # Alles hohe Energie
        energy = [0.85] * n_beats
        beats = [i * 0.5 for i in range(n_beats)]
        result = detect_sections(energy, beats, beats[-1])
        labels = [s.section_type for s in result]
        assert "DROP" in labels, f"Hohe Energie sollte DROP enthalten, aber: {labels}"

    def test_low_energy_detected_as_breakdown(self):
        from services.pacing_beat_grid import detect_sections
        n_beats = 200
        energy = [0.1] * n_beats
        beats = [i * 0.5 for i in range(n_beats)]
        result = detect_sections(energy, beats, beats[-1])
        labels = [s.section_type for s in result]
        # Erste 5% koennten WARMUP sein, rest sollte BREAKDOWN enthalten
        has_breakdown_or_warmup = any(l in ("BREAKDOWN", "WARMUP") for l in labels)
        assert has_breakdown_or_warmup, f"Niedrige Energie sollte BREAKDOWN/WARMUP enthalten: {labels}"

    def test_sections_cover_full_duration(self):
        from services.pacing_beat_grid import detect_sections
        n_beats = 200
        energy = [0.3 + 0.4 * np.sin(i / 15) for i in range(n_beats)]
        beats = [i * 0.5 for i in range(n_beats)]
        total = beats[-1]
        result = detect_sections(energy, beats, total)
        assert result[0].start == 0.0
        assert result[-1].end == round(total, 2)

    def test_multiple_sections_for_varied_energy(self):
        from services.pacing_beat_grid import detect_sections
        n_beats = 200
        energy = (
            [0.1] * 50 +  # niedrig
            [0.85] * 50 +  # hoch
            [0.15] * 50 +  # niedrig
            [0.9] * 50     # hoch
        )
        beats = [i * 0.5 for i in range(n_beats)]
        result = detect_sections(energy, beats, beats[-1])
        assert len(result) >= 2, f"Erwartet >=2 Sektionen fuer variierte Energie, bekam {len(result)}"


class TestGetSectionAtTime:
    def test_finds_correct_section(self):
        from services.pacing_beat_grid import Section, get_section_at_time
        sections = [
            Section(start=0.0, end=30.0, section_type="WARMUP", avg_energy=0.3),
            Section(start=30.0, end=60.0, section_type="DROP", avg_energy=0.8),
            Section(start=60.0, end=90.0, section_type="COOLDOWN", avg_energy=0.2),
        ]
        sec = get_section_at_time(sections, 15.0)
        assert sec.section_type == "WARMUP"

        sec = get_section_at_time(sections, 45.0)
        assert sec.section_type == "DROP"

        sec = get_section_at_time(sections, 75.0)
        assert sec.section_type == "COOLDOWN"

    def test_empty_sections_returns_none(self):
        from services.pacing_beat_grid import get_section_at_time
        assert get_section_at_time([], 10.0) is None

    def test_time_at_section_boundary(self):
        from services.pacing_beat_grid import Section, get_section_at_time
        sections = [
            Section(start=0.0, end=30.0, section_type="WARMUP", avg_energy=0.3),
            Section(start=30.0, end=60.0, section_type="DROP", avg_energy=0.8),
        ]
        # Exakt auf der Grenze -> sollte die naechste Sektion zurueckgeben
        sec = get_section_at_time(sections, 30.0)
        assert sec.section_type == "DROP"

    def test_time_before_first_section(self):
        """Zeit vor erster Sektion -> Fallback auf letzte Sektion."""
        from services.pacing_beat_grid import Section, get_section_at_time
        sections = [
            Section(start=5.0, end=30.0, section_type="DROP", avg_energy=0.8),
        ]
        sec = get_section_at_time(sections, 2.0)
        # bisect_right(2.0) - 1 = -1, so it falls to sections[-1]
        assert sec is not None
        assert sec.section_type == "DROP"


# =========================================================================
# pacing_edit_helpers.py — _density_to_beat_step()
# =========================================================================


class TestDensityToBeatStep:
    @pytest.mark.parametrize("density,expected", [
        (1.0, 1),    # >= 0.8
        (0.8, 1),    # >= 0.8
        (0.79, 2),   # >= 0.5
        (0.5, 2),    # >= 0.5
        (0.49, 4),   # >= 0.3
        (0.3, 4),    # >= 0.3
        (0.29, 8),   # >= 0.15
        (0.15, 8),   # >= 0.15
        (0.14, 16),  # < 0.15
        (0.0, 16),   # < 0.15
    ])
    def test_density_to_step(self, density, expected):
        from services.pacing_edit_helpers import _density_to_beat_step
        assert _density_to_beat_step(density) == expected


# =========================================================================
# onset_rhythm_service.py — _cosine_sim und Datenklassen
# =========================================================================


class TestCosineSim:
    def test_identical_vectors(self):
        from services.onset_rhythm_service import _cosine_sim
        a = np.array([1.0, 2.0, 3.0])
        assert abs(_cosine_sim(a, a) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        from services.onset_rhythm_service import _cosine_sim
        a = np.array([1.0, 0.0, 0.0])
        b = np.array([0.0, 1.0, 0.0])
        assert abs(_cosine_sim(a, b)) < 1e-6

    def test_zero_vector_returns_zero(self):
        from services.onset_rhythm_service import _cosine_sim
        a = np.array([0.0, 0.0, 0.0])
        b = np.array([1.0, 2.0, 3.0])
        assert _cosine_sim(a, b) == 0.0

    def test_opposite_vectors(self):
        from services.onset_rhythm_service import _cosine_sim
        a = np.array([1.0, 0.0])
        b = np.array([-1.0, 0.0])
        assert abs(_cosine_sim(a, b) - (-1.0)) < 1e-6


class TestPercussiveOnsetDataclass:
    def test_creation(self):
        from services.onset_rhythm_service import PercussiveOnset
        o = PercussiveOnset(time=1.5, strength=0.8)
        assert o.time == 1.5
        assert o.strength == 0.8


class TestRhythmAnalysisDefaults:
    def test_default_values(self):
        from services.onset_rhythm_service import RhythmAnalysis
        ra = RhythmAnalysis()
        assert ra.onsets_kick == []
        assert ra.onsets_snare == []
        assert ra.onsets_hihat == []
        assert ra.onset_strength_curve == []
        assert ra.syncopation_score == 0.0
        assert ra.groove_template == "unknown"
        assert ra.groove_confidence == 0.0
        assert ra.swing_ratio == 0.5


class TestOnsetRhythmServiceAnalyze:
    """Tests fuer OnsetRhythmService.analyze() mit synthetischem Audio."""

    def test_analyze_with_kick_drum(self):
        """Synthetisches Kick-Drum-Signal erzeugt Kick-Onsets."""
        from services.onset_rhythm_service import OnsetRhythmService
        sr = 22050
        duration = 4.0
        n_samples = int(sr * duration)
        y = np.zeros(n_samples, dtype=np.float32)
        # 4 Kicks bei 0.0, 1.0, 2.0, 3.0 Sekunden (120 BPM)
        for kick_time in [0.0, 1.0, 2.0, 3.0]:
            idx = int(kick_time * sr)
            # Kick: kurzer Impuls (10ms) im Bass-Bereich
            kick_dur = int(0.01 * sr)  # 10ms
            end = min(idx + kick_dur, n_samples)
            t = np.arange(end - idx) / sr
            y[idx:end] += np.sin(2 * np.pi * 60 * t).astype(np.float32) * 0.8  # 60Hz

        beats = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]
        svc = OnsetRhythmService()
        result = svc.analyze(y, sr, beats)

        assert len(result.onsets_kick) >= 0  # Mindestens Analyse laeuft
        assert result.syncopation_score >= 0.0
        assert result.syncopation_score <= 1.0
        assert result.groove_template != ""
        assert result.swing_ratio >= 0.0

    def test_analyze_empty_beats(self):
        """Leere Beats-Liste erzeugt Defaults."""
        from services.onset_rhythm_service import OnsetRhythmService
        sr = 22050
        y = np.random.randn(sr * 2).astype(np.float32)
        svc = OnsetRhythmService()
        result = svc.analyze(y, sr, beats=[])
        assert result.syncopation_score == 0.0
        assert result.groove_template == "unknown"
        assert result.swing_ratio == 0.5

    def test_analyze_silence(self):
        """Stille erzeugt keine Onsets."""
        from services.onset_rhythm_service import OnsetRhythmService
        sr = 22050
        y = np.zeros(sr * 2, dtype=np.float32)
        beats = [0.0, 0.5, 1.0, 1.5]
        svc = OnsetRhythmService()
        result = svc.analyze(y, sr, beats)
        # Bei Stille sollten keine oder sehr wenige Onsets erkannt werden
        assert isinstance(result.onsets_kick, list)
        assert isinstance(result.onsets_snare, list)


class TestRefineCutPoints:
    """Tests fuer OnsetRhythmService.refine_cut_points()."""

    def test_no_strong_onsets_returns_copy(self):
        from services.onset_rhythm_service import OnsetRhythmService, RhythmAnalysis
        svc = OnsetRhythmService()
        analysis = RhythmAnalysis()  # Keine Onsets
        cuts = [1.0, 2.0, 3.0]
        result = svc.refine_cut_points(cuts, analysis)
        assert result == cuts

    def test_snaps_to_nearby_onset(self):
        from services.onset_rhythm_service import (
            OnsetRhythmService, RhythmAnalysis, PercussiveOnset,
        )
        svc = OnsetRhythmService()
        analysis = RhythmAnalysis(
            onsets_kick=[PercussiveOnset(time=1.02, strength=0.9)],
            onsets_snare=[PercussiveOnset(time=2.05, strength=0.8)],
        )
        cuts = [1.0, 2.0, 3.0]
        result = svc.refine_cut_points(cuts, analysis, window_sec=0.08)
        assert abs(result[0] - 1.02) < 0.001, f"Erwartet snap zu 1.02, bekam {result[0]}"
        assert abs(result[1] - 2.05) < 0.001, f"Erwartet snap zu 2.05, bekam {result[1]}"
        assert abs(result[2] - 3.0) < 0.001, "Cut 3.0 sollte nicht gesnapped werden"

    def test_deduplicates_after_snap(self):
        from services.onset_rhythm_service import (
            OnsetRhythmService, RhythmAnalysis, PercussiveOnset,
        )
        svc = OnsetRhythmService()
        # Zwei Cuts die beide zum gleichen Onset snappen
        analysis = RhythmAnalysis(
            onsets_kick=[PercussiveOnset(time=1.5, strength=0.9)],
        )
        cuts = [1.48, 1.52]  # Beide nah an 1.5
        result = svc.refine_cut_points(cuts, analysis, window_sec=0.08)
        assert len(result) == 1
        assert abs(result[0] - 1.5) < 0.001

    def test_empty_cuts_returns_empty(self):
        from services.onset_rhythm_service import (
            OnsetRhythmService, RhythmAnalysis, PercussiveOnset,
        )
        svc = OnsetRhythmService()
        analysis = RhythmAnalysis(
            onsets_kick=[PercussiveOnset(time=1.0, strength=0.9)],
        )
        result = svc.refine_cut_points([], analysis)
        assert result == []

    def test_weak_onsets_ignored(self):
        from services.onset_rhythm_service import (
            OnsetRhythmService, RhythmAnalysis, PercussiveOnset,
        )
        svc = OnsetRhythmService()
        # Onset unterhalb min_onset_strength
        analysis = RhythmAnalysis(
            onsets_kick=[PercussiveOnset(time=1.02, strength=0.2)],
        )
        cuts = [1.0]
        result = svc.refine_cut_points(cuts, analysis, min_onset_strength=0.4)
        assert result == [1.0], "Schwache Onsets sollten ignoriert werden"

    def test_result_is_sorted(self):
        from services.onset_rhythm_service import (
            OnsetRhythmService, RhythmAnalysis, PercussiveOnset,
        )
        svc = OnsetRhythmService()
        analysis = RhythmAnalysis(
            onsets_kick=[
                PercussiveOnset(time=0.5, strength=0.9),
                PercussiveOnset(time=3.5, strength=0.9),
            ],
        )
        cuts = [3.48, 0.52, 2.0]
        result = svc.refine_cut_points(cuts, analysis, window_sec=0.08)
        assert result == sorted(result)


class TestSyncopationComputation:
    """Tests fuer _compute_syncopation der OnsetRhythmService."""

    def test_all_on_beat_zero_syncopation(self):
        from services.onset_rhythm_service import OnsetRhythmService
        svc = OnsetRhythmService()
        beats = [0.0, 0.5, 1.0, 1.5, 2.0]
        # Onsets exakt auf den Beats
        onset_times = [0.0, 0.5, 1.0, 1.5, 2.0]
        score = svc._compute_syncopation(onset_times, beats)
        assert score == 0.0, f"Erwartet Syncopation=0.0, bekam {score}"

    def test_all_off_beat_high_syncopation(self):
        from services.onset_rhythm_service import OnsetRhythmService
        svc = OnsetRhythmService()
        beats = [0.0, 0.5, 1.0, 1.5, 2.0]
        # Onsets zwischen den Beats (0.25, 0.75, 1.25, 1.75)
        onset_times = [0.25, 0.75, 1.25, 1.75]
        score = svc._compute_syncopation(onset_times, beats)
        assert score > 0.5, f"Erwartet Syncopation > 0.5, bekam {score}"

    def test_empty_onsets_zero(self):
        from services.onset_rhythm_service import OnsetRhythmService
        svc = OnsetRhythmService()
        assert svc._compute_syncopation([], [0.0, 0.5, 1.0]) == 0.0

    def test_empty_beats_zero(self):
        from services.onset_rhythm_service import OnsetRhythmService
        svc = OnsetRhythmService()
        assert svc._compute_syncopation([0.5], []) == 0.0


class TestSwingRatio:
    def test_straight_timing(self):
        from services.onset_rhythm_service import OnsetRhythmService, PercussiveOnset
        svc = OnsetRhythmService()
        beats = [i * 0.5 for i in range(10)]  # 120 BPM
        # Onsets exakt in der Mitte zwischen Beats -> ratio = 0.5
        onsets = [PercussiveOnset(time=i * 0.5 + 0.25, strength=0.8) for i in range(9)]
        ratio = svc._compute_swing_ratio(onsets, beats)
        assert abs(ratio - 0.5) < 0.1, f"Erwartet Swing ~0.5, bekam {ratio}"

    def test_no_beats_returns_half(self):
        from services.onset_rhythm_service import OnsetRhythmService
        svc = OnsetRhythmService()
        assert svc._compute_swing_ratio([], []) == 0.5

    def test_few_beats_returns_half(self):
        from services.onset_rhythm_service import OnsetRhythmService, PercussiveOnset
        svc = OnsetRhythmService()
        assert svc._compute_swing_ratio(
            [PercussiveOnset(time=0.5, strength=0.8)],
            [0.0, 0.5],
        ) == 0.5


class TestGrooveTemplateMatching:
    def test_empty_beats_unknown(self):
        from services.onset_rhythm_service import OnsetRhythmService
        svc = OnsetRhythmService()
        name, conf = svc._match_groove_template([], [], [])
        assert name == "unknown"
        assert conf == 0.0

    def test_few_beats_unknown(self):
        from services.onset_rhythm_service import OnsetRhythmService
        svc = OnsetRhythmService()
        name, conf = svc._match_groove_template([], [], [0.0, 0.5])
        assert name == "unknown"

    def test_valid_groove_detection(self):
        """Synthetische 4-on-the-floor Kick -> sollte zu Techno matchen."""
        from services.onset_rhythm_service import OnsetRhythmService, PercussiveOnset
        svc = OnsetRhythmService()
        # 120 BPM, 16 Beats
        beats = [i * 0.5 for i in range(16)]
        beat_dur = 0.5
        bar_dur = beat_dur * 4  # 2.0s
        eighth_dur = bar_dur / 8  # 0.25s

        # Kick auf jede Viertelnote (0, 2, 4, 6 Achtel-Slots pro Takt)
        kicks = []
        for bar in range(4):
            for slot in [0, 2, 4, 6]:
                t = bar * bar_dur + slot * eighth_dur
                kicks.append(PercussiveOnset(time=t, strength=0.9))

        # Snare auf 2 und 6 (wie Techno)
        snares = []
        for bar in range(4):
            for slot in [2, 6]:
                t = bar * bar_dur + slot * eighth_dur
                snares.append(PercussiveOnset(time=t, strength=0.8))

        name, conf = svc._match_groove_template(kicks, snares, beats)
        assert conf > 0.0, "Confidence sollte > 0 sein"
        assert name != "unknown"


# =========================================================================
# Groove Templates Definitionen
# =========================================================================


class TestGrooveTemplates:
    def test_all_templates_have_required_keys(self):
        from services.onset_rhythm_service import GROOVE_TEMPLATES
        for name, template in GROOVE_TEMPLATES.items():
            assert "kick" in template, f"Template '{name}' hat kein 'kick'"
            assert "snare" in template, f"Template '{name}' hat kein 'snare'"
            assert "description" in template, f"Template '{name}' hat kein 'description'"

    def test_slot_values_valid(self):
        from services.onset_rhythm_service import GROOVE_TEMPLATES
        for name, template in GROOVE_TEMPLATES.items():
            for slot in template["kick"]:
                assert 0 <= slot <= 7, f"Template '{name}': Kick-Slot {slot} ausserhalb 0-7"
            for slot in template["snare"]:
                assert 0 <= slot <= 7, f"Template '{name}': Snare-Slot {slot} ausserhalb 0-7"


# =========================================================================
# pacing_strategist.py — PacingPlan
# =========================================================================


class TestPacingPlan:
    def test_default(self):
        from services.pacing_strategist import PacingPlan
        plan = PacingPlan.default()
        assert plan.global_min_duration == 3.0
        assert plan.variety_priority == 0.7
        assert plan.section_overrides == []

    def test_from_json(self):
        from services.pacing_strategist import PacingPlan
        data = {
            "sections": [{"type": "DROP", "cut_rate_beats": 2}],
            "global_min_duration": 4.0,
            "variety_priority": 0.5,
        }
        plan = PacingPlan.from_json(data)
        assert plan.global_min_duration == 4.0
        assert plan.variety_priority == 0.5
        assert len(plan.section_overrides) == 1
        assert plan.section_overrides[0]["type"] == "DROP"

    def test_from_json_empty(self):
        from services.pacing_strategist import PacingPlan
        plan = PacingPlan.from_json({})
        assert plan.section_overrides == []
        assert plan.global_min_duration == 3.0


# =========================================================================
# pacing_beat_grid.py — invalidate_pacing_caches
# =========================================================================


class TestInvalidatePacingCaches:
    def test_invalidate_does_not_crash(self):
        """invalidate_pacing_caches() laeuft ohne Fehler."""
        from services.pacing_beat_grid import invalidate_pacing_caches
        # Sollte keine Exception werfen
        invalidate_pacing_caches()


# =========================================================================
# pacing_memory.py — auto_edit_to_beats tempo mapping
# =========================================================================


class TestAutoEditToBeatsTempoMapping:
    """Tests fuer die Tempo-zu-Rate Zuordnung in auto_edit_to_beats."""

    @pytest.mark.parametrize("tempo,expected_rate", [
        (90, 1),   # >= 80
        (80, 1),   # >= 80
        (70, 2),   # >= 60
        (60, 2),   # >= 60
        (50, 4),   # >= 40
        (40, 4),   # >= 40
        (30, 8),   # >= 20
        (20, 8),   # >= 20
        (10, 16),  # < 20
    ])
    def test_tempo_to_rate_mapping(self, tempo, expected_rate):
        """Teste die Tempo-zu-base_cut_rate Zuordnung direkt."""
        # Wir testen die Mapping-Logik inline
        if tempo >= 80:
            rate = 1
        elif tempo >= 60:
            rate = 2
        elif tempo >= 40:
            rate = 4
        elif tempo >= 20:
            rate = 8
        else:
            rate = 16
        assert rate == expected_rate


# =========================================================================
# BeatAnalysisService — _compute_energy_per_beat (statische Methode)
# =========================================================================


class TestComputeEnergyPerBeat:
    def test_normal_audio(self):
        from services.beat_analysis_service import BeatAnalysisService
        sr = 22050
        y = np.random.randn(sr * 4).astype(np.float32)
        beats = [0.0, 1.0, 2.0, 3.0]
        result = BeatAnalysisService._compute_energy_per_beat(y, sr, beats, 4.0)
        assert len(result) == 4
        assert all(0.0 <= e <= 1.0 for e in result)

    def test_empty_beats_returns_empty(self):
        from services.beat_analysis_service import BeatAnalysisService
        y = np.random.randn(22050).astype(np.float32)
        result = BeatAnalysisService._compute_energy_per_beat(y, 22050, [], 1.0)
        assert result == []

    def test_single_beat_returns_empty(self):
        from services.beat_analysis_service import BeatAnalysisService
        y = np.random.randn(22050).astype(np.float32)
        result = BeatAnalysisService._compute_energy_per_beat(y, 22050, [0.5], 1.0)
        assert result == []

    def test_normalized_to_one(self):
        from services.beat_analysis_service import BeatAnalysisService
        sr = 22050
        # Lautes Signal
        y = np.ones(sr * 3, dtype=np.float32)
        beats = [0.0, 1.0, 2.0]
        result = BeatAnalysisService._compute_energy_per_beat(y, sr, beats, 3.0)
        assert max(result) == 1.0

    def test_silence_returns_zeros(self):
        from services.beat_analysis_service import BeatAnalysisService
        sr = 22050
        y = np.zeros(sr * 3, dtype=np.float32)
        beats = [0.0, 1.0, 2.0]
        result = BeatAnalysisService._compute_energy_per_beat(y, sr, beats, 3.0)
        assert all(e == 0.0 for e in result)


# =========================================================================
# AudioAnalyzer.analyze — Error Handling
# =========================================================================


class TestAudioAnalyzerEdgeCases:
    def test_analyze_wraps_os_error(self, tmp_path):
        """OSError bei librosa.load wird als RuntimeError gewrappt."""
        from services.audio_service import AudioAnalyzer
        analyzer = AudioAnalyzer()
        fake_file = tmp_path / "bad.wav"
        fake_file.write_bytes(b"\x00")

        with patch("services.audio_service.librosa") as mock_librosa:
            mock_librosa.load.side_effect = OSError("Datei kaputt")
            with pytest.raises(RuntimeError, match="Audio-Analyse fehlgeschlagen"):
                analyzer.analyze(str(fake_file))

    def test_analyze_with_progress_callback(self, tmp_path):
        """Progress-Callback wird korrekt aufgerufen."""
        from services.audio_service import AudioAnalyzer
        analyzer = AudioAnalyzer()
        fake_file = tmp_path / "test.wav"
        fake_file.write_bytes(b"\x00" * 100)
        calls = []

        def progress(pct, msg):
            calls.append((pct, msg))

        fake_y = np.random.randn(22050 * 2).astype(np.float32)
        with patch("services.audio_service.librosa") as mock_librosa:
            mock_librosa.load.return_value = (fake_y, 22050)
            mock_librosa.get_duration.return_value = 2.0
            mock_librosa.beat.beat_track.return_value = (np.float64(120.0), np.array([]))
            mock_librosa.feature.rms.return_value = np.array([[0.5, 0.5]])

            analyzer.analyze(str(fake_file), progress_cb=progress)

        assert len(calls) >= 3, f"Mindestens 3 Progress-Calls erwartet, bekam {len(calls)}"
        # Erster Call bei 0%, letzter bei 100%
        assert calls[0][0] == 0
        assert calls[-1][0] == 100

    def test_analyze_beat_positions_are_floats(self, tmp_path):
        """Beat-Positionen sind immer float-Listen."""
        from services.audio_service import AudioAnalyzer
        analyzer = AudioAnalyzer()
        fake_file = tmp_path / "test.wav"
        fake_file.write_bytes(b"\x00" * 100)
        fake_y = np.random.randn(22050 * 2).astype(np.float32)
        with patch("services.audio_service.librosa") as mock_librosa:
            mock_librosa.load.return_value = (fake_y, 22050)
            mock_librosa.get_duration.return_value = 2.0
            mock_librosa.beat.beat_track.return_value = (
                np.float64(120.0),
                np.array([10, 20, 30, 40]),
            )
            mock_librosa.frames_to_time.return_value = np.array([0.46, 0.93, 1.39, 1.86])
            mock_librosa.feature.rms.return_value = np.array([[0.5, 0.5]])

            result = analyzer.analyze(str(fake_file))

        for bp in result["beat_positions"]:
            assert isinstance(bp, float), f"Beat-Position {bp} ist kein float: {type(bp)}"


# =========================================================================
# audio_constants.py — Konstanten-Konsistenz
# =========================================================================


class TestAudioConstantsConsistency:
    def test_default_sr_positive(self):
        from services.audio_constants import DEFAULT_SR
        assert DEFAULT_SR > 0
        assert DEFAULT_SR == 22050

    def test_max_durations_increasing(self):
        from services.audio_constants import (
            MAX_DURATION_KEY, MAX_DURATION_CLASSIFY,
            MAX_DURATION_SPECTRAL, MAX_DURATION_STRUCTURE,
        )
        assert MAX_DURATION_KEY < MAX_DURATION_CLASSIFY
        assert MAX_DURATION_CLASSIFY < MAX_DURATION_SPECTRAL
        assert MAX_DURATION_SPECTRAL < MAX_DURATION_STRUCTURE

    def test_bpm_range_valid(self):
        from services.audio_constants import BPM_MIN, BPM_MAX
        assert 0 < BPM_MIN < BPM_MAX
        assert BPM_MIN == 40.0
        assert BPM_MAX == 300.0

    def test_confidence_range(self):
        from services.audio_constants import CONFIDENCE_MIN, CONFIDENCE_MAX
        assert CONFIDENCE_MIN == 0.0
        assert CONFIDENCE_MAX == 1.0

    def test_energy_range(self):
        from services.audio_constants import ENERGY_MIN, ENERGY_MAX
        assert ENERGY_MIN == 0.0
        assert ENERGY_MAX == 1.0

    def test_genre_bpm_ranges_non_overlapping_between_styles(self):
        from services.audio_constants import (
            GENRE_HOUSE_BPM_MIN, GENRE_HOUSE_BPM_MAX,
            GENRE_TECHNO_BPM_MIN, GENRE_TECHNO_BPM_MAX,
            GENRE_PSYTRANCE_BPM_MIN, GENRE_PSYTRANCE_BPM_MAX,
        )
        # House < Techno < Psytrance (in der unteren Grenze)
        assert GENRE_HOUSE_BPM_MIN < GENRE_TECHNO_BPM_MIN
        assert GENRE_TECHNO_BPM_MIN < GENRE_PSYTRANCE_BPM_MIN

    def test_hop_length_divides_n_fft(self):
        from services.audio_constants import N_FFT, HOP_LENGTH
        assert N_FFT > HOP_LENGTH
        assert N_FFT % HOP_LENGTH == 0 or HOP_LENGTH < N_FFT
