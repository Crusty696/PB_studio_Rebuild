"""D11 — ToggleClipLockCommand ruft Timeline._sync_clip_lock_visual.

Tier-1 Hardening 2026-05-09 (SCHNITT Redesign).

Plan-Abweichung: test_engine + monkeypatch.setattr(uc_mod, engine, ...).
"""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sqlalchemy.orm import Session
from PySide6.QtWidgets import QApplication

from database.models import Project, TimelineEntry
from ui.undo_commands import ToggleClipLockCommand


def _qapp():
    return QApplication.instance() or QApplication([])


class _FakeTimeline:
    def __init__(self):
        self.calls: list[tuple[int, bool]] = []

    def _sync_clip_lock_visual(self, entry_id: int, locked: bool) -> None:
        self.calls.append((entry_id, locked))


def _make_entry(test_engine) -> int:
    with Session(test_engine) as s:
        p = Project(name="lock-sync", path="/tmp/lock-sync")
        s.add(p)
        s.flush()
        e = TimelineEntry(project_id=p.id, track="video", media_id=1,
                          start_time=0, end_time=2, lane=0, locked=False)
        s.add(e)
        s.commit()
        return e.id


def test_redo_triggers_visual_sync(test_engine, monkeypatch):
    _qapp()
    import ui.undo_commands as uc_mod
    monkeypatch.setattr(uc_mod, "engine", test_engine)
    eid = _make_entry(test_engine)

    fake = _FakeTimeline()
    cmd = ToggleClipLockCommand(entry_id=eid, new_locked=True, timeline=fake)
    cmd.redo()

    assert fake.calls == [(eid, True)]
    with Session(test_engine) as s:
        assert s.get(TimelineEntry, eid).locked is True


def test_undo_reverts_and_syncs(test_engine, monkeypatch):
    _qapp()
    import ui.undo_commands as uc_mod
    monkeypatch.setattr(uc_mod, "engine", test_engine)
    eid = _make_entry(test_engine)

    fake = _FakeTimeline()
    cmd = ToggleClipLockCommand(entry_id=eid, new_locked=True, timeline=fake)
    cmd.redo()
    cmd.undo()

    assert fake.calls == [(eid, True), (eid, False)]
    with Session(test_engine) as s:
        assert s.get(TimelineEntry, eid).locked is False


def test_no_timeline_keeps_old_behaviour(test_engine, monkeypatch):
    """Backwards-compat: ohne timeline-Param funktioniert alles wie bisher."""
    _qapp()
    import ui.undo_commands as uc_mod
    monkeypatch.setattr(uc_mod, "engine", test_engine)
    eid = _make_entry(test_engine)

    cmd = ToggleClipLockCommand(entry_id=eid, new_locked=True)
    cmd.redo()
    with Session(test_engine) as s:
        assert s.get(TimelineEntry, eid).locked is True
