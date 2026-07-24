"""B-689: Snapshot-Restore schreibt neue TimelineEntry-Zeilen mit neuen IDs.
Der Undo-Stack haelt danach Commands auf tote entry_ids — ein Ctrl+Z wuerde den
wiederhergestellten Stand zerstoeren. Nach dem Restore muss der Undo-Stack
geleert sein.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QUndoCommand


def _qapp():
    return QApplication.instance() or QApplication([])


class _NoopCommand(QUndoCommand):
    def redo(self):
        pass

    def undo(self):
        pass


def test_restore_done_clears_undo_stack(monkeypatch):
    """B-689 (nach B-708 Variant B async): das Leeren des Undo-Stacks passiert
    im Main-Thread-Completion-Handler ``_on_restore_done`` (nach Worker-Erfolg),
    nicht mehr synchron in ``_restore_snapshot``. Getestet wird der Handler."""
    _qapp()
    import database
    from ui.workspaces.schnitt.timeline_shell import TimelineShell

    shell = TimelineShell()

    # Ein Command auf dem Stack simulieren (z.B. ein vorheriger Auto-Edit).
    shell.timeline.undo_stack.push(_NoopCommand("dummy"))
    assert shell.timeline.undo_stack.count() == 1

    monkeypatch.setattr(database, "get_active_project_id", lambda: 1)
    shell.timeline.load_from_db = lambda project_id=None: None

    shell._on_restore_done(version=3)

    assert shell.timeline.undo_stack.count() == 0, (
        "Undo-Stack nach Snapshot-Restore nicht geleert (B-689) — Ctrl+Z wuerde "
        "den wiederhergestellten Stand zerstoeren."
    )


def test_restore_snapshot_runs_async_without_blocking(monkeypatch):
    """B-708 Variant B: _restore_snapshot startet den Restore als Hintergrund-Task
    (kein synchroner DB-Call im GUI-Thread) und ist re-entrancy-geschuetzt."""
    _qapp()
    from ui.workspaces.schnitt import timeline_shell as tshell
    from ui.workspaces.schnitt.timeline_shell import TimelineShell

    shell = TimelineShell()

    started = {"n": 0, "worker": None}

    class _FakeTM:
        @staticmethod
        def instance():
            return _FakeTM()

        def start_task(self, name, worker, description="", on_finish=None, on_error=None):
            started["n"] += 1
            started["worker"] = worker
            return "task_x"

    monkeypatch.setattr("services.task_manager.GlobalTaskManager", _FakeTM)

    shell._restore_snapshot(snapshot_id=7, version=3)
    assert started["n"] == 1, "Restore wurde nicht als Hintergrund-Task gestartet"
    assert isinstance(started["worker"], tshell._SnapshotRestoreWorker)
    assert shell._restore_inflight is True

    # Re-Entrancy: zweiter Klick startet KEINEN zweiten Task.
    shell._restore_snapshot(snapshot_id=8, version=4)
    assert started["n"] == 1, "Zweiter Restore trotz laufendem gestartet (Re-Entrancy)"
