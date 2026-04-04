"""
Tests fuer services/transcription_service.py

Getestet: TranscriptionResult Dataclass, TranscriptionService.transcribe(),
          TranscriptionService.transcribe_and_store(), Fehlerbehandlung.

Hinweis: faster_whisper und torch werden gemockt da sie GPU-Hardware benoetigen.
"""

import sys
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from sqlalchemy.orm import Session

import database
from database import AudioTrack


# ---------------------------------------------------------------------------
# Mock-Setup fuer faster_whisper und torch (nicht installiert in Test-Env)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_gpu_modules(monkeypatch):
    """Mockt faster_whisper und torch Module fuer alle Tests."""
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = False

    mock_faster_whisper = MagicMock()

    monkeypatch.setitem(sys.modules, "torch", mock_torch)
    monkeypatch.setitem(sys.modules, "faster_whisper", mock_faster_whisper)

    # Mock ModelManager and GPU_LOAD_LOCK (imported inside transcribe)
    mock_model_manager_mod = MagicMock()
    mock_model_manager_mod.GPU_LOAD_LOCK = MagicMock()
    mock_model_manager_mod.ModelManager.return_value = MagicMock()
    monkeypatch.setitem(sys.modules, "services.model_manager", mock_model_manager_mod)

    yield mock_faster_whisper, mock_torch


# ---------------------------------------------------------------------------
# TranscriptionResult Tests
# ---------------------------------------------------------------------------

class TestTranscriptionResult:
    """Tests fuer die TranscriptionResult Dataclass."""

    def test_default_values(self):
        from services.transcription_service import TranscriptionResult
        result = TranscriptionResult()

        assert result.text == ""
        assert result.language == ""
        assert result.language_probability == 0.0
        assert result.segments == []
        assert result.duration == 0.0

    def test_custom_values(self):
        from services.transcription_service import TranscriptionResult
        result = TranscriptionResult(
            text="Hello World",
            language="en",
            language_probability=0.95,
            segments=[{"start": 0.0, "end": 1.0, "text": "Hello World"}],
            duration=1.0,
        )

        assert result.text == "Hello World"
        assert result.language == "en"
        assert result.language_probability == 0.95
        assert len(result.segments) == 1
        assert result.duration == 1.0

    def test_segments_default_is_independent(self):
        """Jede Instanz bekommt eine eigene segments-Liste."""
        from services.transcription_service import TranscriptionResult
        r1 = TranscriptionResult()
        r2 = TranscriptionResult()
        r1.segments.append({"text": "only in r1"})

        assert len(r2.segments) == 0


# ---------------------------------------------------------------------------
# TranscriptionService.__init__() Tests
# ---------------------------------------------------------------------------

class TestTranscriptionServiceInit:
    """Tests fuer die Service-Initialisierung."""

    def test_default_model_size(self):
        from services.transcription_service import TranscriptionService
        svc = TranscriptionService()
        assert svc._model_size == "small"

    def test_custom_model_size(self):
        from services.transcription_service import TranscriptionService
        svc = TranscriptionService(model_size="tiny")
        assert svc._model_size == "tiny"

    def test_none_model_size_uses_default(self):
        from services.transcription_service import TranscriptionService
        svc = TranscriptionService(model_size=None)
        assert svc._model_size == "small"


# ---------------------------------------------------------------------------
# transcribe() Tests
# ---------------------------------------------------------------------------

