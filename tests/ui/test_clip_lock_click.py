"""Click-Toggle fuer Lock-Icon (Phase 05 / Task 5.3).

Plan-Abweichungen:
- `test_engine`-Fixture statt `init_db()` + `DBSession(engine)`.
- `Project(name=..., path=...)` weil `path` NOT-NULL.
- `from sqlalchemy.orm import Session as DBSession` statt `database.session`.
- `monkeypatch.setattr(uc_mod, "engine", test_engine)` — ui.undo_commands haelt
  einen Modul-globalen engine-Snapshot.
- Plan-Original ruft `tl.load_from_db(pid)` und gleich danach `get_video_clip_items()`.
  Das ist mit dem QThread-Worker im Repo nicht synchron testbar (Worker laeuft im
  zweiten Thread, dort liefert `:memory:`-SQLite eine eigene leere DB pro Connection
  → "no such table"). Stattdessen wird der Clip direkt instanziert + `entry_id`
  gesetzt; getestet wird der Click-Pfad `_handle_lock_icon_click(force=True)` →
  `ToggleClipLockCommand.redo()` → DB-Persistenz. `get_video_clip_items()` wird
  zusaetzlich auf der Scene verifiziert.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy.orm import Session as DBSession
from PySide6.QtWidgets import QApplication

from database.models import Project, TimelineEntry


def _qapp():
    return QApplication.instance() or QApplication([])


def test_clicking_lock_icon_toggles_db_value(test_engine, monkeypatch):
    _qapp()

    import ui.timeline as timeline_mod
    import ui.undo_commands as uc_mod
    monkeypatch.setattr(uc_mod, "engine", test_engine)

    with DBSession(test_engine) as s:
        p = Project(name="lock-click", path="/tmp/lock-click")
        s.add(p)
        s.flush()
        entry = TimelineEntry(project_id=p.id, track="video", media_id=1,
                              start_time=0, end_time=2, lane=0, locked=False)
        s.add(entry)
        s.commit()
        pid = p.id
        eid = entry.id

    tl = timeline_mod.InteractiveTimeline()
    clip = timeline_mod.TimelineClipItem(
        entry_id=eid, media_id=1, track_type="video", title="t",
        x=0, y=0, width=200, height=40,
        anchors=[],
    )
    tl._scene.addItem(clip)

    # Helper get_video_clip_items findet den Clip
    clips = tl.get_video_clip_items()
    assert len(clips) == 1
    assert clips[0] is clip

    # Simuliere Klick auf das Lock-Icon
    clip._handle_lock_icon_click(force=True)

    with DBSession(test_engine) as s:
        assert s.query(TimelineEntry).filter_by(project_id=pid).first().locked is True
    assert clip.is_locked() is True
    assert clip.lock_icon.is_locked is True
