"""Test-Isolation fuer die ui-Test-Suite.

Hintergrund: der ``GlobalTaskManager`` ist ein prozessweiter Singleton. Einzelne
ui-Tests legen Tasks an, die als ``status="running"`` zurueckbleiben koennen
(geleakter State zwischen Tests). Im monolithischen Suite-Lauf sieht dann
``PBWindow.closeEvent`` (main.py) diese "laufenden" Tasks und oeffnet einen
MODALEN ``QMessageBox.question`` ("Laufende Tasks ... Trotzdem beenden?"), der im
headless/offscreen-Lauf nie beantwortet wird -> die ganze Suite haengt.

Diese autouse-Fixture raeumt den Singleton nach JEDEM ui-Test, sodass kein
geleakter "running"-Task in einen Folge-Test (insb. die closeEvent-Tests)
blutet. Reines Test-Harness-Verhalten; Produktcode bleibt unveraendert.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_global_task_manager():
    """Raeumt nach jedem ui-Test die Tasks des GlobalTaskManager-Singletons."""
    yield
    try:
        from services.task_manager import GlobalTaskManager
        inst = GlobalTaskManager._instance
        if inst is not None:
            with inst._tasks_lock:
                inst._tasks.clear()
    except Exception:  # best-effort: Test-Cleanup darf nie selbst faillen
        pass


@pytest.fixture(autouse=True)
def _drain_qt_deferred_deletes():
    """B-651: order-abhaengiger nativer Crash im Voll-Lauf von tests/ui.

    Widgets/Worker aus Test A werden via ``deleteLater()`` zerstoert, das
    DeferredDelete-Event haengt aber noch in der Event-Queue, wenn Test B
    (oder erst Test Z) das naechste Mal ``processEvents()``/``exec()`` ruft —
    dann feuert die native Zerstoerung gegen laengst invalidierte
    Python-Wrapper/Signal-Verbindungen und toetet den Prozess ohne Summary.

    Gegenmittel: nach JEDEM Test die DeferredDelete-Events sofort im
    Kontext ihres Tests abarbeiten, solange die beteiligten Objekte noch
    konsistent sind. Reines Test-Harness-Verhalten, kein Produktcode.
    """
    yield
    try:
        from PySide6.QtCore import QCoreApplication, QEvent
        app = QCoreApplication.instance()
        if app is not None:
            for _ in range(3):
                app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                app.processEvents()
        # KEIN gc.collect() hier: GC unmittelbar nach dem DeferredDelete-Drain
        # raeumt Python-Wrapper frisch zerstoerter C++-Objekte ab und provozierte
        # 0xC0000374 (Heap-Corruption) — live bewiesen via faulthandler-Stack
        # ("Garbage-collecting" in dieser Fixture, test_schnitt_controller_wiring).
    except Exception:  # best-effort: Test-Cleanup darf nie selbst faillen
        pass
