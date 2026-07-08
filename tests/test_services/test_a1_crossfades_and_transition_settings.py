import pytest
from database import nullpool_session, Project
from services.pacing_beat_grid import AdvancedPacingSettings
from services.pacing_service import _auto_edit_phase3_inner
from database import engine

@pytest.fixture(scope="module")
def db_setup():
    from database.migrations import init_db
    init_db()  # Migrationen ausführen, um neue Spalten anzulegen
    
    with nullpool_session() as session:
        proj = Project(name="Test A1 Project", path=".", resolution="1920x1080", fps=30.0, transition_type="crossfade")
        session.add(proj)
        session.commit()
        proj_id = proj.id
        
        # Ein paar Testdaten: AudioTrack und VideoClip einpflegen
        from database import AudioTrack, VideoClip, Beatgrid
        audio = AudioTrack(project_id=proj_id, file_path="test_a1.mp3", duration=60.0, bpm=120.0)
        session.add(audio)
        session.commit()
        
        # Beatgrid für den AudioTrack erstellen
        bg = Beatgrid(
            audio_track_id=audio.id,
            bpm=120.0,
            offset=0.0,
            beat_positions=[i * 0.5 for i in range(120)],
            downbeat_positions=[i * 2.0 for i in range(30)],
            energy_per_beat=[0.5] * 120
        )
        session.add(bg)
        
        video = VideoClip(project_id=proj_id, file_path="test_a1.mp4", duration=30.0, fps=30.0)
        session.add(video)
        session.commit()
        
        # Scene für den VideoClip erstellen
        from database import Scene
        scene = Scene(video_clip_id=video.id, start_time=0.0, end_time=30.0, energy=0.6)
        session.add(scene)
        session.commit()
        
        yield proj_id, audio.id, video.id
        
        # Cleanup
        session.query(Scene).filter_by(video_clip_id=video.id).delete()
        session.query(Beatgrid).filter_by(audio_track_id=audio.id).delete()
        session.query(VideoClip).filter_by(project_id=proj_id).delete()
        session.query(AudioTrack).filter_by(project_id=proj_id).delete()
        session.query(Project).filter_by(id=proj_id).delete()
        session.commit()

def test_pacing_crossfade_transitions(db_setup):
    """Testet, dass bei 'crossfade' Übergängen automatisch berechnete Crossfades gesetzt werden."""
    proj_id, audio_id, video_id = db_setup
    
    settings = AdvancedPacingSettings(
        base_cut_rate=4,
        energy_reactivity=50,
        breakdown_behavior="halve",
        transition_type="crossfade"
    )
    
    # Auto-Edit ausführen
    segments, cut_points = _auto_edit_phase3_inner(
        engine, audio_id=audio_id, video_clip_ids=[video_id], settings=settings
    )
    
    assert len(segments) > 0
    # Es muss mindestens einige Segmente mit Crossfade > 0.0 geben
    crossfades = [s.crossfade_duration for s in segments if s.crossfade_duration > 0.0]
    assert len(crossfades) > 0

def test_pacing_cut_transitions(db_setup):
    """Testet, dass bei 'cut' Übergängen alle Crossfades exakt 0.0 sind."""
    proj_id, audio_id, video_id = db_setup
    
    settings = AdvancedPacingSettings(
        base_cut_rate=4,
        energy_reactivity=50,
        breakdown_behavior="halve",
        transition_type="cut"
    )
    
    # Auto-Edit ausführen
    segments, cut_points = _auto_edit_phase3_inner(
        engine, audio_id=audio_id, video_clip_ids=[video_id], settings=settings
    )
    
    assert len(segments) > 0
    # Alle Segmente müssen crossfade_duration == 0.0 besitzen
    for s in segments:
        assert s.crossfade_duration == 0.0
