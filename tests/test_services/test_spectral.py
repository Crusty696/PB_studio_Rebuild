"""Tests für SpectralAnalysisService — 8-Band Frequenz-Analyse."""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from services.spectral_analysis_service import (
    SpectralAnalysisService, SpectralResult, SpectralBand, SpectralEvent,
    FREQUENCY_BANDS,
)


class TestFrequencyBands:
    """Tests für die Band-Definitionen."""

    def test_eight_bands(self):
        assert len(FREQUENCY_BANDS) == 8

    def test_bands_contiguous(self):
        """Bänder sind lückenlos aneinander (20→60→250→...→20000)."""
        for i in range(len(FREQUENCY_BANDS) - 1):
            _, _, high = FREQUENCY_BANDS[i]
            _, low_next, _ = FREQUENCY_BANDS[i + 1]
            assert high == low_next, f"Lücke: Band {i} endet bei {high}, Band {i+1} beginnt bei {low_next}"

    def test_bands_cover_hearing_range(self):
        """Bänder decken 20Hz-20kHz ab."""
        assert FREQUENCY_BANDS[0][1] == 20      # Erste Band startet bei 20Hz
        assert FREQUENCY_BANDS[-1][2] == 20000   # Letzte Band endet bei 20kHz


class TestSpectralAnalysis:
    """Tests für SpectralAnalysisService.analyze()."""

    def test_fallback_without_librosa(self):
        """Ohne librosa → leeres Result mit 8 Bändern bei Energie 0."""
        import services.spectral_analysis_service as sas
        svc = SpectralAnalysisService()
        # Simuliere fehlende librosa via Modul-Level Flag
        with patch.object(sas, "_HAS_LIBROSA", False), \
             patch.object(sas, "_HAS_NUMPY", False):
            result = svc.analyze("/nonexistent.mp3")
            assert isinstance(result, SpectralResult)
            assert len(result.bands) == 8
            assert all(b.energy == 0.0 for b in result.bands)

    def test_analyze_with_real_librosa(self):
        """Echte librosa-Analyse mit synthetischem 500Hz Sinus."""
        try:
            import librosa as real_librosa
        except ImportError:
            pytest.skip("librosa nicht installiert")

        sr = 22050
        duration = 2.0
        t = np.linspace(0, duration, int(sr * duration), endpoint=False)
        sine_500hz = np.sin(2 * np.pi * 500 * t).astype(np.float32)

        # Patch nur librosa.load um Datei-Zugriff zu vermeiden
        with patch("librosa.load", return_value=(sine_500hz, sr)):
            svc = SpectralAnalysisService()
            result = svc.analyze("/test/sine500.wav")
            assert isinstance(result, SpectralResult)
            assert len(result.bands) == 8
            # 500Hz fällt in "Low Mid" (250-500Hz) oder "Mid" (500-2000Hz)
            mid_bands = [b for b in result.bands if b.name in ("Low Mid", "Mid")]
            assert any(b.energy > 0 for b in mid_bands), "500Hz Sinus sollte Mid-Bänder aktivieren"

    def test_normalize_bands_real(self):
        """Echte Analyse: Alle Band-Energien liegen im Bereich 0.0-1.0."""
        try:
            import librosa
        except ImportError:
            pytest.skip("librosa nicht installiert")

        y = np.random.randn(22050 * 2).astype(np.float32)
        with patch("librosa.load", return_value=(y, 22050)):
            svc = SpectralAnalysisService()
            result = svc.analyze("/test/noise.wav")
            for band in result.bands:
                assert 0.0 <= band.energy <= 1.0, f"Band '{band.name}' Energie={band.energy}"

    def test_empty_audio(self):
        """Leere Audio-Datei → leeres Result mit Energie 0."""
        try:
            import librosa
        except ImportError:
            pytest.skip("librosa nicht installiert")

        with patch("librosa.load", return_value=(np.array([]), 22050)):
            svc = SpectralAnalysisService()
            result = svc.analyze("/test/empty.wav")
            assert all(b.energy == 0.0 for b in result.bands)


class TestAnalyzeExtendedBufferReuse:
    """B-231: ``analyze_extended`` darf Audio + STFT nicht doppelt berechnen."""

    def test_analyze_extended_loads_audio_once(self):
        """``analyze_extended`` ruft ``librosa.load`` + ``librosa.stft`` genau
        einmal auf (via ``_analyze_with_buffers``), nicht ein zweites Mal."""
        try:
            import librosa  # noqa: F401
        except ImportError:
            pytest.skip("librosa nicht installiert")

        sr = 22050
        y = np.random.randn(sr * 2).astype(np.float32)

        with patch("librosa.load", return_value=(y, sr)) as mock_load, \
             patch("librosa.stft", wraps=librosa.stft) as mock_stft:
            svc = SpectralAnalysisService()
            report = svc.analyze_extended("/test/track.wav")

        assert mock_load.call_count == 1, (
            f"B-231: librosa.load {mock_load.call_count}x aufgerufen, erwartet 1x"
        )
        assert mock_stft.call_count == 1, (
            f"B-231: librosa.stft {mock_stft.call_count}x aufgerufen, erwartet 1x"
        )
        # Erweiterte Analyse hat trotzdem Ergebnisse produziert
        assert len(report.temporal_bands) > 0
        assert len(report.spectral.bands) == 8

    def test_analyze_extended_empty_audio_uses_buffer_path(self):
        """Leeres Audio aus dem Helper → Fallback-Report ohne zweiten Load."""
        try:
            import librosa  # noqa: F401
        except ImportError:
            pytest.skip("librosa nicht installiert")

        with patch("librosa.load", return_value=(np.array([], dtype=np.float32), 22050)) as mock_load:
            svc = SpectralAnalysisService()
            report = svc.analyze_extended("/test/empty.wav")

        assert mock_load.call_count == 1, "B-231: kein zweiter Load bei leerem Audio"
        assert report.temporal_bands == []
        assert report.best_genre_match == "unknown"


class TestGetBandsJson:
    """Tests für JSON-Serialisierung."""

    def test_json_format(self):
        """get_bands_json gibt gültiges JSON zurück."""
        import json
        svc = SpectralAnalysisService()
        result = SpectralResult(
            bands=[SpectralBand("Bass", 60, 250, 0.8), SpectralBand("Mid", 500, 2000, 0.5)],
            events=[],
            dominant_band="Bass",
            spectral_centroid_mean=1500.0,
        )
        j = svc.get_bands_json(result)
        data = json.loads(j)
        assert len(data) == 2
        assert data[0]["name"] == "Bass"
        assert data[0]["energy"] == 0.8


def _selective_import_error(name, *args, **kwargs):
    """Import-Error nur für librosa/numpy werfen."""
    if name in ("librosa", "numpy"):
        raise ImportError(f"Mocked: {name} not available")
    return __builtins__.__import__(name, *args, **kwargs) if callable(getattr(__builtins__, '__import__', None)) else None
