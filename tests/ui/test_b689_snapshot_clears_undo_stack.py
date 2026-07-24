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


def test_restore_snapshot_clears_undo_stack(monkeypatch):
    _qapp()
    import database
    import services.timeline_snapshot_service as tss
    from ui.workspaces.schnitt.timeline_shell import TimelineShell

    shell = TimelineShell()

    # Ein Command auf dem Stack simulieren (z.B. ein vorheriger Auto-Edit).
    shell.timeline.undo_stack.push(_NoopCommand("dummy"))
    assert shell.timeline.undo_stack.count() == 1

    # Restore + Reload stubben, damit kein echter DB-Zugriff passiert.
    monkeypatch.setattr(tss, "restore_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(database, "get_active_project_id", lambda: 1)
    shell.timeline.load_from_db = lambda project_id=None: None

    shell._restore_snapshot(snapshot_id=7, version=3)

    assert shell.timeline.undo_stack.count() == 0, (
        "Undo-Stack nach Snapshot-Restore nicht geleert (B-689) — Ctrl+Z wuerde "
        "den wiederhergestellten Stand zerstoeren."
    )
