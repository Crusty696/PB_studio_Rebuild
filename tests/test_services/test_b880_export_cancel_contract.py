"""B-880: User-Cancel ist kein Renderfehler und darf keinen Fallback starten."""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_batch_cancel_propagates_without_hardcut_fallback(monkeypatch, tmp_path):
    from services import export_service

    assert hasattr(export_service, "ExportCancelled")
    cancel_type = export_service.ExportCancelled
    fallback_calls: list[bool] = []

    def _cancel(*args, **kwargs):
        Path(args[2]).write_bytes(b"partial-mp4-without-moov")
        raise cancel_type("Export abgebrochen (User-Cancel)")

    def _fallback(*args, **kwargs):
        fallback_calls.append(True)
        return "unexpected-fallback.mp4"

    monkeypatch.setattr(export_service, "_export_with_filtergraph_batched", _cancel)
    monkeypatch.setattr(export_service, "_export_optimized_concat", _fallback)

    segments = [
        {
            "path": f"clip-{index}.mp4",
            "start": float(index),
            "end": float(index + 1),
            "source_start": 0.0,
            "source_duration": 1.0,
            "transition_duration": 0.25,
        }
        for index in range(export_service.XFADE_BATCH_SIZE + 1)
    ]

    output_path = tmp_path / "cancelled.mp4"
    with pytest.raises(cancel_type):
        export_service._export_with_filtergraph(
            segments,
            None,
            output_path,
            "1920",
            "1080",
            30.0,
            None,
            4,
            cancel_check=lambda: True,
        )

    assert fallback_calls == []
    assert not output_path.exists()


def test_export_worker_cancel_emits_no_error_or_crash(monkeypatch, caplog):
    from services import export_service
    from workers import import_export

    assert hasattr(export_service, "ExportCancelled")

    def _cancelled_export(**kwargs):
        raise export_service.ExportCancelled("Export abgebrochen (User-Cancel)")

    monkeypatch.setattr(import_export, "export_timeline", _cancelled_export)
    worker = import_export.ExportWorker(project_id=1, output_name="cancelled.mp4")
    finished: list[str] = []
    errors: list[str] = []
    worker.finished.connect(finished.append)
    worker.error.connect(errors.append)

    with caplog.at_level(logging.ERROR):
        worker.run()

    assert finished == [""]
    assert errors == []
    assert "ExportWorker crashed" not in caplog.text
    assert "Traceback" not in caplog.text


def test_export_controller_keeps_cancelled_task_on_empty_finish(monkeypatch):
    from ui.controllers import export as export_controller

    class _Widget:
        def setEnabled(self, value):
            pass

        def setText(self, value):
            pass

        def setVisible(self, value):
            pass

    class _TaskManager:
        def __init__(self):
            self.task = SimpleNamespace(status="cancelled")
            self.finish_calls: list[tuple] = []

        def get_task(self, task_id):
            return self.task

        def finish_task(self, *args):
            self.finish_calls.append(args)

    fake_manager = _TaskManager()
    monkeypatch.setattr(export_controller, "task_manager", fake_manager)
    controller = SimpleNamespace(
        window=SimpleNamespace(
            btn_export=_Widget(),
            export_progress=_Widget(),
        )
    )

    export_controller.ExportController._on_export_finished(
        controller, "", "task-cancelled"
    )

    assert fake_manager.finish_calls == []
    assert fake_manager.task.status == "cancelled"
