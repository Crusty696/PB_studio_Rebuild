"""E6 (Perf): ``repair_timeline_integrity`` holt Dauern per 2
Spalten-Queries statt ``session.get(VideoClip/AudioTrack)`` pro Row.

Paritaets-Pins auf praeparierter Test-DB mit kaputten Rows:
- Video fehlt (media_id ohne VideoClip) -> Rebuild nutzt wie vorher die
  Timeline-Duration (clip_duration=0.0-Pfad, identisch zu get->None).
- duration-Ueberhang -> geklemmt wie vorher.
- Audio fehlt / duration None -> Row bleibt unangetastet (wie vorher
  ``track and track.duration`` falsy).
- Query-Count-Beleg: genau 1 SELECT auf video_clips und 1 auf
  audio_tracks, unabhaengig von der Row-Anzahl.
"""
from sqlalchemy import event
from sqlalchemy.orm import Session as DBSession

from database.models import AudioTrack, Project, TimelineEntry, VideoClip


def _setup_broken_timeline(test_engine):
    with DBSession(test_engine) as s:
        p = Project(name="e6-repair", path="/tmp/e6-repair")
        s.add(p)
        s.flush()
        clip_a = VideoClip(
            project_id=p.id, file_path="/tmp/e6/a.mp4", duration=8.0,
        )
        track_t = AudioTrack(
            project_id=p.id, file_path="/tmp/e6/t.wav", title="T",
            duration=100.0,
        )
        track_t2 = AudioTrack(
            project_id=p.id, file_path="/tmp/e6/t2.wav", title="T2",
            duration=None,
        )
        s.add_all([clip_a, track_t, track_t2])
        s.flush()

        s.add_all([
            # 1) Zero-Span + Clip vorhanden (dur=8 < row-dur=10):
            #    Rebuild klemmt source_end auf 8, danach end_time auf 8.
            TimelineEntry(
                project_id=p.id, track="video", media_id=clip_a.id,
                start_time=0.0, end_time=10.0,
                source_start=0.0, source_end=0.0, lane=0, locked=False,
            ),
            # 2) Zero-Span + Clip FEHLT (media_id=999): clip_duration=0.0
            #    wie frueher bei session.get -> None; Rebuild nutzt die
            #    Timeline-Duration (source_end=10).
            TimelineEntry(
                project_id=p.id, track="video", media_id=999,
                start_time=10.0, end_time=20.0,
                source_start=0.0, source_end=0.0, lane=0, locked=False,
            ),
            # 3) duration-Ueberhang: span=5, row-dur=10 -> end geklemmt.
            TimelineEntry(
                project_id=p.id, track="video", media_id=clip_a.id,
                start_time=30.0, end_time=40.0,
                source_start=0.0, source_end=5.0, lane=0, locked=False,
            ),
            # a) Audio T, falsche Laenge -> synced auf 0..100.
            TimelineEntry(
                project_id=p.id, track="audio", media_id=track_t.id,
                start_time=0.0, end_time=50.0, lane=0,
            ),
            # b) Audio T Duplikat (gleiche media_id+lane) -> geloescht.
            TimelineEntry(
                project_id=p.id, track="audio", media_id=track_t.id,
                start_time=60.0, end_time=70.0, lane=0,
            ),
            # c) Audio FEHLT (media_id=888) -> unangetastet.
            TimelineEntry(
                project_id=p.id, track="audio", media_id=888,
                start_time=0.0, end_time=10.0, lane=1,
            ),
            # d) Audio T2 mit duration=None -> unangetastet.
            TimelineEntry(
                project_id=p.id, track="audio", media_id=track_t2.id,
                start_time=0.0, end_time=10.0, lane=2,
            ),
        ])
        s.commit()
        return p.id, clip_a.id, track_t.id, track_t2.id


