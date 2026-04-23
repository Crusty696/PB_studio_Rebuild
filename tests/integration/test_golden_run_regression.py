import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np

from services.pacing_service import PacingService
from services.pacing_beat_grid import _get_beat_positions
from agents.pacing_agent import PacingAgent
from database import AudioTrack, VideoClip, Beatgrid

def test_golden_run_pipeline_regression(db_session, project):
    """
    P14: Golden-Run-Snapshot Test.
    Führt die Pacing-Pipeline mit echten Fixtures aus und prüft auf Fehlerfreiheit.
    """
    # 1. Fixtures lokalisieren
    fixtures_dir = Path(__file__).resolve().parent.parent / "fixtures"
    audio_path = fixtures_dir / "golden_mix" / "segment.wav"
    clips_dir = fixtures_dir / "clips_20"
    
    if not audio_path.exists():
        pytest.skip(f"Audio fixture {audio_path} nicht gefunden")
    
    # 2. DB Einträge erstellen
    track = AudioTrack(
        project_id=project.id,
        file_path=str(audio_path),
        duration=30.0, # Annahme für segment.wav
        bpm=124.0,
        status="PROCESSED"
    )
    db_session.add(track)
    db_session.commit()
    
    # Beatgrid mit fiktiven Beats erstellen (124 BPM -> ~0.48s pro Beat)
    beats = [i * (60.0/124.0) for i in range(60)]
    bg = Beatgrid(
        audio_track_id=track.id,
        beat_positions=beats,
        confidence=1.0
    )
    db_session.add(bg)
    db_session.commit()
    
    # 3 Video Clips hinzufügen
    video_files = list(clips_dir.glob("*.mp4"))[:5]
    for i, v_path in enumerate(video_files):
        clip = VideoClip(
            project_id=project.id,
            file_path=str(v_path),
            duration=10.0,
            status="PROCESSED"
        )
        db_session.add(clip)
    db_session.commit()
    
    # 3. Pacing Service ausführen
    # Mocking Ollama/LLM Response des PacingAgents, um Netzwerk-Abhängigkeit zu vermeiden
    # Der Agent soll eine gültige Strategie zurückgeben.

    with patch("services.ollama_client.OllamaClient.chat") as mock_chat, \
         patch("services.pacing_beat_grid._get_cached_stem_audio", return_value=(np.zeros(1000), 22050)), \
         patch("services.pacing_beat_grid._get_beat_data_combined") as mock_beats:

        # Mock LLM response
        mock_chat.return_value = '{"strategy": "techno_aggressive", "cut_rate": 2, "vibe": "dark"}'

        # Mock beat data (energy per beat)
        mock_beats.return_value = (beats, [0.5] * len(beats), [0.3] * len(beats), [0.1] * len(beats), [0.2] * len(beats))

        from services.pacing_beat_grid import AdvancedPacingSettings
        from services.pacing_service import auto_edit_phase3

        video_ids = [c.id for c in db_session.query(VideoClip).filter_by(project_id=project.id).all()]
        settings = AdvancedPacingSettings(base_cut_rate=4) # Alle 4 Beats ein Schnitt

        # 4. Pipeline ausführen (4-Stage Pacing)
        segments, strategy_used = auto_edit_phase3(track.id, video_ids, settings)

        # 5. Assertions
        assert len(segments) > 0, "Die Pipeline sollte mindestens ein Timeline-Segment generieren."
        assert segments[0].video_id in video_ids, "Das Video-ID im Segment muss aus der Liste der Clips stammen."
        assert segments[0].start == beats[0], "Der erste Schnitt muss auf dem ersten Beat liegen."

        # Überprüfen ob es valide Cut-Entscheidungen sind
        for i in range(len(segments) - 1):
            assert segments[i].end == segments[i+1].start, "Segmente müssen lückenlos aneinandergrenzen."

