"""Tests mit echten Dateien aus C:/Users/david/Documents/test_data.

Nutzt eine temporaere SQLite-DB pro Test-Session um File-Lock-Probleme
auf Windows zu vermeiden.
"""

import os
import sys
import json
import subprocess
import tempfile
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

TEST_DATA = Path("C:/Users/david/Documents/test_data")
AUDIO_DIR = TEST_DATA / "audio"
VIDEO_DIR = TEST_DATA / "video"

AUDIO_MP3 = AUDIO_DIR / "Crusty_Progressive Psy Set2.mp3"
AUDIO_WAV = AUDIO_DIR / "Crusty -Klangkraft-21nai2022-002.wav"
AUDIO_M4A = AUDIO_DIR / "Podcast-04.m4a"
VIDEO_MP4 = VIDEO_DIR / "generation 4" / "20250612_2109_Neon_Forest_Rave_gen_01jxjzjy17ez3t5v8ca6dbka6a.mp4"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path):
    """Patcht die Engine auf eine temp-DB fuer jeden Test."""
    import database
    from sqlalchemy import create_engine

    db_path = tmp_path / "test.db"
    test_engine = create_engine(f"sqlite:///{db_path}", echo=False)

    # Engine in allen Modulen ersetzen
    original_engine = database.engine
    database.engine = test_engine

    # Services nutzen auch database.engine - Module neu patchen
    import services.ingest_service as ingest_mod
    import services.audio_service as audio_mod
    import services.video_service as video_mod
    import services.pacing_service as pacing_mod
    ingest_mod.engine = test_engine
    audio_mod.engine = test_engine
    video_mod.engine = test_engine
    pacing_mod.engine = test_engine

    # Tabellen erstellen + Default-Projekt
    database.Base.metadata.create_all(test_engine)
    from sqlalchemy.orm import Session
    with Session(test_engine) as s:
        s.add(database.Project(name="Test", path=".", resolution="1920x1080", fps=30.0))
        s.commit()

    yield test_engine

    # Restore
    database.engine = original_engine
    ingest_mod.engine = original_engine
    audio_mod.engine = original_engine
    video_mod.engine = original_engine
    pacing_mod.engine = original_engine
    test_engine.dispose()


class TestAudioIngest:
    def test_ingest_mp3(self):
        from services.ingest_service import ingest_audio
        track = ingest_audio(str(AUDIO_MP3))
        assert track is not None
        assert track.id > 0
        assert "Crusty_Progressive" in track.title

    def test_ingest_wav(self):
        from services.ingest_service import ingest_audio
        track = ingest_audio(str(AUDIO_WAV))
        assert track is not None
        assert track.id > 0

    def test_ingest_m4a(self):
        from services.ingest_service import ingest_audio
        track = ingest_audio(str(AUDIO_M4A))
        assert track is not None
        assert "Podcast" in track.title

    def test_duplicate_rejected(self):
        from services.ingest_service import ingest_audio
        t1 = ingest_audio(str(AUDIO_MP3))
        t2 = ingest_audio(str(AUDIO_MP3))
        assert t1 is not None
        assert t2 is None


class TestVideoIngest:
    def test_ingest_mp4(self):
        from services.ingest_service import ingest_video
        clip = ingest_video(str(VIDEO_MP4))
        assert clip is not None
        assert clip.id > 0

    def test_duplicate_rejected(self):
        from services.ingest_service import ingest_video
        c1 = ingest_video(str(VIDEO_MP4))
        c2 = ingest_video(str(VIDEO_MP4))
        assert c1 is not None
        assert c2 is None


class TestAudioAnalysis:
    def test_bpm_detection(self, fresh_db):
        """BPM-Erkennung mit echtem Psy-Trance Track."""
        from services.ingest_service import ingest_audio
        from services.audio_service import AudioAnalyzer
        from sqlalchemy.orm import Session
        from database import AudioTrack

        track = ingest_audio(str(AUDIO_MP3))
        analyzer = AudioAnalyzer()
        result = analyzer.analyze_and_store(track.id)

        assert "bpm" in result
        assert 80 < result["bpm"] < 200
        assert result["duration"] > 60
        assert len(result["energy_curve"]) > 10
        assert len(result["beat_positions"]) > 50

        with Session(fresh_db) as s:
            t = s.get(AudioTrack, track.id)
            assert t.bpm == result["bpm"]
            assert t.duration == result["duration"]
            assert t.beatgrid is not None
            assert t.beatgrid.bpm == result["bpm"]

    def test_scalar_conversion(self, fresh_db):
        """BPM wird als float gespeichert, nicht ndarray."""
        from services.ingest_service import ingest_audio
        from services.audio_service import AudioAnalyzer
        from sqlalchemy.orm import Session
        from database import AudioTrack

        track = ingest_audio(str(AUDIO_MP3))
        analyzer = AudioAnalyzer()
        result = analyzer.analyze_and_store(track.id)

        assert isinstance(result["bpm"], float)

        with Session(fresh_db) as s:
            t = s.get(AudioTrack, track.id)
            assert isinstance(t.bpm, float)


