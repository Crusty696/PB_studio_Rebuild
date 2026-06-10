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
