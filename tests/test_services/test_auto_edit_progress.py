"""Phase 09 Task 9.1: AutoEditWorker stage-progress signal.

Plan: docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/
       09_WORKER_REFACTOR.md
"""
from __future__ import annotations

import os


def test_class_has_progress_signal() -> None:
    from services.auto_edit_worker import AutoEditWorker
    assert hasattr(AutoEditWorker, "progress")


def test_emit_progress_collects_stage_keys() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from services.auto_edit_worker import AutoEditWorker

    _app = QApplication.instance() or QApplication([])
    w = AutoEditWorker(audio_id=1, video_ids=[1], settings=None)
    received: list[tuple[str, float]] = []
    w.progress.connect(lambda s, f: received.append((s, f)))
    w._emit_stage("audio_load", 0.1)
    w._emit_stage("cut_calc", 0.5)
    assert received == [("audio_load", 0.1), ("cut_calc", 0.5)]
