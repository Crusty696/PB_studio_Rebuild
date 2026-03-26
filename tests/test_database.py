"""
Tests fuer database.py – Models, FK-Constraints, Cascade-Delete.
"""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import database
from database import (
    AudioTrack,
    Beatgrid,
    Base,
    ClipAnchor,
    PacingBlueprint,
    Project,
    Scene,
    TimelineEntry,
    VideoClip,
    WaveformData,
)


# ---------------------------------------------------------------------------
# Hilfsfunktion: Frische In-Memory-Engine mit FK-Support
# ---------------------------------------------------------------------------

def _make_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(eng, "connect")
    def _fk(conn, _rec):
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(eng)
    return eng


# ---------------------------------------------------------------------------
# Projekt-Tests
# ---------------------------------------------------------------------------

class TestProjectModel:
    def test_create_and_read_project(self):
        """Projekt anlegen und wieder laden."""
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="DJ Set", path="/music", resolution="1920x1080", fps=25.0)
            s.add(proj)
            s.commit()
            s.refresh(proj)
            assert proj.id is not None
            assert proj.name == "DJ Set"
            assert proj.fps == 25.0

    def test_project_default_values(self):
        """Standardwerte fuer resolution und fps werden gesetzt."""
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="Default", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)
            assert proj.resolution == "1920x1080"
            assert proj.fps == 30.0

    def test_project_repr(self):
        proj = Project(id=1, name="Test", path=".", fps=24.0)
        assert "Test" in repr(proj)
        assert "24.0" in repr(proj)


# ---------------------------------------------------------------------------
# AudioTrack-Tests
# ---------------------------------------------------------------------------

class TestAudioTrackModel:
    def _project(self, session) -> Project:
        p = Project(name="P", path=".")
        session.add(p)
        session.commit()
        session.refresh(p)
        return p

    def test_create_audio_track(self):
        eng = _make_engine()
        with Session(eng) as s:
            proj = self._project(s)
            track = AudioTrack(
                project_id=proj.id,
                file_path="/audio/mix.mp3",
                title="Mix 1",
                duration=3600.0,
                bpm=130.0,
            )
            s.add(track)
            s.commit()
            s.refresh(track)
            assert track.id is not None
            assert track.bpm == 130.0
            assert track.duration == 3600.0

    def test_audio_track_fk_violation_raises(self):
        """Fehlende project_id loest IntegrityError aus."""
        eng = _make_engine()
        with Session(eng) as s:
            track = AudioTrack(project_id=9999, file_path="/x.mp3")
            s.add(track)
            with pytest.raises(IntegrityError):
                s.commit()

    def test_audio_track_repr(self):
        t = AudioTrack(id=1, title="Mix", bpm=128.0)
        assert "Mix" in repr(t)


# ---------------------------------------------------------------------------
# VideoClip-Tests
# ---------------------------------------------------------------------------

class TestVideoClipModel:
    def _project(self, session) -> Project:
        p = Project(name="VP", path=".")
        session.add(p)
        session.commit()
        session.refresh(p)
        return p

    def test_create_video_clip(self):
        eng = _make_engine()
        with Session(eng) as s:
            proj = self._project(s)
            clip = VideoClip(
                project_id=proj.id,
                file_path="/video/clip1.mp4",
                duration=30.0,
                width=1920,
                height=1080,
                fps=30.0,
                codec="h264",
            )
            s.add(clip)
            s.commit()
            s.refresh(clip)
            assert clip.id is not None
            assert clip.codec == "h264"

    def test_video_clip_fk_violation_raises(self):
        eng = _make_engine()
        with Session(eng) as s:
            clip = VideoClip(project_id=9999, file_path="/bad.mp4")
            s.add(clip)
            with pytest.raises(IntegrityError):
                s.commit()

    def test_video_clip_repr(self):
        c = VideoClip(id=1, file_path="/clip.mp4")
        assert "/clip.mp4" in repr(c)


# ---------------------------------------------------------------------------
# Beatgrid-Tests
# ---------------------------------------------------------------------------

class TestBeatgridModel:
    def test_create_beatgrid(self):
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            track = AudioTrack(project_id=proj.id, file_path="/a.mp3")
            s.add(track)
            s.commit()
            s.refresh(track)

            bg = Beatgrid(
                audio_track_id=track.id,
                bpm=128.0,
                offset=0.0,
                beat_positions="[0.0, 0.47, 0.94]",
            )
            s.add(bg)
            s.commit()
            s.refresh(bg)
            assert bg.bpm == 128.0

    def test_beatgrid_repr(self):
        bg = Beatgrid(id=1, bpm=140.0)
        assert "140.0" in repr(bg)


# ---------------------------------------------------------------------------
# Scene-Tests
# ---------------------------------------------------------------------------

class TestSceneModel:
    def test_create_scene(self):
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            clip = VideoClip(project_id=proj.id, file_path="/v.mp4")
            s.add(clip)
            s.commit()
            s.refresh(clip)

            scene = Scene(
                video_clip_id=clip.id,
                start_time=0.0,
                end_time=5.0,
                energy=0.75,
            )
            s.add(scene)
            s.commit()
            s.refresh(scene)
            assert scene.energy == 0.75

    def test_scene_repr(self):
        scene = Scene(id=1, start_time=1.0, end_time=3.0)
        assert "1.0" in repr(scene)


