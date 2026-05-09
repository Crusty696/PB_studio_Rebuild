"""SchnittController — verbindet Workers mit SchnittWorkspace-States.

Plan: docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/
       09_WORKER_REFACTOR.md  (Task 9.3)
"""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject


class SchnittController(QObject):
    def __init__(self, workspace, parent=None):
        super().__init__(parent)
        self.workspace = workspace
        self._current_worker: Any | None = None
        workspace.cancel_requested.connect(self._on_cancel)

    def attach_worker(self, worker: Any) -> None:
        self._current_worker = worker
        if hasattr(worker, "progress"):
            worker.progress.connect(self.workspace.show_progress)
        if hasattr(worker, "done"):
            worker.done.connect(self._on_done)
        if hasattr(worker, "failed"):
            worker.failed.connect(self._on_failed)

    def _on_done(self, *args, **kwargs):
        self.workspace.refresh_state_from_db()
        self._current_worker = None

    def _on_failed(self, *args, **kwargs):
        self.workspace.refresh_state_from_db()
        self._current_worker = None

    def _on_cancel(self):
        if self._current_worker is not None and hasattr(self._current_worker, "cancel"):
            try:
                self._current_worker.cancel()
            except Exception:
                pass
        self.workspace.refresh_state_from_db()
        self._current_worker = None
