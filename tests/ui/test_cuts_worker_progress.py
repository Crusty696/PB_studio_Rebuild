"""Phase 09 Task 9.2: _CutsWorker stage-progress signal.

Plan: docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/
       09_WORKER_REFACTOR.md
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _get_cuts_worker_class():
    """``_CutsWorker`` ist in ``EditWorkspaceController._generate_timeline``
    lokal definiert — wir extrahieren sie via direkter Reflection."""
    import ast
    import inspect
    from ui.controllers.edit_workspace import EditWorkspaceController

    src = inspect.getsource(EditWorkspaceController._generate_timeline_impl)
    # Sicherstellen dass _CutsWorker im Source vorhanden ist
    assert "class _CutsWorker" in src
    return src


def test_cuts_worker_class_has_progress_signal_in_source():
    src = _get_cuts_worker_class()
    assert "progress = Signal(" in src, (
        "Phase 09: _CutsWorker.progress = Signal(str, float) fehlt."
    )


def test_cuts_worker_instantiates_with_progress_signal():
    """Instanziere ``_CutsWorker`` ueber den lokal-definierten Konstruktor.

    Da ``_CutsWorker`` lokal in ``_generate_timeline`` lebt, fuehren wir den
    relevanten Definitions-Block in einem isolierten Namespace aus."""
    _qapp()
    import inspect
    import textwrap
    from PySide6.QtCore import QObject, Signal, QThread  # noqa: F401
    from ui.controllers.edit_workspace import EditWorkspaceController

    src = inspect.getsource(EditWorkspaceController._generate_timeline_impl)
    # Klassen-Block extrahieren
    lines = src.splitlines()
    start = next(i for i, ln in enumerate(lines) if "class _CutsWorker" in ln)
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = start + 1
    while end < len(lines):
        ln = lines[end]
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent:
            break
        end += 1
    block = textwrap.dedent("\n".join(lines[start:end]))

    ns = {
        "QObject": QObject,
        "Signal": Signal,
        "logger": __import__("logging").getLogger("test"),
        "calculate_cut_points": lambda *a, **kw: [],
    }
    exec(block, ns)
    Cls = ns["_CutsWorker"]
    w = Cls(1, 1, None, 60.0, 1)
    assert hasattr(w, "progress")
