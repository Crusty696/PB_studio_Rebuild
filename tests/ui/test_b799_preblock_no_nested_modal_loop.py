"""B-799: Der B-465-Pre-Block darf den GUI-Thread nicht blockieren.

Live-Befund (2026-08-10, ``logs/live-verify-2026-08-11-gui.log`` +
``logs/freeze_stacks.log:219668``): bei 486 laufenden Proxy-Tasks stand der
Main-Thread >4,5 Minuten in ``project_management.py:85 _tasks_running_block``
<- ``:147 _open_project``. Zeile 85 war ``QMessageBox.warning(...)`` — die
statische Variante ruft intern ``exec()`` und haengt eine verschachtelte
Event-Loop in den GUI-Thread. Die Box wurde unter der Last nie gezeichnet und
nie bedienbar → kein Rueckweg, Force-Kill noetig.

NICHT die Ursache war ``ProjectManager._has_running_tasks`` (Zeile 68):
``GlobalTaskManager.get_all_tasks`` gibt eine Kopie unter kurzem Lock zurueck
(``services/task_manager.py:652-655``), es wird also weder ueber eine
mutierende Struktur iteriert noch ein Lock ueber den Abbruchpfad gehalten.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _ctrl():
    from ui.controllers.project_management import ProjectManagementController
    ctrl = ProjectManagementController.__new__(ProjectManagementController)
    ctrl.window = SimpleNamespace(status_bar=SimpleNamespace(showMessage=MagicMock()))
    return ctrl


def test_b799_preblock_uses_no_blocking_dialog_call():
    """Weder ``QMessageBox.warning/critical/information`` noch ``exec``."""
    from ui.controllers.project_management import ProjectManagementController

    # Nur der ausfuehrbare Code zaehlt. Docstrings und Kommentare muessen
    # raus, weil sie das ALTE Verhalten woertlich zitieren ("vorher rief das
    # QMessageBox.warning(...)") — eine reine String-Suche wuerde daran
    # haengenbleiben und der Test schluege trotz korrektem Fix fehl.
    def _executable_code(func) -> str:
        tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                     ast.ClassDef, ast.Module)):
                continue
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
        return ast.unparse(tree)

    code = (_executable_code(ProjectManagementController._tasks_running_block)
            + "\n"
            + _executable_code(ProjectManagementController._show_tasks_running_notice))
    for blocking in ("QMessageBox.warning(", "QMessageBox.critical(",
                     "QMessageBox.information(", ".exec("):
        assert blocking not in code, (
            f"B-799: '{blocking}' oeffnet eine verschachtelte Modal-Event-Loop im "
            "GUI-Thread — der Pre-Block muss nicht-blockierend sein."
        )
    assert ".show()" in code, "B-799: Hinweis muss nicht-modal via show() kommen."


def test_b799_preblock_returns_immediately_with_many_running_tasks():
    """Guard muss auch bei vielen laufenden Tasks sofort zurueckkehren."""
    ctrl = _ctrl()
    with patch("services.project_manager.ProjectManager._has_running_tasks",
               return_value=True), \
         patch("ui.controllers.project_management.QMessageBox"):
        start = time.perf_counter()
        blocked = ctrl._tasks_running_block("Projekt oeffnen")
        elapsed = time.perf_counter() - start
    assert blocked is True
    assert elapsed < 1.0, f"Pre-Block blockierte {elapsed:.2f}s (B-799)"


def test_b799_repeated_block_does_not_stack_dialogs():
    """Mehrfach-Klick darf keine Box-Kette erzeugen (Folge des show()-Wechsels)."""
    ctrl = _ctrl()
    with patch("services.project_manager.ProjectManager._has_running_tasks",
               return_value=True), \
         patch("ui.controllers.project_management.QMessageBox") as mb:
        mb.return_value.isVisible.return_value = True
        ctrl._tasks_running_block("Projekt oeffnen")
        ctrl._tasks_running_block("Projekt oeffnen")
        ctrl._tasks_running_block("Neues Projekt")
    assert mb.call_count == 1, "B-799: pro sichtbarer Box nur eine Instanz"
    assert mb.return_value.show.call_count == 1


def test_b799_has_running_tasks_iterates_over_snapshot():
    """Gegenprobe: get_all_tasks liefert eine Kopie, kein Live-Dict."""
    import services.task_manager as tm_mod

    src = inspect.getsource(tm_mod.GlobalTaskManager.get_all_tasks)
    assert "list(self._tasks.values())" in src, (
        "B-799-Diagnose beruht darauf, dass get_all_tasks() einen Snapshot "
        "unter kurzem Lock liefert."
    )
