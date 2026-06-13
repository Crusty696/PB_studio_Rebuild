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
