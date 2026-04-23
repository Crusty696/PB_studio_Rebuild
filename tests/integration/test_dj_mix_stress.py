import pytest
import numpy as np
from unittest.mock import MagicMock, patch
from services.onset_rhythm_service import OnsetRhythmService, RhythmAnalysis, PercussiveOnset

def test_dj_mix_chunking_logic_no_oom():
    """
    P13: Testet die Chunking-Logik des OnsetRhythmService für lange Mixe.
    Simuliert einen 3-Stunden Mix und prüft die Aggregation ohne echten RAM-Overload.
    """
    service = OnsetRhythmService()
    
    # 3 Stunden in Sekunden
    total_duration = 3 * 3600 
    
    # Wir mocken librosa.load und analyze, um keine echten Daten zu verarbeiten
    # aber die Loop-Struktur zu testen.
    mock_y = np.zeros(1000) 
    mock_sr = 22050
    
    with patch("librosa.load", return_value=(mock_y, mock_sr)), \
         patch("librosa.get_duration", return_value=total_duration), \
         patch("services.onset_rhythm_service.OnsetRhythmService.analyze") as mock_analyze, \
         patch("services.pacing_beat_grid._get_beat_positions", return_value=[i * 0.5 for i in range(100)]), \
         patch("sqlalchemy.orm.Session") as mock_session_cls, \
         patch("database.nullpool_session") as mock_nullpool_ctx:
        
        # Setup mock session for analyze_and_store (Session(engine))
        mock_session = MagicMock()
        mock_session_cls.return_value.__enter__.return_value = mock_session
        
        mock_track = MagicMock()
        mock_track.file_path = "mock_mix.wav"
        mock_track.stem_drums_path = None
        mock_session.query.return_value.filter.return_value.first.return_value = mock_track
        
        # Mock analyze return value for each chunk
        def side_effect(y, sr, beats, drums_y=None):
            return RhythmAnalysis(
                onsets_kick=[PercussiveOnset(time=1.0, strength=0.8)],
                onsets_snare=[PercussiveOnset(time=2.0, strength=0.7)],
                onsets_hihat=[PercussiveOnset(time=3.0, strength=0.6)],
                onset_strength_curve=[0.1, 0.2, 0.3],
                syncopation_score=0.4,
                groove_template="4on4_techno",
                groove_confidence=0.9,
                swing_ratio=0.5
            )
        mock_analyze.side_effect = side_effect
        
        # Wir mocken auch _store, um DB-Schreibvorgänge zu vermeiden
        with patch("services.onset_rhythm_service.OnsetRhythmService._store") as mock_store:
            analysis = service.analyze_and_store(track_id=1)
            
            assert analysis is not None
            # Bei 3 Stunden (10800s) und 900s Chunks erwarten wir 12 Chunks.
            assert mock_analyze.call_count >= 12
            
            # Prüfen ob Aggregation funktioniert hat
            assert len(analysis.onsets_kick) >= 12
            assert analysis.syncopation_score == 0.4 
            assert analysis.groove_template == "4on4_techno"

def test_aggregate_results_deduplication():
    """Prüft ob die Deduplizierung in Overlap-Zonen funktioniert."""
    service = OnsetRhythmService()
    
    a1 = RhythmAnalysis(onsets_kick=[PercussiveOnset(time=898.0, strength=0.8)])
    a2 = RhythmAnalysis(onsets_kick=[PercussiveOnset(time=3.0, strength=0.8)])
    
    analyses = [a1, a2]
    offsets = [0.0, 895.0] 
    
    aggregated = service._aggregate_results(analyses, offsets, 1800.0)
    
    # Sollte nur einen Kick Onset haben
    assert len(aggregated.onsets_kick) == 1
    assert aggregated.onsets_kick[0].time == 898.0
