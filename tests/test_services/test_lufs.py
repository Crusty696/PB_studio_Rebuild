"""Tests für LUFSService — EBU R128 Loudness Measurement."""

import pytest
from unittest.mock import patch, MagicMock
import subprocess

from services.lufs_service import (
    LUFSService, LUFSResult,
    _parse_loudnorm_json, _safe_float,
)


class TestSafeFloat:
    """Tests für _safe_float() Edge Cases."""

    def test_normal_float(self):
        assert _safe_float(3.14) == 3.14

    def test_string_float(self):
        assert _safe_float("-14.02") == -14.02

    def test_negative_infinity(self):
        """'-inf' wird auf -70.0 geclampft."""
        assert _safe_float(float("-inf")) == -70.0

    def test_positive_infinity(self):
        """'+inf' wird auf 0.0 geclampft."""
        assert _safe_float(float("inf")) == 0.0

    def test_string_inf(self):
        assert _safe_float("-inf") == -70.0

    def test_invalid_string(self):
        assert _safe_float("abc", default=-99.0) == -99.0

    def test_none(self):
        assert _safe_float(None) == 0.0

    def test_zero(self):
        assert _safe_float(0.0) == 0.0


class TestParseLoudnormJson:
    """Tests für _parse_loudnorm_json() FFmpeg Output Parsing."""

    def test_real_ffmpeg_output(self):
        """Parst echten FFmpeg loudnorm JSON Output."""
        stderr = '''
[Parsed_loudnorm_0 @ 0x7f8b1c000b80]
{
    "input_i" : "-14.02",
    "input_tp" : "-0.31",
    "input_lra" : "8.50",
    "input_thresh" : "-24.78",
    "output_i" : "-24.00",
    "output_tp" : "-2.00",
    "output_lra" : "7.00",
    "output_thresh" : "-34.17",
    "normalization_type" : "dynamic",
    "target_offset" : "-0.02"
}
'''
        data = _parse_loudnorm_json(stderr)
        assert data is not None
        assert data["input_i"] == "-14.02"
        assert data["input_tp"] == "-0.31"
        assert data["input_lra"] == "8.50"

    def test_empty_stderr(self):
        """Leeres stderr → None."""
        assert _parse_loudnorm_json("") is None

    def test_no_json_block(self):
        """stderr ohne JSON → None."""
        assert _parse_loudnorm_json("Some random FFmpeg output\nno json here") is None

    def test_malformed_json(self):
        """Kaputtes JSON → None (kein Crash)."""
        assert _parse_loudnorm_json('{"input_i": broken}') is None


class TestLUFSService:
    """Tests für LUFSService.analyze()."""

    def test_successful_analysis(self):
        """Mock: Normaler FFmpeg-Lauf → korrekte LUFS-Werte."""
        fake_stderr = '''
{
    "input_i" : "-14.02",
    "input_tp" : "-0.31",
    "input_lra" : "8.50",
    "input_thresh" : "-24.78"
}
'''
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = fake_stderr

        with patch("services.lufs_service.subprocess.run", return_value=mock_result):
            svc = LUFSService()
            result = svc.analyze("/test/audio.mp3")
            assert isinstance(result, LUFSResult)
            assert result.integrated == -14.02
            assert result.loudness_range == 8.50
            assert result.true_peak == -0.31

    def test_ffmpeg_not_found(self):
        """FFmpeg nicht installiert → Fallback-Result."""
        with patch("services.lufs_service.subprocess.run", side_effect=FileNotFoundError):
            svc = LUFSService()
            result = svc.analyze("/test/audio.mp3")
            assert isinstance(result, LUFSResult)
            assert result.integrated == -14.0  # Fallback

    def test_ffmpeg_timeout(self):
        """FFmpeg Timeout → Fallback-Result."""
        with patch("services.lufs_service.subprocess.run",
                    side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=120)):
            svc = LUFSService()
            result = svc.analyze("/test/audio.mp3")
            assert isinstance(result, LUFSResult)
            assert result.integrated == -14.0

    def test_short_term_max_clamped(self):
        """Short-term max darf true_peak + 3 dB nicht überschreiten."""
        fake_stderr = '{"input_i": "-5.0", "input_tp": "-1.0", "input_lra": "20.0"}'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = fake_stderr

        with patch("services.lufs_service.subprocess.run", return_value=mock_result):
            svc = LUFSService()
            result = svc.analyze("/test/loud.mp3")
            # integrated(-5) + lra(20)/2 = 5.0, aber clamped to tp(-1) + 3 = 2.0
            assert result.short_term_max <= result.true_peak + 3.0
