"""B-751: Legacy-Dispatcher muss B-724-Cancel-Vorrang verwenden."""

from __future__ import annotations

import inspect
import logging


def test_precreated_task_error_uses_cancel_preserving_handler():
    from ui.controllers.worker_dispatcher import WorkerDispatcherController

    source = inspect.getsource(WorkerDispatcherController._start_worker_thread)
    assert "_handle_worker_error" in source
    assert "_tm.finish_task(_tid, status=\"error\"" not in source


def test_cancel_transport_is_not_logged_as_worker_error(qapp, caplog):
    from services.task_manager import GlobalTaskManager

    manager = GlobalTaskManager.instance()
    task = manager.create_task("b751 cancel log")
    manager.cancel_task(task.task_id)

    with caplog.at_level(logging.DEBUG):
        manager._handle_worker_error(
            task.task_id,
            "AudioPipelineV2",
            (1, "Audio-V2 Stage 'av_pacing' abgebrochen (User-Cancel)"),
        )

    assert manager.get_task(task.task_id).status == "cancelled"
    assert not any(
        record.levelno >= logging.ERROR and "Worker-Fehler" in record.message
        for record in caplog.records
    )
