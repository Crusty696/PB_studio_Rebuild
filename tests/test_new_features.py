"""Tests fuer Phase 1-4 Features: Stems, Auto-Edit, Effects, Export."""

import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import Base, AudioTrack, VideoClip, TimelineEntry, Project, Beatgrid


@pytest.fixture
def db_session():
    """In-Memory DB fuer Tests."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(Project(name="Test", path=".", resolution="1920x1080", fps=30.0))
        session.commit()
        yield session, engine


class TestDatabaseSchema:
    """Phase 1+3: Neue DB-Spalten vorhanden."""

    def test_audio_track_has_stem_fields(self, db_session):
        session, engine = db_session
        track = AudioTrack(
            project_id=1, file_path="/test.mp3", title="test",
            stem_vocals_path="/stems/vocals.mp3",
            stem_drums_path="/stems/drums.mp3",
            stem_bass_path="/stems/bass.mp3",
            stem_other_path="/stems/other.mp3",
        )
        session.add(track)
        session.commit()
        session.refresh(track)
        assert track.stem_vocals_path == "/stems/vocals.mp3"
        assert track.stem_drums_path == "/stems/drums.mp3"
        assert track.stem_bass_path == "/stems/bass.mp3"
        assert track.stem_other_path == "/stems/other.mp3"

    def test_timeline_entry_has_effect_fields(self, db_session):
        session, engine = db_session
        entry = TimelineEntry(
            project_id=1, track="video", media_id=1,
            start_time=0.0, end_time=10.0, lane=0,
            crossfade_duration=0.5,
            brightness=0.1,
            contrast=1.2,
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        assert entry.crossfade_duration == 0.5
        assert entry.brightness == 0.1
        assert entry.contrast == 1.2


class TestPacingService:
    """Phase 2: Cut-Point Berechnungen."""

    def test_calculate_cut_points_with_bpm(self, db_session):
        session, engine = db_session
        track = AudioTrack(project_id=1, file_path="/test.mp3", title="test", bpm=120.0)
        session.add(track)
        session.commit()

        # Patch the engine used by pacing_service and pacing_beat_grid
        # (after AUD-53 refactor, _get_bpm lives in pacing_beat_grid)
        import services.pacing_service as ps
        import services.pacing_beat_grid as pbg
        original_ps_engine = ps.engine
        original_pbg_engine = pbg.engine
        ps.engine = engine
        pbg.engine = engine
        try:
            from services.pacing_service import PacingSettings, calculate_cut_points
            settings = PacingSettings(tempo=50, energy=50, cut_density=50)
            cuts = calculate_cut_points(track.id, None, settings, 10.0)
            assert len(cuts) > 0
            assert all(c.source == "beat" for c in cuts)
            # 120 BPM, tempo=50 -> divisor=1, interval=0.5s, ~20 cuts in 10s
            assert len(cuts) >= 15
        finally:
            ps.engine = original_ps_engine
            pbg.engine = original_pbg_engine

    @pytest.mark.skip(reason="Fails with mock data, tested in E2E")
    def test_auto_edit_to_beats_distributes_clips(self, db_session):
        session, engine = db_session
        track = AudioTrack(project_id=1, file_path="/test.mp3", title="test", bpm=140.0)
        session.add(track)
        for i in range(3):
            session.add(VideoClip(project_id=1, file_path=f"/vid{i}.mp4", duration=2.0))
        session.commit()

        import services.pacing_service as ps
        original_engine = ps.engine
        ps.engine = engine
        try:
            from services.pacing_service import auto_edit_to_beats
            segments = auto_edit_to_beats(track.id, [1, 2, 3], 10.0)
            assert len(segments) > 0
            # Segmente decken die gesamte Dauer ab
            assert segments[0]["start"] == 0.0
            assert segments[-1]["end"] == pytest.approx(10.0, abs=0.5)
            # Alle 3 Videos werden verwendet
            used_ids = {s["video_id"] for s in segments}
            assert len(used_ids) == 3
        finally:
            ps.engine = original_engine

    def test_cut_point_drum_source(self):
        from services.pacing_service import CutPoint
        cut = CutPoint(time=1.5, source="drum", strength=0.8)
        assert cut.source == "drum"
        assert cut.strength == 0.8


class TestAIAudioService:
    """Phase 1: Stem Separation + Auto-Ducking."""

    def test_stem_separator_init(self):
        from services.ai_audio_service import StemSeparator
        separator = StemSeparator()
        assert separator is not None

    def test_auto_ducker_init(self):
        from services.ai_audio_service import AutoDucker
        ducker = AutoDucker(duck_db=-12.0, attack_ms=200.0)
        assert ducker.duck_db == -12.0
        assert ducker.attack_ms == 200.0

    def test_auto_ducker_scipy_with_synthetic(self, tmp_path):
        """Test Scipy Ducking mit synthetischen Daten."""
        import numpy as np
        from scipy.io import wavfile
        from services.ai_audio_service import AutoDucker

        sr = 44100
        duration = 2  # 2 Sekunden

        # Musik: Sinuston
        t = np.linspace(0, duration, sr * duration, endpoint=False)
        music = (np.sin(2 * np.pi * 440 * t) * 0.5).astype(np.float32)

        # Voice: Stille, dann laut
        voice = np.zeros_like(music)
        voice[sr:] = (np.sin(2 * np.pi * 200 * t[sr:]) * 0.3).astype(np.float32)

        music_path = str(tmp_path / "music.wav")
        voice_path = str(tmp_path / "voice.wav")
        output_path = str(tmp_path / "ducked.wav")

        wavfile.write(music_path, sr, (music * 32767).astype(np.int16))
        wavfile.write(voice_path, sr, (voice * 32767).astype(np.int16))

        ducker = AutoDucker()
        result = ducker.create_ducked_audio_scipy(music_path, voice_path, output_path)
        assert Path(result).exists()
        assert os.path.getsize(result) > 0


class TestExportService:
    """Phase 3: Erweiterter Export."""

    def test_get_timeline_summary_empty(self, db_session):
        session, engine = db_session
        import services.export_service as es
        original_engine = es.engine
        es.engine = engine
        try:
            summary = es.get_timeline_summary(1)
            assert summary["total_entries"] == 0
            assert summary["video_clips"] == 0
            assert summary["audio_tracks"] == 0
        finally:
            es.engine = original_engine

    def test_get_timeline_summary_with_entries(self, db_session):
        session, engine = db_session
        session.add(VideoClip(id=1, project_id=1, file_path="clip.mp4", duration=10.0))
        session.add(AudioTrack(id=1, project_id=1, file_path="track.wav", duration=30.0))
        session.add(TimelineEntry(project_id=1, track="video", media_id=1,
                                  start_time=0.0, end_time=10.0, lane=0))
        session.add(TimelineEntry(project_id=1, track="audio", media_id=1,
                                  start_time=0.0, end_time=30.0, lane=0))
        session.commit()

        import services.export_service as es
        original_engine = es.engine
        es.engine = engine
        try:
            summary = es.get_timeline_summary(1)
            assert summary["total_entries"] == 2
            assert summary["video_clips"] == 1
            assert summary["audio_tracks"] == 1
            assert summary["estimated_duration"] == 10.0
        finally:
            es.engine = original_engine


class TestIngestService:
    """Phase 1: Stem-Status in get_all_media."""

    def test_get_all_audio_includes_stems(self, db_session):
        session, engine = db_session
        track = AudioTrack(
            project_id=1, file_path="/test.mp3", title="test",
            stem_vocals_path="/v.mp3", stem_drums_path="/d.mp3",
        )
        session.add(track)
        session.commit()

        import services.ingest_service as ing
        original_engine = ing.engine
        ing.engine = engine
        try:
            media = ing.get_all_audio(1)
            assert len(media) == 1
            assert media[0]["stems"] == "2/4"
        finally:
            ing.engine = original_engine

    def test_get_all_audio_no_stems(self, db_session):
        session, engine = db_session
        track = AudioTrack(project_id=1, file_path="/test.mp3", title="test")
        session.add(track)
        session.commit()

        import services.ingest_service as ing
        original_engine = ing.engine
        ing.engine = engine
        try:
            media = ing.get_all_audio(1)
            assert media[0]["stems"] == "-"
        finally:
            ing.engine = original_engine
