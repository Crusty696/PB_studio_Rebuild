"""B-653: ueberlappende Video-Clips auf einer Lane (unsichtbare 2. Schicht).

Fixes:
1. Peer-Overlap-Klemme in apply_auto_edit_segments (Persistenz-Invariante).
2. resolve_video_overlaps: schiebt Kollisionen nach rechts, laesst Luecken
   (anders als repair_timeline_integrity, das Gaps schliesst) — laeuft nach
   manuellem Add (edit_actions, AddClipCommand).
3. Overlap-Warnung beim Timeline-Load (Source-Pin).
4. source_start >= 0 Klemme (DB-Beweis: -3.626 durch Trim-Links).
"""
from __future__ import annotations

import inspect

from sqlalchemy.orm import Session as DBSession

from database.models import Project, TimelineEntry


def _mk_project(test_engine, name: str) -> int:
    with DBSession(test_engine) as s:
        p = Project(name=name, path=f"/tmp/{name}")
        s.add(p)
        s.commit()
        return p.id


def test_resolve_video_overlaps_shifts_but_keeps_gaps(test_engine):
    from services.timeline_service import resolve_video_overlaps

    pid = _mk_project(test_engine, "b653-resolve")
    with DBSession(test_engine) as s:
        s.add_all([
            TimelineEntry(project_id=pid, track="video", media_id=1,
                          start_time=0.0, end_time=4.0, lane=0),
            # ueberlappt den ersten komplett teilweise
            TimelineEntry(project_id=pid, track="video", media_id=2,
                          start_time=2.0, end_time=5.0, lane=0),
            # bewusste Luecke (5..10) — MUSS erhalten bleiben
            TimelineEntry(project_id=pid, track="video", media_id=3,
                          start_time=10.0, end_time=12.0, lane=0),
        ])
        s.commit()

    shifted = resolve_video_overlaps(pid)
    assert shifted == 1

    with DBSession(test_engine) as s:
        rows = (s.query(TimelineEntry)
                .filter_by(project_id=pid, track="video")
                .order_by(TimelineEntry.start_time).all())
        spans = [(r.media_id, r.start_time, r.end_time) for r in rows]
    # Clip 2 wurde hinter Clip 1 geschoben (4..7), Luecke vor Clip 3 bleibt
    assert spans[0] == (1, 0.0, 4.0)
    assert spans[1] == (2, 4.0, 7.0)
    assert spans[2] == (3, 10.0, 12.0)
    # Invariante: keine Ueberlappungen mehr
    for (_, s1, e1), (_, s2, _e2) in zip(spans, spans[1:]):
        assert s2 >= e1 - 1e-6


def test_resolve_video_overlaps_respects_locked(test_engine):
    from services.timeline_service import resolve_video_overlaps

    pid = _mk_project(test_engine, "b653-locked")
    with DBSession(test_engine) as s:
        s.add_all([
            TimelineEntry(project_id=pid, track="video", media_id=1,
                          start_time=0.0, end_time=4.0, lane=0),
            TimelineEntry(project_id=pid, track="video", media_id=2,
                          start_time=2.0, end_time=5.0, lane=0, locked=True),
        ])
        s.commit()

    assert resolve_video_overlaps(pid) == 0  # locked wird nicht angefasst
    with DBSession(test_engine) as s:
        row = (s.query(TimelineEntry)
               .filter_by(project_id=pid, media_id=2).one())
        assert row.start_time == 2.0


def test_apply_segments_clamps_peer_overlap(test_engine, monkeypatch):
    import services.timeline_service as ts_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)

    pid = _mk_project(test_engine, "b653-apply")
    segments = [
        {"media_id": 1, "start": 0.0, "end": 5.0, "lane": 0,
         "source_start": 0.0, "source_end": 5.0},
        # fehlerhafte Eingabe: ueberlappt den Vorgaenger um 2s
        {"media_id": 2, "start": 3.0, "end": 8.0, "lane": 0,
         "source_start": 0.0, "source_end": 5.0},
    ]
    ts_mod.apply_auto_edit_segments(segments, project_id=pid)

    with DBSession(test_engine) as s:
        rows = (s.query(TimelineEntry)
                .filter_by(project_id=pid, track="video")
                .order_by(TimelineEntry.start_time).all())
        spans = [(r.media_id, r.start_time, r.end_time, r.source_start) for r in rows]
    assert spans[0][:3] == (1, 0.0, 5.0)
    # Segment 2: Start auf 5.0 geklemmt, Quellfenster um 2s mitverschoben
    assert spans[1][1] == 5.0
    assert spans[1][3] == 2.0
    for (_, s1, e1, _), (_, s2, _e2, _) in zip(spans, spans[1:]):
        assert s2 >= e1 - 1e-6


def test_manual_add_paths_run_resolver_pin():
    import services.actions.edit_actions as ea
    import ui.undo_commands as uc

    assert "resolve_video_overlaps" in inspect.getsource(ea), (
        "B-653: add_to_timeline muss den Overlap-Resolver rufen")
    assert "resolve_video_overlaps" in inspect.getsource(uc.AddClipCommand.redo), (
        "B-653: Drag-Add (AddClipCommand) muss den Overlap-Resolver rufen")


def test_timeline_load_warns_on_overlaps_pin():
    import ui.timeline as tl
    src = inspect.getsource(tl.InteractiveTimeline._on_db_load_finished)
    assert "UEBERLAPPUNG" in src or "ueberlappende" in src, (
        "B-653: Load muss Ueberlappungen laut melden statt still zu stapeln")


def test_trim_clamps_negative_source_start_pin():
    import ui.undo_commands as uc
    src = inspect.getsource(uc.TrimClipCommand._apply)
    assert "max(0.0, source_start)" in src, (
        "B-653: source_start darf nie negativ persistiert werden")