class TestVideoAnalysis:
    def test_probe_metadata(self):
        from services.video_service import VideoAnalyzer
        va = VideoAnalyzer()
        info = va.probe(str(VIDEO_MP4))

        assert info["width"] > 0
        assert info["height"] > 0
        assert info["fps"] > 0
        assert info["codec"] in ("h264", "h265", "hevc", "vp9", "av1")
        assert info["duration"] > 0

    def test_analyze_and_store(self, fresh_db):
        from services.ingest_service import ingest_video
        from services.video_service import VideoAnalyzer
        from sqlalchemy.orm import Session
        from database import VideoClip

        clip = ingest_video(str(VIDEO_MP4))
        va = VideoAnalyzer()
        info = va.analyze_and_store(clip.id, create_proxy=False)

        with Session(fresh_db) as s:
            c = s.get(VideoClip, clip.id)
            assert c.width == info["width"]
            assert c.height == info["height"]
            assert c.fps == info["fps"]
            assert c.duration == info["duration"]
            assert c.codec == info["codec"]


class TestTimeline:
    def test_add_and_persist(self, fresh_db):
        from services.ingest_service import ingest_audio, ingest_video
        from services.video_service import VideoAnalyzer
        from sqlalchemy.orm import Session
        from database import VideoClip, TimelineEntry

        audio = ingest_audio(str(AUDIO_MP3))
        video = ingest_video(str(VIDEO_MP4))

        va = VideoAnalyzer()
        va.analyze_and_store(video.id, create_proxy=False)

        with Session(fresh_db) as s:
            clip = s.get(VideoClip, video.id)
            vid_dur = clip.duration

            e1 = TimelineEntry(project_id=1, track="audio", media_id=audio.id,
                               start_time=0.0, end_time=30.0, lane=0)
            e2 = TimelineEntry(project_id=1, track="video", media_id=video.id,
                               start_time=0.0, end_time=vid_dur, lane=0)
            s.add_all([e1, e2])
            s.commit()

            entries = s.query(TimelineEntry).filter_by(project_id=1).all()
            assert len(entries) == 2

    def test_move_clip(self, fresh_db):
        from sqlalchemy.orm import Session
        from database import TimelineEntry

        with Session(fresh_db) as s:
            entry = TimelineEntry(project_id=1, track="video", media_id=1,
                                  start_time=0.0, end_time=10.0, lane=0)
            s.add(entry)
            s.commit()
            eid = entry.id

            entry = s.get(TimelineEntry, eid)
            entry.start_time = 5.0
            entry.end_time = 15.0
            s.commit()

            moved = s.get(TimelineEntry, eid)
            assert moved.start_time == 5.0
            assert moved.end_time == 15.0


class TestExport:
    def test_export_creates_file(self, fresh_db):
        """Exportiert echte Video-Clips zu einer .mp4-Datei."""
        from services.ingest_service import ingest_video
        from services.video_service import VideoAnalyzer
        from services.export_service import EXPORT_DIR
        from sqlalchemy.orm import Session
        from database import VideoClip, TimelineEntry

        video_files = sorted((VIDEO_DIR / "generation 4").glob("*.mp4"))[:3]
        va = VideoAnalyzer()
        clip_ids = []
        for vf in video_files:
            clip = ingest_video(str(vf))
            if clip:
                va.analyze_and_store(clip.id, create_proxy=False)
                clip_ids.append(clip.id)

        assert len(clip_ids) >= 2

        # Timeline-Eintraege
        start = 0.0
        video_paths = []
        with Session(fresh_db) as s:
            for cid in clip_ids:
                clip = s.get(VideoClip, cid)
                dur = clip.duration or 10.0
                entry = TimelineEntry(project_id=1, track="video", media_id=cid,
                                      start_time=start, end_time=start + dur, lane=0)
                s.add(entry)
                video_paths.append(clip.file_path)
                start += dur
            s.commit()

        # FFmpeg-Export direkt (umgeht Session-Isolation)
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = EXPORT_DIR / "test_export.mp4"

        concat_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="pb_test_"
        )
        for p in video_paths:
            concat_file.write(f"file '{p}'\n")
        concat_file.close()

        try:
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_file.name,
                "-vf", "scale=854:480:force_original_aspect_ratio=decrease,"
                       "pad=854:480:(ow-iw)/2:(oh-ih)/2,setsar=1",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "32",
                "-an", str(output_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            assert result.returncode == 0, f"FFmpeg failed: {result.stderr[-300:]}"
        finally:
            Path(concat_file.name).unlink(missing_ok=True)

        assert output_path.exists()
        assert output_path.stat().st_size > 10000