# ---------------------------------------------------------------------------
# Cascade-Delete-Tests
# ---------------------------------------------------------------------------

class TestCascadeDelete:
    def test_delete_project_cascades_to_audio_tracks(self):
        """Projekt loeschen entfernt auch alle AudioTracks."""
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)
            proj_id = proj.id

            track = AudioTrack(project_id=proj_id, file_path="/a.mp3")
            s.add(track)
            s.commit()
            track_id = track.id

            # Projekt loeschen
            s.delete(proj)
            s.commit()

            # AudioTrack muss weg sein
            assert s.get(AudioTrack, track_id) is None

    def test_delete_project_cascades_to_video_clips(self):
        """Projekt loeschen entfernt auch alle VideoClips."""
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            clip = VideoClip(project_id=proj.id, file_path="/v.mp4")
            s.add(clip)
            s.commit()
            clip_id = clip.id

            s.delete(proj)
            s.commit()

            assert s.get(VideoClip, clip_id) is None

    def test_delete_video_clip_cascades_to_scenes(self):
        """VideoClip loeschen entfernt auch alle Scenes."""
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            clip = VideoClip(project_id=proj.id, file_path="/v.mp4")
            s.add(clip)
            s.commit()
            s.refresh(clip)

            scene = Scene(video_clip_id=clip.id, start_time=0.0, end_time=5.0)
            s.add(scene)
            s.commit()
            scene_id = scene.id

            s.delete(clip)
            s.commit()

            assert s.get(Scene, scene_id) is None

    def test_delete_audio_track_cascades_to_beatgrid(self):
        """AudioTrack loeschen entfernt auch das Beatgrid."""
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            track = AudioTrack(project_id=proj.id, file_path="/a.mp3")
            s.add(track)
            s.commit()
            s.refresh(track)

            bg = Beatgrid(audio_track_id=track.id, bpm=120.0, offset=0.0)
            s.add(bg)
            s.commit()
            bg_id = bg.id

            s.delete(track)
            s.commit()

            assert s.get(Beatgrid, bg_id) is None


# ---------------------------------------------------------------------------
# WaveformData-Tests
# ---------------------------------------------------------------------------

class TestWaveformDataModel:
    def test_create_waveform_data(self):
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            track = AudioTrack(project_id=proj.id, file_path="/a.mp3")
            s.add(track)
            s.commit()
            s.refresh(track)

            wd = WaveformData(
                audio_track_id=track.id,
                num_samples=1000,
                duration=30.0,
                band_low="[0.1, 0.2]",
                band_mid="[0.3, 0.4]",
                band_high="[0.5, 0.6]",
            )
            s.add(wd)
            s.commit()
            s.refresh(wd)
            assert wd.num_samples == 1000

    def test_waveform_data_repr(self):
        wd = WaveformData(id=1, num_samples=500)
        assert "500" in repr(wd)


# ---------------------------------------------------------------------------
# TimelineEntry- und ClipAnchor-Tests
# ---------------------------------------------------------------------------

class TestTimelineEntryModel:
    def test_create_timeline_entry(self):
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            entry = TimelineEntry(
                project_id=proj.id,
                track="video",
                media_id=1,
                start_time=0.0,
                end_time=5.0,
                lane=0,
            )
            s.add(entry)
            s.commit()
            s.refresh(entry)
            assert entry.track == "video"

    def test_timeline_entry_repr(self):
        e = TimelineEntry(id=1, track="audio", start_time=2.5)
        assert "audio" in repr(e)
        assert "2.5" in repr(e)

    def test_clip_anchor_cascade_from_timeline_entry(self):
        """ClipAnchor wird geloescht wenn TimelineEntry geloescht wird."""
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            entry = TimelineEntry(
                project_id=proj.id,
                track="audio",
                media_id=1,
                start_time=0.0,
                end_time=5.0,
            )
            s.add(entry)
            s.commit()
            s.refresh(entry)

            anchor = ClipAnchor(
                timeline_entry_id=entry.id,
                time_offset=1.5,
                label="Downbeat",
            )
            s.add(anchor)
            s.commit()
            anchor_id = anchor.id

            s.delete(entry)
            s.commit()

            assert s.get(ClipAnchor, anchor_id) is None


# ---------------------------------------------------------------------------
# PacingBlueprint-Tests
# ---------------------------------------------------------------------------

class TestPacingBlueprintModel:
    def test_create_pacing_blueprint(self):
        eng = _make_engine()
        with Session(eng) as s:
            proj = Project(name="P", path=".")
            s.add(proj)
            s.commit()
            s.refresh(proj)

            bp = PacingBlueprint(
                project_id=proj.id,
                name="Fast Cuts",
                style="energetic",
                cuts_per_bar=4,
            )
            s.add(bp)
            s.commit()
            s.refresh(bp)
            assert bp.cuts_per_bar == 4

    def test_pacing_blueprint_repr(self):
        bp = PacingBlueprint(id=1, name="Chill")
        assert "Chill" in repr(bp)
