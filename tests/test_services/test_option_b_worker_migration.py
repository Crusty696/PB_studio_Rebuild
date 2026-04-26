"""Cycle 14 / Option B: Verifiziert dass die migrierten Inline-Workers
in project_management.py auf BaseWorker basieren."""
from __future__ import annotations

import inspect

import pytest


def test_project_management_imports_base_worker():
    from ui.controllers import project_management
    src = inspect.getsource(project_management)
    assert "from workers.base import BaseWorker" in src


def test_create_worker_extends_base_worker():
    from ui.controllers import project_management
    src = inspect.getsource(project_management)
    # CreateWorker, OpenWorker, SaveAsWorker sind alle BaseWorker-Subklassen
    assert "class CreateWorker(BaseWorker):" in src
    assert "class OpenWorker(BaseWorker):" in src
    assert "class SaveAsWorker(BaseWorker):" in src


def test_workers_use_do_work_pattern():
    """Migrierte Workers haben _do_work() statt eigenem run()-Body."""
    from ui.controllers import project_management
    src = inspect.getsource(project_management)
    # Mind. 3 _do_work-Definitionen (eine pro Worker)
    assert src.count("def _do_work(self):") >= 3


def test_no_more_inline_qobject_signal_definitions():
    """Vorher: 'finished = Signal(object); error = Signal(str)' inline.
    Jetzt: BaseWorker definiert sie zentral."""
    from ui.controllers import project_management
    src = inspect.getsource(project_management)
    # 'class XWorker(QObject):' inline-Pattern darf nicht mehr da sein
    assert "(QObject):\n            finished = Signal" not in src
    # Worker erben jetzt von BaseWorker
    assert "(BaseWorker):" in src
