from sqlalchemy.orm import Session

from database.models import (
    AudioTrack,
    Beatgrid,
    Project,
    TimelineEntry,
    VideoClip,
    WaveformData,
)


def test_context_empty_project(test_engine):
    from services.schnitt_context import build_schnitt_context

    with Session(test_engine) as s:
        p = Project(name="schnitt-empty", path="C:/tmp/schnitt-empty")
        s.add(p)
        s.commit()
        pid = p.id

    ctx = build_schnitt_context(test_engine, pid)

    assert ctx.project_id == pid
    assert ctx.audio_id is None
    assert ctx.video_ids == ()
    assert ctx.timeline_entry_count == 0
    assert ctx.has_stems is False
    assert ctx.has_waveform is False
    assert ctx.has_beatgrid is False
    assert ctx.can_auto_edit is False
    assert "Audio fehlt" in ctx.missing_reasons
    assert "Video fehlt" in ctx.missing_reasons


def test_context_with_audio_video_and_beatgrid(test_engine):
    from services.schnitt_context import build_schnitt_context

    with Session(test_engine) as s:
        p = Project(name="schnitt-ready", path="C:/tmp/schnitt-ready")
        s.add(p)
        s.flush()
        a = AudioTrack(
            project_id=p.id,
            file_path="song.mp3",
            title="song",
            duration=60.0,
            stem_vocals_path="vocals.wav",
            stem_drums_path="drums.wav",
        )
        v = VideoClip(project_id=p.id, file_path="clip.mp4", duration=10.0)
        s.add_all([a, v])
        s.flush()
        s.add(Beatgrid(audio_track_id=a.id, bpm=128.0, beat_positions=[0.0, 1.0, 2.0]))
        s.add(
            WaveformData(
                audio_track_id=a.id,
                num_samples=1,
                duration=60.0,
                band_low=[0.1],
                band_mid=[0.2],
                band_high=[0.3],
            )
        )
        s.add(
            TimelineEntry(
                project_id=p.id,
                track="video",
                media_id=v.id,
                start_time=0.0,
                end_time=10.0,
            )
        )
        s.commit()
        pid = p.id
        audio_id = a.id
        video_id = v.id

    ctx = build_schnitt_context(test_engine, pid)

    assert ctx.audio_id == audio_id
    assert ctx.video_ids == (video_id,)
    assert ctx.has_stems is True
    assert ctx.has_beatgrid is True
    assert ctx.has_waveform is True
    assert ctx.timeline_entry_count == 1
    assert ctx.can_auto_edit is True
    assert ctx.missing_reasons == ()


def test_context_none_project_is_disabled(test_engine):
    from services.schnitt_context import build_schnitt_context

    ctx = build_schnitt_context(test_engine, None)

    assert ctx.project_id is None
    assert ctx.can_auto_edit is False
    assert ctx.missing_reasons == ("Projekt fehlt",)