class TestTranscribe:
    """Tests fuer TranscriptionService.transcribe()."""

    def test_file_not_found_raises(self):
        """Nicht existierende Datei → FileNotFoundError."""
        from services.transcription_service import TranscriptionService
        svc = TranscriptionService()

        with pytest.raises(FileNotFoundError):
            svc.transcribe("/nonexistent/audio.wav")

    def test_transcribe_happy_path(self, mock_gpu_modules, tmp_path):
        """Erfolgreiche Transkription mit gemocktem Whisper-Modell."""
        mock_faster_whisper, mock_torch = mock_gpu_modules

        # Create a dummy audio file so Path.exists() returns True
        dummy_audio = tmp_path / "test_audio.wav"
        dummy_audio.write_bytes(b"fake audio data")

        # Mock segment objects
        mock_seg1 = MagicMock()
        mock_seg1.start = 0.0
        mock_seg1.end = 2.5
        mock_seg1.text = " Hello World "

        mock_seg2 = MagicMock()
        mock_seg2.start = 2.5
        mock_seg2.end = 5.0
        mock_seg2.text = " Test transcript "

        # Mock info object
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.92

        # Configure WhisperModel mock
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (
            iter([mock_seg1, mock_seg2]),
            mock_info,
        )
        mock_faster_whisper.WhisperModel.return_value = mock_model

        from services.transcription_service import TranscriptionService
        svc = TranscriptionService(model_size="tiny")
        result = svc.transcribe(str(dummy_audio))

        assert result.text == "Hello World Test transcript"
        assert result.language == "en"
        assert result.language_probability == 0.92
        assert len(result.segments) == 2
        assert result.segments[0]["text"] == "Hello World"
        assert result.segments[1]["start"] == 2.5
        assert result.duration == 5.0

    def test_transcribe_with_language(self, mock_gpu_modules, tmp_path):
        """Transkription mit expliziter Sprache."""
        mock_faster_whisper, _ = mock_gpu_modules

        dummy_audio = tmp_path / "german.wav"
        dummy_audio.write_bytes(b"fake")

        mock_seg = MagicMock()
        mock_seg.start = 0.0
        mock_seg.end = 1.0
        mock_seg.text = " Hallo Welt "

        mock_info = MagicMock()
        mock_info.language = "de"
        mock_info.language_probability = 0.98

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([mock_seg]), mock_info)
        mock_faster_whisper.WhisperModel.return_value = mock_model

        from services.transcription_service import TranscriptionService
        svc = TranscriptionService()
        result = svc.transcribe(str(dummy_audio), language="de")

        assert result.language == "de"
        # Verify language was passed to model.transcribe
        mock_model.transcribe.assert_called_once()
        call_kwargs = mock_model.transcribe.call_args
        assert call_kwargs[1]["language"] == "de"

    def test_transcribe_empty_audio(self, mock_gpu_modules, tmp_path):
        """Leere Audio-Datei → leeres Ergebnis."""
        mock_faster_whisper, _ = mock_gpu_modules

        dummy_audio = tmp_path / "empty.wav"
        dummy_audio.write_bytes(b"fake")

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.5

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), mock_info)
        mock_faster_whisper.WhisperModel.return_value = mock_model

        from services.transcription_service import TranscriptionService
        svc = TranscriptionService()
        result = svc.transcribe(str(dummy_audio))

        assert result.text == ""
        assert result.segments == []
        assert result.duration == 0.0

    def test_progress_callback_invoked(self, mock_gpu_modules, tmp_path):
        """Progress-Callback wird aufgerufen."""
        mock_faster_whisper, _ = mock_gpu_modules

        dummy_audio = tmp_path / "progress.wav"
        dummy_audio.write_bytes(b"fake")

        mock_seg = MagicMock()
        mock_seg.start = 0.0
        mock_seg.end = 1.0
        mock_seg.text = " Test "

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_info.language_probability = 0.9

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([mock_seg]), mock_info)
        mock_faster_whisper.WhisperModel.return_value = mock_model

        from services.transcription_service import TranscriptionService
        svc = TranscriptionService()

        progress_calls = []
        result = svc.transcribe(
            str(dummy_audio),
            progress_cb=lambda p, m: progress_calls.append((p, m)),
        )

        # Should have been called at least for: model loading, transcribing, cleanup, done
        assert len(progress_calls) >= 3
        # Last call should be 100%
        assert progress_calls[-1][0] == 100

    def test_file_not_found_before_progress(self):
        """FileNotFoundError tritt VOR dem Progress-Callback auf."""
        from services.transcription_service import TranscriptionService
        svc = TranscriptionService()
        progress_calls = []

        with pytest.raises(FileNotFoundError):
            svc.transcribe(
                "/nonexistent.wav",
                progress_cb=lambda p, m: progress_calls.append((p, m)),
            )

        assert len(progress_calls) == 0


# ---------------------------------------------------------------------------
# transcribe_and_store() Tests
# ---------------------------------------------------------------------------

class TestTranscribeAndStore:
    """Tests fuer transcribe_and_store()."""

    def test_nonexistent_track_raises(self, test_engine):
        """Fehlender AudioTrack → ValueError."""
        from services.transcription_service import TranscriptionService

        svc = TranscriptionService()

        with pytest.raises(ValueError, match="nicht gefunden"):
            svc.transcribe_and_store(track_id=99999)

    def test_calls_transcribe_with_correct_path(self, test_engine, audio_track):
        """transcribe_and_store liest Pfad aus DB und ruft transcribe() auf."""
        from services.transcription_service import TranscriptionService, TranscriptionResult

        svc = TranscriptionService()

        mock_result = TranscriptionResult(
            text="Mocked text",
            language="de",
            language_probability=0.88,
            segments=[],
            duration=10.0,
        )

        with patch.object(svc, "transcribe", return_value=mock_result) as mock_transcribe:
            result = svc.transcribe_and_store(track_id=audio_track.id, language="de")

        mock_transcribe.assert_called_once_with(
            audio_track.file_path, language="de", progress_cb=None
        )
        assert result.text == "Mocked text"
        assert result.language == "de"

    def test_transcribe_and_store_returns_result(self, test_engine, audio_track):
        """Ergebnis wird korrekt zurueckgegeben."""
        from services.transcription_service import TranscriptionService, TranscriptionResult

        svc = TranscriptionService()
        expected = TranscriptionResult(
            text="Test", language="en", language_probability=0.9,
            segments=[{"start": 0, "end": 1, "text": "Test"}], duration=1.0,
        )

        with patch.object(svc, "transcribe", return_value=expected):
            result = svc.transcribe_and_store(track_id=audio_track.id)

        assert result is expected


# ---------------------------------------------------------------------------
# Model Size Validation Tests
# ---------------------------------------------------------------------------

class TestModelSizes:
    """Tests fuer verschiedene Modell-Groessen."""

    @pytest.mark.parametrize("model_size", ["tiny", "base", "small", "medium", "large"])
    def test_valid_model_sizes(self, model_size):
        from services.transcription_service import TranscriptionService
        svc = TranscriptionService(model_size=model_size)
        assert svc._model_size == model_size
