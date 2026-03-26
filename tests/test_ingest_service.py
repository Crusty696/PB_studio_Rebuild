import tempfile
from pathlib import Path

from services.ingest_service import ingest_audio, ingest_video, get_all_media


def test_ingest_audio_creates_track(tmp_path, project):
    """project-Fixture stellt sicher, dass Projekt mit id=1 in In-Memory-DB existiert."""
    audio_file = tmp_path / "test_song.mp3"
    audio_file.write_bytes(b"\x00" * 100)

    track = ingest_audio(str(audio_file))
    assert track is not None
    assert track.title == "test_song"
    assert track.project_id == project.id


def test_ingest_audio_duplicate_returns_none(tmp_path, project):
    audio_file = tmp_path / "dup.wav"
    audio_file.write_bytes(b"\x00" * 100)

    first = ingest_audio(str(audio_file))
    second = ingest_audio(str(audio_file))
    assert first is not None
    assert second is None


def test_ingest_video_creates_clip(tmp_path, project):
    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"\x00" * 100)

    clip = ingest_video(str(video_file))
    assert clip is not None
    assert clip.project_id == project.id


def test_get_all_media_returns_both(tmp_path, project):
    audio = tmp_path / "song.mp3"
    audio.write_bytes(b"\x00" * 100)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00" * 100)

    ingest_audio(str(audio))
    ingest_video(str(video))

    media = get_all_media(project.id)
    assert len(media) == 2
    types = {m["type"] for m in media}
    assert types == {"Audio", "Video"}
