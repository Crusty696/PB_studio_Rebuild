"""ToggleClipLockCommand Tests — SCHNITT Redesign 2026-05-09 Task 3.3.

Plan-Abweichung: nutzt `test_engine`-Fixture (siehe tests/conftest.py)
und monkeypatched `engine` in `ui.undo_commands` — analog zu den
Phase-02-Tests (test_timeline_state.py etc.). Plan-Original
verwendete `init_db()` direkt + `from database.session import DBSession`,
beides ist im Repo nicht so vorhanden bzw. wuerde die Produktions-DB
beruehren.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy.orm import Session
from PySide6.QtWidgets import QApplication

from database.models import Project, TimelineEntry
from ui.undo_commands import ToggleClipLockCommand


def _qapp():
    return QApplication.instance() or QApplication([])


def _make_entry(test_engine) -> int:
    with Session(test_engine) as s:
        p = Project(name="lock-cmd", path="/tmp/lock-cmd")
        s.add(p)
        s.flush()
        e = TimelineEntry(project_id=p.id, track="video", media_id=1,
                          start_time=0, end_time=2, lane=0, locked=False)
        s.add(e)
        s.commit()
        return e.id


def test_redo_sets_locked_true(test_engine, monkeypatch):
    _qapp()
    import ui.undo_commands as uc_mod
    monkeypatch.setattr(uc_mod, "engine", test_engine)
    eid = _make_entry(test_engine)
    cmd = ToggleClipLockCommand(entry_id=eid, new_locked=True)
    cmd.redo()
    with Session(test_engine) as s:
        assert s.get(TimelineEntry, eid).locked is True


def test_undo_reverts(test_engine, monkeypatch):
    _qapp()
    import ui.undo_commands as uc_mod
    monkeypatch.setattr(uc_mod, "engine", test_engine)
    eid = _make_entry(test_engine)
    cmd = ToggleClipLockCommand(entry_id=eid, new_locked=True)
    cmd.redo()
    cmd.undo()
    with Session(test_engine) as s:
        assert s.get(TimelineEntry, eid).locked is False
