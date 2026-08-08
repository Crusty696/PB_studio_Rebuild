"""B-772: Overlay-"Auto-Edit abbrechen" muss auch den TaskEngine-Task treffen.

Livetest 2026-08-07: Der Inline-Button cancelte nur ``_current_worker``.
War der durch den zweiten attach_worker-Pfad (``_cuts_worker``) ersetzt oder
bereits ``None``, schloss der Klick nur das Overlay — der Auto-Edit-Task lief
weiter (Playbook 2.7). Fix: ``_on_cancel`` ruft zusaetzlich
``GlobalTaskManager.cancel_task(worker.task_id)`` — denselben kooperativen
Pfad wie der TASKS-Panel-Abbrechen, der live nachweislich wirkt.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def ctrl(test_engine, monkeypatch):
    from tests.ui.test_schnitt_controller_wiring import _qapp

    _qapp()
    import ui.workspaces.schnitt_workspace as ws_mod
    monkeypatch.setattr(ws_mod, "engine", test_engine)

    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    from ui.controllers.schnitt_controller import SchnittController

    return SchnittController(SchnittWorkspace())


def test_cancel_hits_worker_and_taskengine(ctrl, monkeypatch):
    from services.task_manager import GlobalTaskManager

    cancelled: list = []
    task_cancels: list = []

    class FakeWorker:
        task_id = "task_b772_test"

        def cancel(self):
            cancelled.append(True)

    class FakeTM:
        def cancel_task(self, task_id):
            task_cancels.append(task_id)

    monkeypatch.setattr(GlobalTaskManager, "instance", staticmethod(FakeTM))

    ctrl.attach_worker(FakeWorker())
    ctrl._on_cancel()

    assert cancelled == [True]
    assert task_cancels == ["task_b772_test"]
    assert ctrl._current_worker is None


def test_cancel_without_task_id_skips_taskengine(ctrl, monkeypatch):
    from services.task_manager import GlobalTaskManager

    task_cancels: list = []

    class FakeWorker:
        def cancel(self):
            pass

    class FakeTM:
        def cancel_task(self, task_id):
            task_cancels.append(task_id)

    monkeypatch.setattr(GlobalTaskManager, "instance", staticmethod(FakeTM))

    ctrl.attach_worker(FakeWorker())
    ctrl._on_cancel()

    assert task_cancels == []


def test_cancel_with_none_worker_does_not_crash(ctrl):
    ctrl._current_worker = None
    ctrl._on_cancel()  # darf weder werfen noch TaskEngine treffen
