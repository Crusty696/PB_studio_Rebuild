from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import Session

from database.models import (
    AudioTrack,
    Beatgrid,
    Project,
    Scene,
    TimelineEntry,
    VideoClip,
    WaveformData,
)


def test_b315_schnitt_context_uses_aggregate_queries(test_engine):
    from services.schnitt_context import build_schnitt_context

    with Session(test_engine) as s:
        p = Project(name="schnitt-fast", path="C:/tmp/schnitt-fast")
        s.add(p)
        s.flush()
        a = AudioTrack(
            project_id=p.id,
            file_path="song.mp3",
            title="song",
            duration=60.0,
            stem_vocals_path="vocals.wav",
        )
        s.add(a)
        s.flush()
        s.add(Beatgrid(audio_track_id=a.id, bpm=128.0, beat_positions=[0.0]))
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
        for idx in range(4):
            v = VideoClip(project_id=p.id, file_path=f"clip_{idx}.mp4", duration=10.0)
            s.add(v)
            s.flush()
            s.add(Scene(video_clip_id=v.id, start_time=0.0, end_time=1.0))
            s.add(
                TimelineEntry(
                    project_id=p.id,
                    track="video",
                    media_id=v.id,
                    start_time=float(idx),
                    end_time=float(idx + 1),
                )
            )
        s.commit()
        project_id = p.id

    select_count = 0

    def _count_select(_conn, _cursor, statement, _params, _context, _executemany):
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT"):
            select_count += 1

    event.listen(test_engine, "before_cursor_execute", _count_select)
    try:
        ctx = build_schnitt_context(test_engine, project_id)
    finally:
        event.remove(test_engine, "before_cursor_execute", _count_select)

    assert ctx.can_auto_edit is True
    assert ctx.video_ids == (1, 2, 3, 4)
    assert ctx.timeline_entry_count == 4
    assert ctx.has_video_analysis is True
    assert select_count <= 7
