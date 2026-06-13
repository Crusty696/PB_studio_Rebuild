"""B-529: Clip-Drag-Moves landen im Undo-Stack.

Regression: mouseReleaseEvent loeschte den Item-Drag-Cache (_drag_start_x/
_drag_duration) SOFORT, der 200ms-Debounce _flush_pending_moves feuerte aber
erst nach dem Release -> las None -> "No cached drag data, skipping" -> es wurde
KEIN MoveClipCommand gepusht. Folge: Strg+Z entfernte stattdessen die
vorherige Clip-Hinzufuegung. Fix: Drag-Start/Dauer werden zur Move-Zeit in
_pending_moves festgehalten, unabhaengig vom spaeter geleerten Item-Cache.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

from sqlalchemy.orm import Session as DBSession
from PySide6.QtWidgets import QApplication

from database.models import Project, TimelineEntry


def _qapp():
    return QApplication.instance() or QApplication([])


def test_clip_move_survives_release_clear_and_pushes_undo(test_engine, monkeypatch):
    app = _qapp()
    import ui.undo_commands as uc_mod
    from ui.timeline import InteractiveTimeline, PIXELS_PER_SECOND

    monkeypatch.setattr(uc_mod, "engine", test_engine)

    with DBSession(test_engine) as s:
        p = Project(name="b529", path="/tmp/b529")
        s.add(p)
        s.flush()
        e = TimelineEntry(
            project_id=p.id, track="video", media_id=1,
            start_time=0.0, end_time=2.0, lane=0,
        )
        s.add(e)
        s.commit()
        eid = e.id

    tl = InteractiveTimeline()
    try:
        # Fake-Clip-Item mit gueltigem Drag-Cache (wie waehrend eines echten Drags,
        # nachdem itemChange/ItemPositionChange die Werte gesetzt hat).
        item = SimpleNamespace(
            entry_id=eid, _drag_start_x=0.0, _drag_duration=2.0,
            _track_y=0.0, setPos=lambda *a, **k: None,
        )
        tl.clip_items.append(item)

        # Drag: Clip nach rechts ziehen.
        new_x = 5.0 * PIXELS_PER_SECOND
        tl._on_clip_moved(eid, new_x)

        # mouseReleaseEvent loescht den Item-Cache VOR dem Debounce-Flush.
        item._drag_start_x = None
        item._drag_duration = None

        # Debounce feuert (nach dem Release).
        tl._flush_pending_moves()
        app.processEvents()

        # B-529: Move-Command wurde gepusht (frueher: skip wegen geleertem Cache).
        assert tl.undo_stack.count() == 1
        with DBSession(test_engine) as s:
            moved = s.get(TimelineEntry, eid)
            assert moved.start_time > 0.0, "Clip-Move wurde nicht in die DB geschrieben"
    finally:
        tl.deleteLater()
        app.processEvents()


def test_b529_real_clip_item_move_undo_roundtrip(
    test_engine, db_session, project, video_clip, monkeypatch
):
    """Voller Real-Code-Roundtrip mit ECHTEM TimelineClipItem (kein Fake):
    setPos -> echtes itemChange -> on_moved -> Release loescht Cache ->
    _flush_pending_moves -> MoveClipCommand -> DB-Start verschoben; Strg+Z
    (undo_stack.undo) -> DB-Start zurueck auf Original, Clip bleibt erhalten.
    """
    app = _qapp()
    import database
    import ui.timeline as timeline_mod
    import ui.undo_commands as uc_mod
    from ui.timeline import InteractiveTimeline, PIXELS_PER_SECOND

    monkeypatch.setattr(timeline_mod, "nullpool_session", database.nullpool_session)
    monkeypatch.setattr(uc_mod, "engine", test_engine)

    entry = TimelineEntry(
        project_id=project.id, track="video", media_id=video_clip.id,
        start_time=0.0, end_time=10.0,
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)
    eid = entry.id

    tl = InteractiveTimeline()
    try:
        # Echtes Clip-Item synchron bauen (wie _on_db_load_finished).
        tl._brain_v3_timeline_meta = {}
        tl._anchor_map = {}
        tl._build_entries([entry], {}, {video_clip.id: video_clip}, {})
        item = tl._find_clip_item(eid)
        assert item is not None
        assert item.pos().x() == 0.0  # Start 0.0 -> x 0

        # ECHTER Drag: setPos triggert itemChange (ItemPositionChange setzt
        # _drag_start_x; ItemPositionHasChanged ruft on_moved=_on_clip_moved).
        new_x = 6.0 * PIXELS_PER_SECOND
        item.setPos(new_x, item._track_y)
        app.processEvents()

        # mouseReleaseEvent loescht den Item-Cache VOR dem Debounce-Flush (Race).
        item._drag_start_x = None
        item._drag_duration = None

        # Debounce-Flush (nach Release).
        tl._flush_pending_moves()
        app.processEvents()

        # Move im Undo-Stack + DB-Start verschoben.
        assert tl.undo_stack.count() == 1
        with database.nullpool_session() as s:
            assert s.get(TimelineEntry, eid).start_time > 0.0

        # Strg+Z: Move wird rueckgaengig gemacht -> Start zurueck auf 0.0,
        # Clip bleibt erhalten (NICHT entfernt).
        tl.undo_stack.undo()
        app.processEvents()
        with database.nullpool_session() as s:
            row = s.get(TimelineEntry, eid)
            assert row is not None, "Clip wurde durch Undo entfernt (B-529-Regression)"
            assert abs(row.start_time) < 1e-6, f"Undo hat Move nicht revertiert: start={row.start_time}"
        assert tl._find_clip_item(eid) is not None
    finally:
        # Test-Isolation: Timeline-Worker/Timer stoppen + Event-Loop drainen,
        # damit kein Hintergrund-Job in timing-sensitive Folgetests laeuft.
        import time as _t
        try:
            tl._cancel_pending_db_load()
        except Exception:
            pass
        tl.deleteLater()
        for _ in range(10):
            app.processEvents(); _t.sleep(0.02)
