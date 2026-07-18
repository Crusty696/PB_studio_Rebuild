import pytest
from services.pacing_service import auto_edit_phase3, AdvancedPacingSettings
from database import Session, engine, Project, AudioTrack, VideoClip, Beatgrid

def test_beat_analysis_degradation_fallback(tmp_path):
    """B2 (PIPE-009): Verifiziert, dass bei fehlenden Beat-Positions
    ein BPM-Fallback ausgeloest wird und alle Segmente als degraded markiert sind."""
    
    with Session(engine) as session:
        # Check or create project
        project = session.query(Project).filter_by(id=1).first()
        if not project:
            project = Project(id=1, name="Test Project", path=".")
            session.add(project)
            session.commit()
            
        # Audio Track erstellen
        audio = session.query(AudioTrack).filter_by(id=998).first()
        if not audio:
            audio = AudioTrack(
                id=998,
                project_id=1,
                file_path="dummy_audio_b2.mp3",
                duration=30.0,
                bpm=120.0
            )
            session.add(audio)
            session.commit()
        
        # Beatgrid erstellen aber OHNE beat_positions! (Simuliert fehlgeschlagene beat_this Analyse)
        bg = session.query(Beatgrid).filter_by(audio_track_id=998).first()
        if bg:
            session.delete(bg)
            session.commit()
            
        bg = Beatgrid(
            audio_track_id=998,
            bpm=120.0,
            offset=0.0,
            beat_positions=None,      # Keine Beats
            downbeat_positions=None,
            energy_per_beat=None,
        )
        session.add(bg)
        session.commit()
        
        # Video Clip erstellen
        video = session.query(VideoClip).filter_by(id=998).first()
        if not video:
            video = VideoClip(
                id=998,
                project_id=1,
                file_path="dummy_video_b2.mp4",
                duration=10.0
            )
            session.add(video)
            session.commit()
            
    settings = AdvancedPacingSettings(
        base_cut_rate=4,
        energy_reactivity=50.0,
        breakdown_behavior="none",
        vibe="", # leere Vibe um SigLIP-degraded nicht zu triggern (falls moeglich, aber mood_embeddings koennte leer sein)
    )
    
    # auto_edit_phase3 ausfuehren (sollte fehlerfrei durchlaufen)
    segments, cut_points = auto_edit_phase3(
        audio_id=998,
        video_clip_ids=[998],
        settings=settings,
    )
    
    # Assertions
    assert len(segments) > 0
    assert all(seg.degraded for seg in segments), "Alle Segmente muessen wegen Beat-Fallback degraded sein."
    # B2-Rest: Ursache muss mitgefuehrt werden, damit die UI-Warnung nicht
    # pauschal "SigLIP" behauptet.
    assert all("beat_fallback" in seg.degraded_reason for seg in segments), \
        "degraded_reason muss 'beat_fallback' enthalten."
