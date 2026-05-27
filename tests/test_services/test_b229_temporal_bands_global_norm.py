"""B-229: _compute_temporal_bands normalisiert track-global statt per-Window.

Ein leiser Abschnitt darf nach Normalisierung NICHT dieselbe Magnitude haben
wie der lauteste Abschnitt — sonst ist zeitlicher Vergleich ("temporal")
unmoeglich. Option 1 aus B-229 (track-globale Normalisierung).
"""
from __future__ import annotations

import numpy as np

from services.spectral_analysis_service import SpectralAnalysisService


def _bands(power_spec, sr=22050, hop=512, n_fft=2048):
    # __init__ umgehen — die Methode nutzt keine Instanz-Attribute.
    svc = object.__new__(SpectralAnalysisService)
    return svc._compute_temporal_bands(power_spec, sr, hop, n_fft)


def test_temporal_bands_are_globally_normalized():
    sr, hop, n_fft = 22050, 512, 2048
    frames_per_sec = max(1, int(sr / hop))
    bins = n_fft // 2 + 1

    # 2 Sekunden: Sekunde 0 laut (1.0), Sekunde 1 leise (0.1).
    power = np.ones((bins, frames_per_sec * 2), dtype=np.float64)
    power[:, frames_per_sec:] = 0.1

    result = _bands(power, sr, hop, n_fft)
    assert len(result) == 2

    loud_max = max(result[0].band_energies.values())
    quiet_max = max(result[1].band_energies.values())

    # Track-globaler Max liegt in Sekunde 0 -> dort 1.0.
    assert abs(loud_max - 1.0) < 1e-6
    # Leise Sekunde bleibt klein (NICHT auf 1.0 hochnormalisiert wie vorher).
    assert quiet_max < 0.5
    assert abs(quiet_max - 0.1) < 1e-3
    # Genau ein globales Maximum == 1.0 ueber alle Fenster.
    overall = max(v for tb in result for v in tb.band_energies.values())
    assert abs(overall - 1.0) < 1e-6


def test_temporal_bands_empty_on_short_input():
    # < 1 Sekunde -> keine Fenster.
    power = np.ones((1025, 10), dtype=np.float64)
    assert _bands(power) == []