def test_e6_repair_parity_on_broken_rows(test_engine, monkeypatch):
    import services.timeline_service as ts_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)

    pid, clip_a_id, track_t_id, track_t2_id = _setup_broken_timeline(test_engine)

    result = ts_mod.repair_timeline_integrity(pid)

    # Rueckgabewert-Paritaet (Semantik der Vor-E6-Implementierung):
    assert result == {
        "video_duration_clamped": 2,      # Rows 1 + 3
        "video_overlaps_shifted": 0,
        "video_gaps_closed": 2,           # Rows 2 + 3 (Luecken zu Row davor)
        "video_source_span_rebuilt": 2,   # Rows 1 + 2
        "audio_duplicates_removed": 1,    # Row b
        "audio_duration_synced": 1,       # Row a
    }

    with DBSession(test_engine) as s:
        video_rows = (
            s.query(TimelineEntry)
            .filter_by(project_id=pid, track="video")
            .order_by(TimelineEntry.start_time, TimelineEntry.id)
            .all()
        )
        audio_rows = (
            s.query(TimelineEntry)
            .filter_by(project_id=pid, track="audio")
            .order_by(TimelineEntry.lane, TimelineEntry.id)
            .all()
        )

    # Row 1: Rebuild auf Clip-Dauer 8 begrenzt, dann Ende geklemmt.
    assert video_rows[0].media_id == clip_a_id
    assert video_rows[0].source_end == 8.0
    assert video_rows[0].end_time == 8.0
    # Row 2 (Clip fehlt): Rebuild wie get->None-Pfad -> source_end=10,
    # Gap zu Row 1 geschlossen (start 8, end 18).
    assert video_rows[1].media_id == 999
    assert video_rows[1].source_end == 10.0
    assert (video_rows[1].start_time, video_rows[1].end_time) == (8.0, 18.0)
    # Row 3: Ueberhang auf span=5 geklemmt, Gap geschlossen (18..23).
    assert (video_rows[2].start_time, video_rows[2].end_time) == (18.0, 23.0)

    # Audio: Duplikat weg, T synced, 888 + T2 unangetastet.
    assert len(audio_rows) == 3
    assert audio_rows[0].media_id == track_t_id
    assert (audio_rows[0].start_time, audio_rows[0].end_time) == (0.0, 100.0)
    assert audio_rows[0].source_end == 100.0
    assert audio_rows[1].media_id == 888
    assert (audio_rows[1].start_time, audio_rows[1].end_time) == (0.0, 10.0)
    assert audio_rows[2].media_id == track_t2_id
    assert (audio_rows[2].start_time, audio_rows[2].end_time) == (0.0, 10.0)


def test_e6_repair_uses_two_column_queries_not_get_per_row(test_engine, monkeypatch):
    """Query-Count-Beleg: 1 SELECT auf video_clips + 1 auf audio_tracks,
    egal wie viele Timeline-Rows repariert werden (vorher: 1 pro Row)."""
    import services.timeline_service as ts_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)

    pid, _, _, _ = _setup_broken_timeline(test_engine)

    statements: list[str] = []

    @event.listens_for(test_engine, "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    try:
        ts_mod.repair_timeline_integrity(pid)
    finally:
        event.remove(test_engine, "before_cursor_execute", _count)

    video_selects = [
        st for st in statements
        if st.lstrip().upper().startswith("SELECT") and "FROM video_clips" in st
    ]
    audio_selects = [
        st for st in statements
        if st.lstrip().upper().startswith("SELECT") and "FROM audio_tracks" in st
    ]
    assert len(video_selects) == 1, (
        f"E6: erwartet genau 1 video_clips-SELECT, bekommen "
        f"{len(video_selects)}:\n" + "\n".join(video_selects)
    )
    assert len(audio_selects) == 1, (
        f"E6: erwartet genau 1 audio_tracks-SELECT, bekommen "
        f"{len(audio_selects)}:\n" + "\n".join(audio_selects)
    )
