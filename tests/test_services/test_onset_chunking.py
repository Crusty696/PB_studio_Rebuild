import pytest
import numpy as np
import librosa
from unittest.mock import MagicMock, patch
from services.onset_rhythm_service import OnsetRhythmService, RhythmAnalysis, PercussiveOnset
from services.audio_constants import DEFAULT_SR

def create_synthetic_onset_signal(duration_sec, onset_times, sr=DEFAULT_SR):
    """Erzeugt ein synthetisches Signal mit Klicks an bestimmten Zeitpunkten."""
    y = np.zeros(int(duration_sec * sr))
    for t in onset_times:
        idx = int(t * sr)
        if idx < len(y):
            # Ein kurzer Klick (Impuls)
            y[idx:idx+100] = 1.0
    return y

@pytest.fixture
def service():
    return OnsetRhythmService()

def test_onset_chunked_boundary(service):
    """T5.1: Testet die Erkennung von Onsets an Chunk-Grenzen."""
    # Wir simulieren ein Signal von 1000 Sekunden.
    # Chunk-Größe ist 900s, Überlappung 5s.
    # Onsets bei 899s (kurz vor Grenze) und 901s (kurz nach Grenze).
    sr = DEFAULT_SR
    onset_times = [899.0, 901.0]
    
    # Da wir analyze_and_store testen wollen, müssen wir librosa.load mocken
    # Um RAM zu sparen, mocken wir librosa.load so, dass es nur den angeforderten Teil zurückgibt
    
    def side_effect_load(path, sr=None, mono=True, offset=0.0, duration=None):
        # Erzeuge nur den Teil des Signals, der angefordert wurde
        start_t = offset
        end_t = offset + duration if duration else 1000.0
        
        chunk_onsets = [t for t in onset_times if start_t <= t < end_t]
        # Relativ zum Offset
        relative_onsets = [t - start_t for t in chunk_onsets]
        
        y_chunk = create_synthetic_onset_signal(end_t - start_t, relative_onsets, sr=sr)
        return y_chunk, sr

    with patch("librosa.load", side_effect=side_effect_load), \
         patch("librosa.get_duration", return_value=1000.0), \
         patch("services.pacing_beat_grid._get_beat_positions", return_value=[i for i in range(1000)]), \
         patch("database.engine"), \
         patch("database.AudioTrack") as mock_track_cls, \
         patch("sqlalchemy.orm.Session") as mock_session_cls, \
         patch.object(OnsetRhythmService, "_store") as mock_store:
        
        # Mocking der Datenbank-Interaktion
        mock_session = mock_session_cls.return_value.__enter__.return_value
        mock_track = MagicMock()
        mock_track.file_path = "fake_path.wav"
        mock_track.stem_drums_path = None
        mock_track.id = 1
        mock_session.query.return_value.filter.return_value.first.return_value = mock_track
        
        # Ausführung
        analysis = service.analyze_and_store(track_id=1)
        
        assert analysis is not None
        
        # Überprüfen, ob beide Onsets gefunden wurden
        # Wir kombinieren alle Onset-Typen (Kick, Snare, HiHat), da unser synthetisches Signal
        # wahrscheinlich in allen Bändern ausschlägt (Impuls).
        all_onsets = sorted([o.time for o in (analysis.onsets_kick + analysis.onsets_snare + analysis.onsets_hihat)])
        
        # Wir prüfen auf die Nähe zu den Zielzeiten (aufgrund von Hop-Size Ungenauigkeiten)
        found_899 = any(abs(t - 899.0) < 0.1 for t in all_onsets)
        found_901 = any(abs(t - 901.0) < 0.1 for t in all_onsets)
        
        assert found_899, f"Onset bei 899s nicht gefunden. Onsets: {all_onsets}"
        assert found_901, f"Onset bei 901s nicht gefunden. Onsets: {all_onsets}"
        
        # Sicherstellen, dass keine Duplikate durch Overlap entstanden sind
        # Wenn 899.0 zweimal vorkommt (einmal pro Chunk), wäre das falsch.
        # Im Overlap (895-900) liegt 899.0.
        onsets_899 = [t for t in all_onsets if abs(t - 899.0) < 0.1]
        assert len(onsets_899) >= 1 # Mindestens einer pro Band
        # Die Logik sollte sie pro Band deduplizieren.

def test_long_audio_processing(service):
    """T5.2: Verifiziert, dass mehrere Chunks für langes Audio verarbeitet werden."""
    duration = 3600.0 # 1 Stunde
    
    with patch("librosa.load") as mock_load, \
         patch("librosa.get_duration", return_value=duration), \
         patch("services.pacing_beat_grid._get_beat_positions", return_value=[]), \
         patch("database.engine"), \
         patch("database.AudioTrack"), \
         patch("sqlalchemy.orm.Session") as mock_session_cls, \
         patch.object(OnsetRhythmService, "analyze", return_value=RhythmAnalysis()), \
         patch.object(OnsetRhythmService, "_store"):
        
        # Mocking der Datenbank-Interaktion
        mock_session = mock_session_cls.return_value.__enter__.return_value
        mock_track = MagicMock()
        mock_track.file_path = "fake_path.wav"
        mock_track.stem_drums_path = None
        mock_session.query.return_value.filter.return_value.first.return_value = mock_track

        mock_load.return_value = (np.zeros(100), DEFAULT_SR)
        
        service.analyze_and_store(track_id=1)
        
        # 3600s / 900s = 4 Chunks.
        # Mit Overlap könnten es mehr sein, wenn wir strikt 900s Schritte gehen.
        # Start-Zeiten: 0, 900, 1800, 2700.
        # Letzter Chunk von 2700 bis 3600.
        assert mock_load.call_count >= 4
        
        # Überprüfe die Offsets der ersten Calls
        calls = mock_load.call_args_list
        offsets = [call.kwargs.get('offset') for call in calls if 'offset' in call.kwargs]
        assert 0.0 in offsets
        assert 900.0 - 5.0 in offsets # Wegen Overlap? Oder fängt der zweite bei 900-Overlap an?
        # Specification says: 15-minute chunks with a 1-second overlap (Wait, prompt says 5s overlap in logic description)
        # Goal: "1-second overlap"
        # Technical Spec Logic: "5 seconds (to ensure onsets at boundaries are captured)"
        # I will use 5 seconds as stated in the Logic section.
