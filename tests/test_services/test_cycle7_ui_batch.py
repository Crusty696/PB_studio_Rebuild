"""Cycle 7 UI-Layer — RED-Tests fuer B-171, B-172, B-173.

Source-inspection-Tests (kein Qt). Asserten strukturelle
Eigenschaften der gefixten Production-Funktionen.
"""
from __future__ import annotations

import inspect


def test_b171_cutsworker_logs_exceptions():
    """B-171: _CutsWorker.run muss logger.exception im except-Pfad rufen,
    sonst silent failure ohne Stacktrace."""
    from ui.controllers import edit_workspace as ew

    src = inspect.getsource(ew)
    # Den genauen _CutsWorker-Block finden
    assert "_CutsWorker" in src, "_CutsWorker fehlt"
    cw_idx = src.find("class _CutsWorker")
    cw_end = src.find("\n        self._cuts_worker = _CutsWorker", cw_idx)
    cw_body = src[cw_idx:cw_end] if cw_end > cw_idx else src[cw_idx:cw_idx + 1500]

    # logger.exception oder logger.error innerhalb des except-Blocks
    assert "logger.exception" in cw_body or "logger.error" in cw_body, (
        "_CutsWorker.run muss Exceptions loggen (B-171)."
    )


def test_b172_generate_timeline_uses_sequence_counter():
    """B-172: _generate_timeline_impl muss eine Sequence-Counter-Strategie
    nutzen (Worker-Cancel via requestInterruption ist no-op fuer einen
    nicht-pollenden run())."""
    from ui.controllers import edit_workspace as ew

    src = inspect.getsource(ew.EditWorkspaceController._generate_timeline_impl)
    assert "_gen_seq" in src or "_gen_sequence" in src or "seq" in src, (
        "_generate_timeline_impl muss eine Sequence-Counter-Strategie "
        "nutzen damit Stale-Worker-Results verworfen werden (B-172)."
    )


def test_b173_worker_dispatcher_handles_already_finished_thread():
    """B-173: WorkerDispatcher else-Branch muss isRunning()-Check nach
    finished.connect machen, sonst Race-Hang."""
    from ui.controllers import worker_dispatcher

    src = inspect.getsource(worker_dispatcher.WorkerDispatcherController._start_worker_thread)
    # Heuristik: irgendwo nach `task.thread.finished.connect` muss ein
    # isRunning()-Check oder ein direkter _cleanup_worker-Aufruf folgen.
    # B-222 F2: Window vergroessert von 600 -> 1200, weil das connect()
    # jetzt mehrzeilig formatiert ist (mit Qt.ConnectionType.QueuedConnection
    # als 3. Argument) — der Race-Guard-Block steht weiterhin direkt darunter,
    # nur einige Zeilen weiter weg.
    connect_idx = src.find("task.thread.finished.connect")
    assert connect_idx > 0, "task.thread.finished.connect fehlt"
    after = src[connect_idx:connect_idx + 1200]
    assert "isRunning" in after or "_cleanup_worker(task.thread" in after, (
        "WorkerDispatcher muss nach finished.connect pruefen ob Thread "
        "schon fertig ist (B-173 race)."
    )
