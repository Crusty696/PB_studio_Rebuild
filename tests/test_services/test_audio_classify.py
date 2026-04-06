"""Tests für AudioClassifyService — Mood/Genre Erkennung."""

import pytest
from unittest.mock import patch, MagicMock

from services.audio_classify_service import (
    AudioClassifyService, ClassifyResult, GENRE_BPM_RANGES, _fallback_result,
)


class TestFallbackResult:
    """Tests für _fallback_result()."""

    def test_returns_classify_result(self):
        r = _fallback_result("test reason")
        assert isinstance(r, ClassifyResult)
        assert r.confidence == 0.0
        assert r.mood == "unknown"
        assert "test reason" in r.description


class TestClassifyGenre:
    """Tests für die BPM-basierte Genre-Klassifikation."""

    def test_140_bpm_psytrance(self):
        """140 BPM + hoher Centroid → Psytrance."""
        genre, conf = AudioClassifyService._classify_genre(140.0, 4000.0, 0.1)
        assert genre in ("Psytrance", "Trance", "Techno")
        assert conf > 0

    def test_170_bpm_dnb(self):
        """170 BPM → Drum & Bass."""
        genre, conf = AudioClassifyService._classify_genre(170.0, 3000.0, 0.08)
        assert genre == "Drum & Bass"

    def test_90_bpm_hiphop(self):
        """90 BPM + niedriger Centroid → Hip-Hop."""
        genre, conf = AudioClassifyService._classify_genre(90.0, 1500.0, 0.03)
        assert genre in ("Hip-Hop", "Ambient")

    def test_200_bpm_no_match(self):
        """200 BPM → kein BPM-Range Match, Fallback."""
        genre, conf = AudioClassifyService._classify_genre(200.0, 3000.0, 0.08)
        assert conf < 0.7  # Reduced confidence for unmatched

    def test_125_bpm_disambiguation(self):
        """125 BPM matched Techno + House → disambiguiert via Centroid."""
        # Hoher Centroid → Techno
        genre_high, _ = AudioClassifyService._classify_genre(128.0, 4000.0, 0.1)
        # Niedriger Centroid → House
        genre_low, _ = AudioClassifyService._classify_genre(128.0, 1500.0, 0.03)
        # Beide sollten unterschiedliche Ergebnisse liefern
        assert genre_high != genre_low or genre_high in ("Techno", "House")


class TestClassifyMood:
    """Tests für Mood-Klassifikation."""

    def test_energetic(self):
        assert AudioClassifyService._classify_mood(4000.0, 0.15) == "energetic"

    def test_melancholic(self):
        assert AudioClassifyService._classify_mood(1500.0, 0.02) == "melancholic"

    def test_chill(self):
        assert AudioClassifyService._classify_mood(1200.0, 0.02) == "chill"

    def test_dark_default(self):
        """Werte die in keine Kategorie passen → 'dark'."""
        assert AudioClassifyService._classify_mood(2800.0, 0.04) == "dark"


class TestClassifyEnergy:
    """Tests für Energy-Level Klassifikation."""

    def test_high(self):
        assert AudioClassifyService._classify_energy(0.12) == "high"

    def test_medium(self):
        assert AudioClassifyService._classify_energy(0.05) == "medium"

    def test_low(self):
        assert AudioClassifyService._classify_energy(0.01) == "low"


class TestClassifyService:
    """Integration-Tests für classify()."""

    def test_fallback_without_librosa(self):
        """Ohne librosa → Fallback-Result."""
        with patch("services.audio_classify_service._HAS_LIBROSA", False), \
             patch("services.audio_classify_service._HAS_NUMPY", False):
            svc = AudioClassifyService()
            result = svc.classify("/nonexistent.mp3")
            assert result.confidence == 0.0
            assert result.mood == "unknown"

    def test_classify_with_mocked_librosa(self):
        """Mock-librosa → klassifiziert korrekt."""
        import numpy as np
        mock_librosa = MagicMock()
        mock_librosa.load.return_value = (np.random.randn(22050 * 30), 22050)
        mock_librosa.feature.spectral_centroid.return_value = np.array([[3500.0]])
        mock_librosa.feature.spectral_rolloff.return_value = np.array([[8000.0]])
        mock_librosa.feature.rms.return_value = np.array([[0.1]])
        mock_librosa.feature.zero_crossing_rate.return_value = np.array([[0.05]])
        mock_librosa.feature.mfcc.return_value = np.random.randn(13, 20)
        mock_librosa.beat.beat_track.return_value = (np.array([140.0]), np.array([1, 2, 3]))

        with patch("services.audio_classify_service.librosa", mock_librosa), \
             patch("services.audio_classify_service.np", np):
            svc = AudioClassifyService()
            result = svc.classify("/test/psytrance.mp3")
            assert isinstance(result, ClassifyResult)
            assert result.confidence > 0
            assert result.genre != "Unknown"
            assert result.mood in ("energetic", "euphoric", "dark", "melancholic", "chill")


class TestDJMixDetection:
    """Tests für detect_dj_mix()."""

    def test_short_file_not_mix(self):
        """Datei < 10 Min → kein DJ-Mix."""
        import numpy as np
        mock_librosa = MagicMock()
        mock_librosa.get_duration.return_value = 300.0  # 5 Min

        with patch("services.audio_classify_service.librosa", mock_librosa), \
             patch("services.audio_classify_service.np", np):
            svc = AudioClassifyService()
            assert svc.detect_dj_mix("/test/short.mp3") is False

    def test_very_long_file_is_mix(self):
        """Datei > 30 Min → DJ-Mix."""
        import numpy as np
        mock_librosa = MagicMock()
        mock_librosa.get_duration.return_value = 3600.0  # 60 Min

        with patch("services.audio_classify_service.librosa", mock_librosa), \
             patch("services.audio_classify_service.np", np):
            svc = AudioClassifyService()
            assert svc.detect_dj_mix("/test/long_mix.mp3") is True
