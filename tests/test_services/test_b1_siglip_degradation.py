import pytest
from unittest.mock import patch
from services.pacing_service import auto_edit_phase3, AdvancedPacingSettings
from database import Session, engine, Project, AudioTrack, VideoClip

def test_siglip_degradation_fallback(tmp_path):
    """B1 (PIPE-008): Verifiziert, dass ein SigLIP-Ausfall nicht abstuerzt,
    sondern alle Segmente als degraded markiert."""
    
    # 1. Mocken von _precompute_mood_embeddings, um Fehler zu provozieren
    with patch("services.pacing_service._precompute_mood_embeddings") as mock_moods:
        mock_moods.side_effect = RuntimeError("SigLIP model loading failed (OOM)")
        
        # We need a minimal DB state
        with Session(engine) as session:
            # Check or create project
            project = session.query(Project).filter_by(id=1).first()
            if not project:
                project = Project(id=1, name="Test Project", path=".")
                session.add(project)
                session.commit()
                
            # Audio Track erstellen
            audio = session.query(AudioTrack).filter_by(id=999).first()
            if not audio:
                audio = AudioTrack(
                    id=999,
                    project_id=1,
                    file_path="dummy_audio.mp3",
                    duration=30.0,
                    bpm=120.0
                )
                session.add(audio)
                session.commit()
            
            # Video Clip erstellen
            video = session.query(VideoClip).filter_by(id=999).first()
            if not video:
                video = VideoClip(
                    id=999,
                    project_id=1,
                    file_path="dummy_video.mp4",
                    duration=10.0
                )
                session.add(video)
                session.commit()
                
        settings = AdvancedPacingSettings(
            base_cut_rate=4,
            energy_reactivity=50.0,
            breakdown_behavior="none",
            vibe="energetic",
        )
        
        # 2. auto_edit_phase3 ausfuehren (sollte fehlerfrei durchlaufen)
        segments, cut_points = auto_edit_phase3(
            audio_id=999,
            video_clip_ids=[999],
            settings=settings,
        )
        
        # 3. Assertions
        assert len(segments) > 0
        assert all(seg.degraded for seg in segments), "Alle Segmente muessen als degraded markiert sein."
