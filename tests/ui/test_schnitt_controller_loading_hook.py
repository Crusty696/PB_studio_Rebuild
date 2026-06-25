"""Phase 09 Task 9.3: SchnittController routes worker progress.

Plan: docs/superpowers/archive/2026-05-09-schnitt-workspace-redesign/
       09_WORKER_REFACTOR.md
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class FakeWorker:
    def __init__(self):
        from PySide6.QtCore import QObject, Signal

        class _W(QObject):
            progress = Signal(str, float)
            done = Signal(list, float, int)
            failed = Signal(str, int)

        self.q = _W()


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_controller_routes_progress_to_loading_view():
    _qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_LOADING
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)
    fake = FakeWorker()
    ctrl.attach_worker(fake.q)
    ws.enter_loading()
    fake.q.progress.emit("cut_calc", 0.42)
    assert ws.current_state() == STATE_LOADING
    assert "Schnitte" in ws.loading_view.status_label.text()
    assert ws.loading_view.progress_bar.value() == 42
