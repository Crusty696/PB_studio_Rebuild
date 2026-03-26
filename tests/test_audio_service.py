import json
from unittest.mock import patch, MagicMock

import numpy as np

from services.audio_service import AudioAnalyzer
from services.ingest_service import ingest_audio


def test_audio_analyzer_analyze(tmp_path):
    """Testet die analyze-Methode mit gemocktem librosa."""
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"\x00" * 100)

    analyzer = AudioAnalyzer()

    fake_y = np.random.randn(22050 * 5).astype(np.float32)  # 5 Sekunden

    with patch("services.audio_service.librosa") as mock_librosa:
        mock_librosa.load.return_value = (fake_y, 22050)
        mock_librosa.get_duration.return_value = 5.0
        mock_librosa.beat.beat_track.return_value = (np.float64(120.0), np.array([]))
        mock_librosa.feature.rms.return_value = np.array([[0.1, 0.2, 0.3, 0.4, 0.5]])

        result = analyzer.analyze(str(audio_file))

    assert result["bpm"] == 120.0
    assert result["duration"] == 5.0
    assert len(result["energy_curve"]) == 5


def test_analyze_and_store_updates_db(tmp_path, project):
    """Testet, dass analyze_and_store die DB korrekt aktualisiert."""
    audio_file = tmp_path / "store_test.wav"
    audio_file.write_bytes(b"\x00" * 100)

    track = ingest_audio(str(audio_file))
    assert track is not None

    analyzer = AudioAnalyzer()
    fake_y = np.random.randn(22050 * 3).astype(np.float32)

    with patch("services.audio_service.librosa") as mock_librosa:
        mock_librosa.load.return_value = (fake_y, 22050)
        mock_librosa.get_duration.return_value = 3.0
        mock_librosa.beat.beat_track.return_value = (np.float64(140.0), np.array([]))
        mock_librosa.feature.rms.return_value = np.array([[0.5, 0.6, 0.7]])

        result = analyzer.analyze_and_store(track.id)

    assert result["bpm"] == 140.0

    # Prüfe DB
    from sqlalchemy.orm import Session
    from database import engine, AudioTrack
    with Session(engine) as session:
        db_track = session.get(AudioTrack, track.id)
        assert db_track.bpm == 140.0
        assert db_track.energy_curve is not None
        energy = json.loads(db_track.energy_curve)
        assert len(energy) == 3
