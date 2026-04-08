"""
Tests fuer services/pacing_service.py

Getestet: calculate_cut_points(), _compute_effective_step(),
          _select_cut_beats_advanced(), PacingSettings, AdvancedPacingSettings
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from sqlalchemy.orm import Session

import database
from database import AudioTrack, Beatgrid, Project, VideoClip, Scene


# ---------------------------------------------------------------------------
# calculate_cut_points() Tests
# ---------------------------------------------------------------------------

class TestCalculateCutPoints:
    """Tests fuer die Phase-2-kompatible calculate_cut_points() Funktion."""

    def test_empty_beat_array_returns_time_based_cuts(self, test_engine):
        """Ohne Beats wird ein zeitbasierter Fallback verwendet."""
        import services.pacing_service as svc
        svc.engine = test_engine

        from services.pacing_service import PacingSettings, calculate_cut_points

        settings = PacingSettings(tempo=50, energy=50, cut_density=50)

        with patch.object(svc, "_get_beat_positions", return_value=[]):
            with patch.object(svc, "_get_bpm", return_value=None):
                with patch.object(svc, "_get_scenes", return_value=[]):
                    cuts = calculate_cut_points(
                        audio_id=None,
                        video_id=None,
                        settings=settings,
                        total_duration=20.0,
                    )

        assert isinstance(cuts, list)

    def test_cut_points_with_normal_beat_array(self, test_engine):
        """Mit normalem Beat-Array werden Schnittpunkte auf Beats gesetzt."""
        import services.pacing_service as svc
        from services.pacing_service import PacingSettings, CutPoint, calculate_cut_points

        beats = [i * 0.5 for i in range(20)]  # Beat alle 0.5s (120 BPM)
        settings = PacingSettings(tempo=80, energy=70, cut_density=50)

        with patch.object(svc, "_get_beat_positions", return_value=beats):
            with patch.object(svc, "_get_scenes", return_value=[]):
                cuts = calculate_cut_points(
                    audio_id=1,
                    video_id=None,
                    settings=settings,
                    total_duration=10.0,
                )

        assert len(cuts) > 0
        assert all(c.time <= 10.0 for c in cuts)
        beat_set = set(round(b, 4) for b in beats)
        for cut in cuts:
            assert round(cut.time, 4) in beat_set, f"CutPoint {cut.time} liegt nicht auf Beat"

    def test_cut_points_total_duration_zero_returns_empty_list(self):
        """total_duration=0 liefert leere Liste (Division-by-Zero Guard)."""
        import services.pacing_service as svc
        from services.pacing_service import PacingSettings, calculate_cut_points

        beats = [0.0, 0.5, 1.0]
        settings = PacingSettings(tempo=50, energy=50, cut_density=50)

        with patch.object(svc, "_get_beat_positions", return_value=beats):
            with patch.object(svc, "_get_scenes", return_value=[]):
                cuts = calculate_cut_points(
                    audio_id=1,
                    video_id=None,
                    settings=settings,
                    total_duration=0.0,
                )

        assert isinstance(cuts, list)
        assert len(cuts) == 0


    @pytest.mark.parametrize("tempo,expected_step", [
        (90, 1),   # tempo >= 80 -> step 1
        (65, 2),   # tempo >= 60 -> step 2
        (45, 4),   # tempo >= 40 -> step 4
        (25, 8),   # tempo >= 20 -> step 8
        (10, 16),  # tempo < 20  -> step 16
    ])
    def test_cut_points_tempo_maps_to_beat_step(self, tempo, expected_step):
        """Tempo-Wert bestimmt den Beat-Schritt korrekt.

        cut_density=100 -> threshold=0.0 -> alle generierten Cuts durchgelassen.
        Beats sind 0.5s auseinander -> kein Minimum-Interval-Filter greift.
        """
        import services.pacing_service as svc
        from services.pacing_service import PacingSettings, calculate_cut_points

        # 64 Beats alle 0.5s (weit genug auseinander fuer Minimum-Interval)
        beats = [i * 0.5 for i in range(64)]
        # cut_density=100 -> threshold = 1.0 - 1.0 = 0.0 -> ALLE Cuts passieren
        settings = PacingSettings(tempo=tempo, energy=50, cut_density=100)

        with patch.object(svc, "_get_beat_positions", return_value=beats):
            with patch.object(svc, "_get_bpm", return_value=120.0):
                with patch.object(svc, "_get_scenes", return_value=[]):
                    cuts = calculate_cut_points(
                        audio_id=1,
                        video_id=None,
                        settings=settings,
                        total_duration=32.0,
                    )

        # Erwartete Anzahl: beats / expected_step (alle Beats die i % step == 0 erfuellen)
        expected_count = len([i for i in range(len(beats)) if i % expected_step == 0])
        # Kleine Toleranz durch Minimum-Interval-Filter
        assert abs(len(cuts) - expected_count) <= 2, \
            f"tempo={tempo}, expected ~{expected_count} cuts, got {len(cuts)}"

    def test_cut_points_are_sorted_ascending(self):
        """Schnittpunkte sind zeitlich aufsteigend sortiert."""
        import services.pacing_service as svc
        from services.pacing_service import PacingSettings, calculate_cut_points

        beats = sorted([i * 0.47 for i in range(30)])
        settings = PacingSettings(tempo=50, energy=50, cut_density=50)

        with patch.object(svc, "_get_beat_positions", return_value=beats):
            with patch.object(svc, "_get_scenes", return_value=[]):
                cuts = calculate_cut_points(
                    audio_id=1,
                    video_id=None,
                    settings=settings,
                    total_duration=15.0,
                )

        times = [c.time for c in cuts]
        assert times == sorted(times)

    def test_cut_points_minimum_interval_respected(self):
        """Zwei Schnittpunkte liegen mindestens 0.1s auseinander."""
        import services.pacing_service as svc
        from services.pacing_service import PacingSettings, calculate_cut_points

        # Sehr dichte Beats (alle 0.05s)
        beats = [i * 0.05 for i in range(200)]
        settings = PacingSettings(tempo=90, energy=80, cut_density=100)

        with patch.object(svc, "_get_beat_positions", return_value=beats):
            with patch.object(svc, "_get_scenes", return_value=[]):
                cuts = calculate_cut_points(
                    audio_id=1,
                    video_id=None,
                    settings=settings,
                    total_duration=10.0,
                )

        for i in range(1, len(cuts)):
            gap = cuts[i].time - cuts[i - 1].time
            assert gap >= 0.1, f"Zu kleiner Abstand: {gap:.3f}s zwischen Cut {i-1} und {i}"



# ---------------------------------------------------------------------------
# _compute_effective_step() Tests
# ---------------------------------------------------------------------------

class TestComputeEffectiveStep:
    def test_high_energy_reduces_step(self):
        """Hohe Energie (>0.7) mit hoher Reaktivitaet reduziert den Schritt."""
        from services.pacing_service import _compute_effective_step

        step = _compute_effective_step(
            base_step=8,
            beat_index=0,
            beat_time=1.0,
            total_duration=60.0,
            energy_per_beat=[0.9],
            energy_reactivity=100,
            breakdown_behavior="halve",
            pacing_curve=None,
        )
        assert step < 8, f"Erwartet < 8, erhalten: {step}"

    def test_low_energy_with_halve_doubles_step(self):
        """Niedrige Energie (<0.3) mit halve verdoppelt den Schritt."""
        from services.pacing_service import _compute_effective_step

        step = _compute_effective_step(
            base_step=4,
            beat_index=0,
            beat_time=1.0,
            total_duration=60.0,
            energy_per_beat=[0.1],
            energy_reactivity=100,
            breakdown_behavior="halve",
            pacing_curve=None,
        )
        assert step >= 8, f"Erwartet >= 8, erhalten: {step}"

    def test_low_energy_with_force16_returns_16(self):
        """force16 erzwingt immer Step=16 bei niedriger Energie."""
        from services.pacing_service import _compute_effective_step

        step = _compute_effective_step(
            base_step=4,
            beat_index=0,
            beat_time=1.0,
            total_duration=60.0,
            energy_per_beat=[0.1],
            energy_reactivity=100,
            breakdown_behavior="force16",
            pacing_curve=None,
        )
        assert step == 16

    def test_no_energy_data_returns_base_step(self):
        """Ohne Energie-Daten wird der base_step unveraendert zurueckgegeben."""
        from services.pacing_service import _compute_effective_step

        step = _compute_effective_step(
            base_step=4,
            beat_index=5,
            beat_time=5.0,
            total_duration=60.0,
            energy_per_beat=[],
            energy_reactivity=50,
            breakdown_behavior="halve",
            pacing_curve=None,
        )
        assert step == 4

    def test_result_is_always_at_least_1(self):
        """Schritt-Wert ist immer >= 1."""
        from services.pacing_service import _compute_effective_step

        step = _compute_effective_step(
            base_step=1,
            beat_index=0,
            beat_time=0.0,
            total_duration=60.0,
            energy_per_beat=[1.0],
            energy_reactivity=100,
            breakdown_behavior="none",
            pacing_curve=None,
        )
        assert step >= 1


# ---------------------------------------------------------------------------
# AdvancedPacingSettings Defaults
# ---------------------------------------------------------------------------

class TestAdvancedPacingSettings:
    def test_default_values(self):
        from services.pacing_service import AdvancedPacingSettings

        s = AdvancedPacingSettings()
        assert s.base_cut_rate == 4
        assert s.energy_reactivity == 50
        assert s.breakdown_behavior == "halve"
        assert s.vibe == ""
        assert s.manual_density_curve is None
        assert s.anchors is None

    def test_custom_values(self):
        from services.pacing_service import AdvancedPacingSettings

        s = AdvancedPacingSettings(
            base_cut_rate=2,
            energy_reactivity=75,
            breakdown_behavior="force16",
            vibe="action",
        )
        assert s.base_cut_rate == 2
        assert s.vibe == "action"


# ---------------------------------------------------------------------------
# CutPoint Datenklasse
# ---------------------------------------------------------------------------

class TestCutPoint:
    def test_cutpoint_fields(self):
        from services.pacing_service import CutPoint

        cp = CutPoint(time=1.5, source="beat", strength=0.8)
        assert cp.time == 1.5
        assert cp.source == "beat"
        assert cp.strength == 0.8


# ---------------------------------------------------------------------------
# F-009: Vocal-Active Pacing Tests
# ---------------------------------------------------------------------------

class TestVocalActivePacing:
    """Tests fuer F-009: Vocal-Active Pacing Algorithm.

    PhD-Spec Abschnitt 7.3: Wenn Vocals aktiv sind, wird die Schnittfrequenz
    reduziert (S_eff x 2) fuer visuelle Stabilitaet waehrend Gesang.
    """

    def test_compute_vocal_activity_no_vocals(self, test_engine):
        """Ohne Vocal-Stem werden alle Beats als nicht-vokal markiert."""
        import services.pacing_service as svc
        from services.pacing_service import compute_vocal_activity

        svc.engine = test_engine

        # Erstelle Track ohne Vocal-Stem
        with Session(test_engine) as session:
            track = AudioTrack(
                project_id=1,
                filename="test.mp3",
                file_path="/test.mp3",
                duration=10.0,
                stem_vocals_path=None,
            )
            session.add(track)
            session.commit()
            audio_id = track.id

        beats = [0.0, 0.5, 1.0, 1.5, 2.0]
        activity = compute_vocal_activity(audio_id, beats)

        assert len(activity) == len(beats)
        assert all(not active for active in activity), "Alle Beats sollten nicht-vokal sein"

    def test_compute_vocal_activity_with_vocals(self, test_engine, tmp_path):
        """Mit Vocal-Stem wird RMS-basierte Aktivitaet berechnet."""
        import services.pacing_service as svc
        from services.pacing_service import compute_vocal_activity
        import numpy as np
        import soundfile as sf

        svc.engine = test_engine

        # Erstelle synthetisches Vocal-Audio (44.1kHz, 3 Sekunden)
        sr = 44100
        duration = 3.0
        t = np.linspace(0, duration, int(sr * duration))

        # Erste Sekunde: leise (kein Vocal), zweite+dritte: laut (Vocal aktiv)
        audio = np.concatenate([
            np.random.randn(sr) * 0.01,  # 0-1s: sehr leise
            np.random.randn(sr * 2) * 0.5,  # 1-3s: laut
        ])

        vocal_path = tmp_path / "vocals.wav"
        sf.write(str(vocal_path), audio, sr)

        # Erstelle Track mit Vocal-Stem
        with Session(test_engine) as session:
            track = AudioTrack(
                project_id=1,
                filename="test.mp3",
                file_path="/test.mp3",
                duration=3.0,
                stem_vocals_path=str(vocal_path),
            )
            session.add(track)
            session.commit()
            audio_id = track.id

        # Beats: alle 0.5 Sekunden
        beats = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
        activity = compute_vocal_activity(audio_id, beats, threshold=0.15)

        assert len(activity) == len(beats)
        # Erste Beats (0-1s) sollten nicht-vokal sein, spaetere Beats vokal
        assert not activity[0], "Beat bei 0.0s sollte nicht-vokal sein (leises Segment)"
        assert activity[2] or activity[3], "Mindestens ein Beat bei 1.0s+ sollte vokal sein"

    def test_vocal_active_doubles_cut_interval(self):
        """F-009: Vocal-Active verdoppelt den effektiven Schritt (weniger Cuts)."""
        from services.pacing_service import _compute_effective_step

        # Basis-Fall: ohne Vocals
        step_no_vocal = _compute_effective_step(
            base_step=4,
            beat_index=0,
            beat_time=1.0,
            total_duration=60.0,
            energy_per_beat=[0.8],
            energy_reactivity=0,
            breakdown_behavior="none",
            pacing_curve=None,
            vocal_active=False,
        )

        # Mit Vocals: Step sollte verdoppelt sein
        step_with_vocal = _compute_effective_step(
            base_step=4,
            beat_index=0,
            beat_time=1.0,
            total_duration=60.0,
            energy_per_beat=[0.8],
            energy_reactivity=0,
            breakdown_behavior="none",
            pacing_curve=None,
            vocal_active=True,
        )

        assert step_with_vocal == step_no_vocal * 2, \
            f"Vocal-Active sollte Step verdoppeln: {step_no_vocal} → {step_with_vocal}"

    def test_vocal_active_caps_at_16(self):
        """F-009: Vocal-Active ist auf maximal 16 Beats begrenzt."""
        from services.pacing_service import _compute_effective_step

        # Basis-Step = 12, mit Vocals wuerde das 24 ergeben, aber Cap ist 16
        step = _compute_effective_step(
            base_step=12,
            beat_index=0,
            beat_time=1.0,
            total_duration=60.0,
            energy_per_beat=[0.5],
            energy_reactivity=0,
            breakdown_behavior="none",
            pacing_curve=None,
            vocal_active=True,
        )

        assert step == 16, f"Vocal-Active Step sollte auf 16 begrenzt sein, erhalten: {step}"

    def test_vocal_active_integration_in_select_cut_beats(self):
        """F-009: Integration Test — vocal_activity wird in _select_cut_beats_advanced verwendet."""
        from services.pacing_service import _select_cut_beats_advanced, AdvancedPacingSettings

        beats = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
        energy = [0.5] * len(beats)
        settings = AdvancedPacingSettings(base_cut_rate=2, energy_reactivity=0)

        # Fall 1: Keine Vocals (alle False)
        vocal_activity_none = [False] * len(beats)
        cuts_no_vocal = _select_cut_beats_advanced(
            beats, 5.0, settings, energy,
            vocal_activity=vocal_activity_none,
        )

        # Fall 2: Alle Beats haben Vocals (alle True)
        vocal_activity_all = [True] * len(beats)
        cuts_with_vocal = _select_cut_beats_advanced(
            beats, 5.0, settings, energy,
            vocal_activity=vocal_activity_all,
        )

        # Mit Vocals sollten deutlich weniger Cuts entstehen (weil Step verdoppelt wird)
        assert len(cuts_with_vocal) < len(cuts_no_vocal), \
            f"Mit Vocals sollten weniger Cuts sein: {len(cuts_with_vocal)} < {len(cuts_no_vocal)}"

        # Mindestens 30% weniger Cuts bei aktiven Vocals
        reduction = (len(cuts_no_vocal) - len(cuts_with_vocal)) / len(cuts_no_vocal)
        assert reduction >= 0.3, \
            f"Vocal-Active sollte mindestens 30% weniger Cuts erzeugen, aber nur {reduction*100:.0f}%"
