"""Phase 06 / Task 6.2: Lock-aware ``apply_auto_edit_segments``.

Verifiziert SCHNITT-Redesign Risiko #3: Beim erneuten Auto-Edit duerfen
gelockte Video-Clips weder geloescht noch durch neue Segmente ueberlagert
werden. Neue Segmente, die in eine Locked-Range hineinragen, werden auf
die Locked-Boundaries geklemmt oder verworfen.

Plan-Abweichungen (Standard für SCHNITT-Redesign 2026-05-09):
- ``DBSession`` -> ``from sqlalchemy.orm import Session as DBSession``
- ``init_db`` weg, dafuer ``test_engine``-Fixture + monkeypatch.setattr.
- ``Project(name=..., path=...)`` weil ``path`` NOT-NULL.
"""
import pytest
from sqlalchemy.orm import Session as DBSession

from database.models import Project, TimelineEntry


def test_locked_clip_preserved_unchanged(test_engine, monkeypatch):
    # Service-Modul lazy importieren, damit der monkeypatch.setattr greift.
    import services.timeline_service as ts_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)

    with DBSession(test_engine) as s:
        p = Project(name="lock-apply", path="/tmp/lock-apply")
        s.add(p)
        s.flush()
        # Locked Clip bei [10..14]
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=1,
            start_time=10.0, end_time=14.0, lane=0, locked=True,
        ))
        # Ungelockt — wird beim Auto-Edit geloescht
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=2,
            start_time=0.0, end_time=2.0, lane=0, locked=False,
        ))
        s.commit()
        pid = p.id

    new_segments = [
        # Vor der Locked-Range — bleibt komplett bestehen
        {"media_id": 99, "start": 0.0, "end": 5.0, "lane": 0,
         "source_start": 0.0, "source_end": 5.0,
         "crossfade_duration": 0.0, "brightness": 0.0, "contrast": 1.0},
        # Ragt in die Locked-Range hinein -> muss auf 10.0 geklemmt werden
        {"media_id": 100, "start": 5.0, "end": 12.0, "lane": 0,
         "source_start": 0.0, "source_end": 7.0,
         "crossfade_duration": 0.0, "brightness": 0.0, "contrast": 1.0},
        # Nach der Locked-Range — bleibt komplett bestehen
        {"media_id": 101, "start": 14.0, "end": 20.0, "lane": 0,
         "source_start": 0.0, "source_end": 6.0,
         "crossfade_duration": 0.0, "brightness": 0.0, "contrast": 1.0},
    ]

    ts_mod.apply_auto_edit_segments(new_segments, pid)

    with DBSession(test_engine) as s:
        rows = (
            s.query(TimelineEntry)
            .filter_by(project_id=pid, track="video")
            .order_by(TimelineEntry.start_time)
            .all()
        )

    # Locked-Range [10..14] muss exakt erhalten sein
    locked_rows = [r for r in rows if r.locked]
    assert len(locked_rows) == 1
    assert locked_rows[0].media_id == 1
    assert locked_rows[0].start_time == 10.0
    assert locked_rows[0].end_time == 14.0

    unlocked = [r for r in rows if not r.locked]
    # Vor + geklemmt + nach = 3 Segmente erwartet
    assert len(unlocked) == 3

    # Kein unlocked-Segment darf in die Locked-Range [10..14] hineinragen
    for r in unlocked:
        overlap = (r.start_time < 14.0) and (r.end_time > 10.0)
        assert not overlap, (
            f"Segment media_id={r.media_id} [{r.start_time}..{r.end_time}] "
            f"ueberlappt Locked-Range [10..14]"
        )

    # Mittleres Segment (media_id=100) muss bei 10.0 geklemmt sein
    clamped = [r for r in unlocked if r.media_id == 100]
    assert len(clamped) == 1
    assert clamped[0].start_time == 5.0
    assert clamped[0].end_time == 10.0


# ---------------------------------------------------------------------------
# T5.6 Coverage-Sweep (E6) — parametrisiert
# ---------------------------------------------------------------------------


def _seg(media_id: int, start: float, end: float) -> dict:
    return {
        "media_id": media_id, "start": start, "end": end, "lane": 0,
        "source_start": 0.0, "source_end": end - start,
        "crossfade_duration": 0.0, "brightness": 0.0, "contrast": 1.0,
    }


def _setup_project_with_lock(test_engine, lock_range=(10.0, 14.0)):
    with DBSession(test_engine) as s:
        p = Project(name=f"clamp-{lock_range[0]}-{lock_range[1]}",
                    path=f"/tmp/clamp-{lock_range[0]}")
        s.add(p)
        s.flush()
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=1,
            start_time=lock_range[0], end_time=lock_range[1], lane=0, locked=True,
        ))
        s.commit()
        return p.id


