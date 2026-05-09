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

from sqlalchemy.orm import Session as DBSession
from PySide6.QtWidgets import QApplication

from database.models import Project, TimelineEntry
from ui.undo_commands import ToggleClipLockCommand


def _qapp():
    return QApplication.instance() or QApplication([])


def _make_entry(test_engine) -> int:
    with DBSession(test_engine) as s:
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
    with DBSession(test_engine) as s:
        assert s.get(TimelineEntry, eid).locked is True


def test_undo_reverts(test_engine, monkeypatch):
    _qapp()
    import ui.undo_commands as uc_mod
    monkeypatch.setattr(uc_mod, "engine", test_engine)
    eid = _make_entry(test_engine)
    cmd = ToggleClipLockCommand(entry_id=eid, new_locked=True)
    cmd.redo()
    cmd.undo()
    with DBSession(test_engine) as s:
        assert s.get(TimelineEntry, eid).locked is False


def test_t47_mergewith_same_clip_within_window():
    """T4.7: zwei Toggles desselben Clips innerhalb 500ms → mergen."""
    _qapp()
    a = ToggleClipLockCommand(entry_id=42, new_locked=True)
    b = ToggleClipLockCommand(entry_id=42, new_locked=False)
    assert a.id() == b.id()  # gleiche merge-ID
    assert a.mergeWith(b) is True
    # _new wurde uebernommen.
    assert a._new is False


def test_t47_mergewith_different_clip_rejected():
    _qapp()
    a = ToggleClipLockCommand(entry_id=42, new_locked=True)
    b = ToggleClipLockCommand(entry_id=43, new_locked=True)
    assert a.id() != b.id()
    assert a.mergeWith(b) is False


def test_t47_mergewith_outside_window_rejected():
    """Toggle nach >500ms wird nicht gemergt."""
    _qapp()
    a = ToggleClipLockCommand(entry_id=42, new_locked=True)
    a._created_at -= 1.0  # simuliere 1s vorher
    b = ToggleClipLockCommand(entry_id=42, new_locked=False)
    assert a.mergeWith(b) is False


def test_t47_mergewith_only_with_same_command_class():
    _qapp()
    from ui.undo_commands import MoveClipCommand
    a = ToggleClipLockCommand(entry_id=42, new_locked=True)
    # MoveClipCommand braucht timeline; reicht aus, dass isinstance-Check fehlschlaegt.
    class _Stub:
        pass
    other = MoveClipCommand.__new__(MoveClipCommand)
    other._entry_id = 42  # type: ignore[attr-defined]
    assert a.mergeWith(other) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# T5.5 Coverage-Sweep (E5)
# ---------------------------------------------------------------------------


def test_redo_with_nonexistent_entry_id_no_crash(test_engine, monkeypatch):
    """Guard-Pfad: redo() auf nicht-existente entry_id darf nicht crashen."""
    _qapp()
    import ui.undo_commands as uc_mod
    monkeypatch.setattr(uc_mod, "engine", test_engine)
    cmd = ToggleClipLockCommand(entry_id=999_999, new_locked=True)
    # Darf keinen Exception werfen — guard-clause `if e is None: return`.
    cmd.redo()
    # _old wurde nie gesetzt → undo() ist ebenfalls No-Op.
    cmd.undo()


def test_double_redo_idempotent(test_engine, monkeypatch):
    """Zweimal redo() → gleicher Endzustand. _old wird beim 2. Aufruf
    auf den 1. (bereits-True) gesetzt, was den Roundtrip via undo nicht
    perfekt macht — aber DB-Endzustand bleibt locked=True."""
    _qapp()
    import ui.undo_commands as uc_mod
    monkeypatch.setattr(uc_mod, "engine", test_engine)
    eid = _make_entry(test_engine)
    cmd = ToggleClipLockCommand(entry_id=eid, new_locked=True)
    cmd.redo()
    cmd.redo()
    with DBSession(test_engine) as s:
        assert s.get(TimelineEntry, eid).locked is True


def test_mergeWith_within_500ms():
    """T4.7 Hardening Verifikation: schnelle Toggles desselben Clips mergen."""
    _qapp()
    a = ToggleClipLockCommand(entry_id=7, new_locked=True)
    b = ToggleClipLockCommand(entry_id=7, new_locked=False)
    # b._created_at - a._created_at sollte <500ms sein direkt nach Erstellung.
    delta = b._created_at - a._created_at
    assert delta < ToggleClipLockCommand._MERGE_WINDOW_S
    assert a.mergeWith(b) is True
    assert a._new is False
