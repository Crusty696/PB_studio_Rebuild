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