@pytest.mark.parametrize("seg_start,seg_end,expected_kept", [
    # 1) Segment vollstaendig innerhalb der Locked-Range -> verworfen
    (11.0, 13.0, False),
    # 2) Links klemmen: rechte Kante ragt in Locked, links draussen
    #    seg=[5,12], lock=[10,14] -> seg_end auf 10 geklemmt -> Kept
    (5.0, 12.0, True),
    # 3) Rechts klemmen: linke Kante in Locked, rechts draussen
    #    seg=[12,18], lock=[10,14] -> seg_start auf 14 geklemmt -> Kept
    (12.0, 18.0, True),
    # 4) Umschliesst: seg=[5,20], lock=[10,14] -> seg_end auf 10 geklemmt -> Kept
    (5.0, 20.0, True),
])
def test_clamping_cases(test_engine, monkeypatch, seg_start, seg_end, expected_kept):
    import services.timeline_service as ts_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)
    pid = _setup_project_with_lock(test_engine, (10.0, 14.0))

    ts_mod.apply_auto_edit_segments([_seg(99, seg_start, seg_end)], pid)

    with DBSession(test_engine) as s:
        unlocked = (
            s.query(TimelineEntry)
            .filter_by(project_id=pid, track="video", locked=False)
            .all()
        )
    if expected_kept:
        assert len(unlocked) == 1
        # Verifiziere: kein unlocked-Segment ueberlappt Locked-Range
        for r in unlocked:
            assert not (r.start_time < 14.0 and r.end_time > 10.0) or \
                   r.end_time <= 10.0 or r.start_time >= 14.0
    else:
        assert len(unlocked) == 0


def test_threshold_edge_segment_too_thin(test_engine, monkeypatch):
    """`seg_end - seg_start <= 1e-3` → Segment wird verworfen."""
    import services.timeline_service as ts_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)
    with DBSession(test_engine) as s:
        p = Project(name="thin-seg", path="/tmp/thin-seg")
        s.add(p); s.commit()
        pid = p.id

    # Segment-Laenge = 0.0005 (<1e-3)
    ts_mod.apply_auto_edit_segments([_seg(42, 1.0, 1.0005)], pid)

    with DBSession(test_engine) as s:
        rows = s.query(TimelineEntry).filter_by(project_id=pid).all()
    assert len(rows) == 0


@pytest.mark.parametrize("n_locks", [0, 1, 2, 3])
def test_multiple_locked_ranges(test_engine, monkeypatch, n_locks):
    """Mit 0..3 Locked-Ranges; alle Locks bleiben erhalten, einfaches Segment ausserhalb."""
    import services.timeline_service as ts_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)
    with DBSession(test_engine) as s:
        p = Project(name=f"locks-{n_locks}", path=f"/tmp/locks-{n_locks}")
        s.add(p); s.flush()
        # Locks an [10..12], [20..22], [30..32] (je nach n)
        ranges = [(10.0, 12.0), (20.0, 22.0), (30.0, 32.0)][:n_locks]
        for i, (a, b) in enumerate(ranges):
            s.add(TimelineEntry(
                project_id=p.id, track="video", media_id=100 + i,
                start_time=a, end_time=b, lane=0, locked=True,
            ))
        s.commit()
        pid = p.id

    # Neues Segment ausserhalb aller Locks -> bleibt erhalten
    ts_mod.apply_auto_edit_segments([_seg(99, 0.0, 5.0)], pid)

    with DBSession(test_engine) as s:
        locked = s.query(TimelineEntry).filter_by(project_id=pid, locked=True).all()
        unlocked = s.query(TimelineEntry).filter_by(project_id=pid, locked=False).all()
    assert len(locked) == n_locks
    assert len(unlocked) == 1


def test_zero_locks_regression(test_engine, monkeypatch):
    """Ohne Locks bleibt der alte Pfad erhalten — neue Segmente werden 1:1 inserted."""
    import services.timeline_service as ts_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)
    with DBSession(test_engine) as s:
        p = Project(name="no-locks", path="/tmp/no-locks")
        s.add(p)
        # Existierender ungelockter Eintrag → wird beim apply geloescht
        s.flush()
        s.add(TimelineEntry(
            project_id=p.id, track="video", media_id=1,
            start_time=0.0, end_time=2.0, lane=0, locked=False,
        ))
        s.commit()
        pid = p.id

    ts_mod.apply_auto_edit_segments([
        _seg(11, 0.0, 5.0), _seg(12, 5.0, 10.0),
    ], pid)

    with DBSession(test_engine) as s:
        rows = s.query(TimelineEntry).filter_by(project_id=pid).order_by(TimelineEntry.start_time).all()
    assert len(rows) == 2
    assert rows[0].media_id == 11 and rows[0].start_time == 0.0 and rows[0].end_time == 5.0
    assert rows[1].media_id == 12 and rows[1].start_time == 5.0 and rows[1].end_time == 10.0


def test_backward_compat_video_id_field(test_engine, monkeypatch):
    """Legacy seg['video_id'] funktioniert weiter (alter Auto-Edit-Worker)."""
    import services.timeline_service as ts_mod
    monkeypatch.setattr(ts_mod, "engine", test_engine)
    with DBSession(test_engine) as s:
        p = Project(name="legacy", path="/tmp/legacy")
        s.add(p); s.commit()
        pid = p.id

    legacy_seg = {
        "video_id": 77, "start": 0.0, "end": 3.0, "lane": 0,
        "source_start": 0.0, "source_end": 3.0,
        "crossfade_duration": 0.0, "brightness": 0.0, "contrast": 1.0,
    }
    ts_mod.apply_auto_edit_segments([legacy_seg], pid)

    with DBSession(test_engine) as s:
        rows = s.query(TimelineEntry).filter_by(project_id=pid).all()
    assert len(rows) == 1
    assert rows[0].media_id == 77
