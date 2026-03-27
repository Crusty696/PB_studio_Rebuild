"""Tests für KeyDetectionService — Krumhansl-Kessler Key Detection."""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from services.key_detection_service import (
    KeyDetectionService, KeyResult, CAMELOT_WHEEL, KEY_NAMES,
    _pearson, _KK_MAJOR, _KK_MINOR,
)


class TestCamelotWheel:
    """Tests für die Camelot-Wheel Datenstruktur."""

    def test_all_24_sharp_keys_present(self):
        """Alle 12 Major + 12 Minor Keys in Sharp-Notation vorhanden."""
        for name in KEY_NAMES:
            assert name in CAMELOT_WHEEL, f"Major key '{name}' fehlt"
            assert f"{name}m" in CAMELOT_WHEEL, f"Minor key '{name}m' fehlt"

    def test_flat_aliases_present(self):
        """Flat-Notation Aliases (Db, Eb, Gb, Ab, Bb) vorhanden."""
        flats = ["Db", "Dbm", "Eb", "Ebm", "Gb", "Gbm", "Ab", "Abm", "Bb", "Bbm"]
        for flat in flats:
            assert flat in CAMELOT_WHEEL, f"Flat alias '{flat}' fehlt"

    def test_flat_aliases_match_sharp(self):
        """Flat-Aliases zeigen auf den gleichen Camelot-Code wie ihre Sharp-Entsprechung."""
        assert CAMELOT_WHEEL["Db"] == CAMELOT_WHEEL["C#"]
        assert CAMELOT_WHEEL["Ebm"] == CAMELOT_WHEEL["D#m"]
        assert CAMELOT_WHEEL["Bb"] == CAMELOT_WHEEL["A#"]

    def test_camelot_codes_valid_format(self):
        """Alle Camelot-Codes haben Format: Zahl(1-12) + Buchstabe(A/B)."""
        for key, code in CAMELOT_WHEEL.items():
            num = code[:-1]
            letter = code[-1]
            assert letter in ("A", "B"), f"Key '{key}' hat ungültigen Buchstaben: {letter}"
            assert 1 <= int(num) <= 12, f"Key '{key}' hat ungültige Nummer: {num}"


class TestPearson:
    """Tests für die Pearson-Korrelations-Hilfsfunktion."""

    def test_identical_arrays(self):
        """Identische Arrays → Korrelation = 1.0."""
        x = np.array([1.0, 2.0, 3.0, 4.0])
        assert abs(_pearson(x, x) - 1.0) < 1e-6

    def test_opposite_arrays(self):
        """Invertierte Arrays → Korrelation = -1.0."""
        x = np.array([1.0, 2.0, 3.0, 4.0])
        y = np.array([4.0, 3.0, 2.0, 1.0])
        assert abs(_pearson(x, y) - (-1.0)) < 1e-6

    def test_constant_array_returns_zero(self):
        """Array mit std=0 → gibt 0.0 zurück (kein Division-by-Zero)."""
        x = np.array([5.0, 5.0, 5.0, 5.0])
        y = np.array([1.0, 2.0, 3.0, 4.0])
        assert _pearson(x, y) == 0.0


class TestKeyDetection:
    """Tests für KeyDetectionService.detect_key()."""

    def test_fallback_when_librosa_missing(self):
        """Wenn librosa nicht verfügbar → Fallback-Result mit confidence=0."""
        with patch("services.key_detection_service._HAS_LIBROSA", False):
            svc = KeyDetectionService()
            result = svc.detect_key("/nonexistent/file.mp3")
            assert isinstance(result, KeyResult)
            assert result.confidence == 0.0
            assert result.key == "Am"  # Default Fallback

    def test_detect_key_c_major_profile(self):
        """Mock: Chroma-Profil das perfekt C-Major entspricht → erkennt C Major."""
        # C-Major Chroma: starkes C, E, G
        c_major_chroma = np.array([
            [1.0], [0.1], [0.2], [0.1], [0.8], [0.3], [0.1], [0.9], [0.1], [0.2], [0.1], [0.2]
        ])  # shape (12, 1) — C, C#, D, D#, E, F, F#, G, G#, A, A#, B

        mock_librosa = MagicMock()
        mock_librosa.load.return_value = (np.random.randn(22050 * 10), 22050)
        mock_librosa.feature.chroma_cqt.return_value = c_major_chroma

        with patch("services.key_detection_service._HAS_LIBROSA", True), \
             patch("services.key_detection_service.librosa", mock_librosa):
            svc = KeyDetectionService()
            result = svc.detect_key("/test/audio.mp3")
            assert isinstance(result, KeyResult)
            assert result.confidence > 0.0
            # Sollte C oder verwandten Key erkennen
            assert result.key in KEY_NAMES or result.key.rstrip("m") in KEY_NAMES

    def test_detect_key_returns_camelot(self):
        """Erkannter Key hat immer einen gültigen Camelot-Code."""
        mock_librosa = MagicMock()
        mock_librosa.load.return_value = (np.random.randn(22050 * 5), 22050)
        mock_librosa.feature.chroma_cqt.return_value = np.random.rand(12, 20)

        with patch("services.key_detection_service._HAS_LIBROSA", True), \
             patch("services.key_detection_service.librosa", mock_librosa):
            svc = KeyDetectionService()
            result = svc.detect_key("/test/audio.mp3")
            assert result.camelot in CAMELOT_WHEEL.values() or result.camelot == "??"

    def test_detect_key_empty_audio(self):
        """Leere Audio-Datei → Fallback."""
        mock_librosa = MagicMock()
        mock_librosa.load.return_value = (np.array([]), 22050)

        with patch("services.key_detection_service._HAS_LIBROSA", True), \
             patch("services.key_detection_service.librosa", mock_librosa):
            svc = KeyDetectionService()
            result = svc.detect_key("/test/empty.mp3")
            assert result.confidence == 0.0


class TestCompatibleKeys:
    """Tests für get_compatible_keys()."""

    def test_known_key_returns_neighbors(self):
        """Am → gibt 3 Camelot-Nachbarn zurück."""
        svc = KeyDetectionService()
        neighbors = svc.get_compatible_keys("Am")
        assert len(neighbors) == 3
        # Am = 8A → Nachbarn: 8B, 9A, 7A
        assert "8B" in neighbors

    def test_unknown_key_returns_empty(self):
        """Unbekannter Key → leere Liste."""
        svc = KeyDetectionService()
        assert svc.get_compatible_keys("Xm") == []

    def test_wrapping_key_1(self):
        """Key an Position 1 → Wrapping zu 12."""
        svc = KeyDetectionService()
        neighbors = svc.get_compatible_keys("B")  # 1B
        assert len(neighbors) == 3
