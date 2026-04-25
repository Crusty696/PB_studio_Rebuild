"""B-064 fix: Librosa-Fallback liefert KEINE geschätzten Downbeats mehr.

Statt der Heuristik `beats[::4]` (die bei Pickup-/Offbeat-Starts systematisch
falsche Downbeats produziert) gibt der Fallback eine LEERE Downbeat-Liste
zurück. Downstream (`pacing_edit_helpers._select_cut_beats_advanced`) ist
bereits darauf vorbereitet (`set(downbeats) if downbeats else set()`).
"""
import logging

import numpy as np
import pytest

from services.beat_analysis_service import BeatAnalysisService


class _FakeService:
    """Minimaler Wrapper um nur _analyze_librosa_fallback zu testen."""

    def __init__(self):
        self._beat_this_unavailable = True
        self._beat_this_unavailable_reason = "test-mock"


def test_librosa_fallback_returns_empty_downbeats_for_offbeat_start(caplog):
    """DJ-Mix mit Pickup → Fallback darf keine Downbeats raten."""
    sr = 22050
    duration_sec = 8.0
    rng = np.random.default_rng(42)
    y = rng.standard_normal(int(sr * duration_sec)).astype(np.float32) * 0.1
    pulse_period = sr // 2
    for i in range(0, len(y), pulse_period):
        end = min(i + 500, len(y))
        y[i:end] += 0.5

    svc = BeatAnalysisService.__new__(BeatAnalysisService)
    svc._beat_this_unavailable = True
    svc._beat_this_unavailable_reason = "test-mock"

    with caplog.at_level(logging.WARNING):
        beats, downbeats = BeatAnalysisService._analyze_librosa_fallback(svc, y, sr)

    assert isinstance(beats, np.ndarray)
    assert isinstance(downbeats, np.ndarray)
    assert len(downbeats) == 0, (
        f"Fallback darf keine Downbeats raten — {len(downbeats)} Downbeats erhalten"
    )
    assert any(
        "downbeat" in rec.message.lower() and "fallback" in rec.message.lower()
        for rec in caplog.records
    ), "Es muss ein Warning geben dass keine Downbeats verfügbar sind"


def test_librosa_fallback_beats_still_returned():
    """Fallback liefert weiterhin BEATS (nur Downbeats fehlen)."""
    sr = 22050
    duration_sec = 6.0
    rng = np.random.default_rng(7)
    y = rng.standard_normal(int(sr * duration_sec)).astype(np.float32) * 0.05
    pulse_period = sr // 2
    for i in range(0, len(y), pulse_period):
        end = min(i + 300, len(y))
        y[i:end] += 0.4

    svc = BeatAnalysisService.__new__(BeatAnalysisService)
    svc._beat_this_unavailable = True
    svc._beat_this_unavailable_reason = "test-mock"

    beats, downbeats = BeatAnalysisService._analyze_librosa_fallback(svc, y, sr)
    assert len(beats) > 0, "Beats müssen weiterhin geliefert werden"
    assert len(downbeats) == 0


def test_pacing_helper_handles_empty_downbeats():
    """Sanity: pacing_edit_helpers verträgt leere Downbeat-Liste."""
    from services.pacing_edit_helpers import _select_cut_beats_advanced
    from services.pacing_beat_grid import AdvancedPacingSettings

    beats = [i * 0.5 for i in range(20)]  # 20 Beats, jede 0.5s
    settings = AdvancedPacingSettings()
    energy = [0.5] * len(beats)

    selected = _select_cut_beats_advanced(
        beats=beats,
        total_duration=10.0,
        settings=settings,
        energy_per_beat=energy,
        avg_motion=0.5,
        downbeats=[],  # B-064: kein Downbeat-Schätzwerk mehr
    )
    assert isinstance(selected, list)
